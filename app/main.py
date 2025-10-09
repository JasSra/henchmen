"""
DeployBot Controller - FastAPI Application
"""
import os
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Header, Response, File, UploadFile
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from app.models import (
    Agent, AgentRegister, AgentStatus, HeartbeatRequest, HeartbeatResponse,
    Job, JobCreate, JobResponse, JobStatus,
    HostInfo, HostsResponse,
    GitHubPushEvent, WebhookResponse,
    LogEntry, SSHDeploymentRequest, SSHDeploymentResponse,
    SSHDeploymentMode, HostConfigurationModel
)
from app.store import Store
from app.queue import JobQueue
from app.webhooks import WebhookHandler
from app.ai_assistant import AIAssistant, AIChatRequest, AIChatResponse, AIInsight, AIMessage
from app.ssh_connector import SSHConnector, SSHCredentials, SSHConnectionPool

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings"""
    host: str = "0.0.0.0"
    port: int = 8080
    database_path: str = "./data/deploybot.db"
    github_webhook_secret: str = "your-webhook-secret-here"
    log_level: str = "INFO"
    openai_api_key: Optional[str] = None
    ai_model: str = "gpt-4o-mini"
    ai_enabled: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global state
settings = Settings()
store: Store
job_queue: JobQueue
webhook_handler: WebhookHandler
ai_assistant: Optional[AIAssistant] = None
log_subscribers: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    global store, job_queue, webhook_handler, ai_assistant
    
    # Initialize store
    store = Store(settings.database_path)
    await store.init_db()
    
    # Initialize job queue
    job_queue = JobQueue(store)
    await job_queue.initialize()
    
    # Initialize webhook handler
    webhook_handler = WebhookHandler(
        secret=settings.github_webhook_secret,
        config_path="./config/apps.yaml"
    )
    
    # Initialize AI assistant if enabled and API key provided
    global ai_assistant
    if settings.ai_enabled and settings.openai_api_key:
        ai_assistant = AIAssistant(
            api_key=settings.openai_api_key,
            store=store,
            job_queue=job_queue,
            model=settings.ai_model
        )
    
    yield
    
    # Cleanup (if needed)


# Create FastAPI app
app = FastAPI(
    title="DeployBot Controller",
    description="Lightweight deployment orchestration controller",
    version="0.1.0",
    lifespan=lifespan
)


# Mount static files for UI
app.mount("/static", StaticFiles(directory="ui"), name="static")


# UI Routes
@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def serve_ui():
    """Serve the main UI dashboard (AI-enhanced if enabled)"""
    # Serve AI-enhanced UI if AI is enabled, otherwise standard UI
    ui_file = "ui/index_ai.html" if ai_assistant else "ui/index.html"
    with open(ui_file, "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/install.sh", response_class=FileResponse, tags=["UI"])
async def serve_install_script():
    """Serve the agent installation script"""
    return FileResponse(
        path="ui/install.sh",
        media_type="text/x-shellscript",
        filename="install.sh"
    )


# Agent endpoints
@app.post("/v1/agents/register", response_model=Agent, tags=["Agents"])
async def register_agent(agent_data: AgentRegister) -> Agent:
    """Register a new agent"""
    # Check if agent already exists by hostname
    existing_agent = await store.get_agent_by_hostname(agent_data.hostname)
    
    if existing_agent:
        # Update existing agent
        existing_agent.last_heartbeat = datetime.utcnow()
        existing_agent.status = AgentStatus.ONLINE
        existing_agent.capabilities = agent_data.capabilities
        await store.save_agent(existing_agent)
        return existing_agent
    
    # Create new agent
    agent = Agent(
        id=str(uuid.uuid4()),
        hostname=agent_data.hostname,
        capabilities=agent_data.capabilities,
        status=AgentStatus.ONLINE,
        registered_at=datetime.utcnow(),
        last_heartbeat=datetime.utcnow()
    )
    
    await store.save_agent(agent)
    return agent


@app.post("/v1/agents/{agent_id}/heartbeat", response_model=HeartbeatResponse, tags=["Agents"])
async def agent_heartbeat(agent_id: str, heartbeat: HeartbeatRequest) -> HeartbeatResponse:
    """Process agent heartbeat and return job if available"""
    # Get agent
    agent = await store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Update agent heartbeat
    agent.last_heartbeat = datetime.utcnow()
    agent.status = heartbeat.status
    await store.save_agent(agent)
    
    # Check for pending jobs for this agent's hostname
    next_job = await job_queue.get_next_job_for_host(agent.hostname)
    
    if next_job:
        # Assign job to agent
        next_job.assigned_agent = agent_id
        await store.save_job(next_job)
        
        return HeartbeatResponse(acknowledged=True, job=next_job)
    
    return HeartbeatResponse(acknowledged=True, job=None)


# Job endpoints
@app.post("/v1/jobs", response_model=JobResponse, tags=["Jobs"], status_code=201)
async def create_job(job_data: JobCreate) -> JobResponse:
    """Create a new deployment job"""
    job = await job_queue.enqueue(job_data)
    return JobResponse(job=job)


@app.get("/v1/jobs/{job_id}", response_model=JobResponse, tags=["Jobs"])
async def get_job(job_id: str) -> JobResponse:
    """Get job details"""
    job = await job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobResponse(job=job)


@app.get("/v1/jobs", response_model=list[Job], tags=["Jobs"])
async def list_jobs() -> list[Job]:
    """List all jobs"""
    jobs = await job_queue.list_jobs()
    return jobs


@app.put("/v1/jobs/{job_id}/status", tags=["Jobs"])
async def update_job_status(job_id: str, status_update: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update job status (called by agents when job completes)
    
    Body should contain:
    - status: "success" or "failed"
    - error: optional error message if failed
    """
    status = status_update.get("status", "unknown")
    error = status_update.get("error")
    
    # Map status to JobStatus enum
    job_status_map = {
        "success": JobStatus.SUCCESS,
        "failed": JobStatus.FAILED,
        "running": JobStatus.RUNNING,
        "pending": JobStatus.PENDING
    }
    
    new_status = job_status_map.get(status, JobStatus.FAILED)
    
    # Update job in store
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job.status = new_status
    if error:
        job.error = error
    job.completed_at = datetime.utcnow()
    
    await store.update_job(job)
    
    logger.info(f"Job {job_id} status updated to {status}")
    
    return {
        "job_id": job_id,
        "status": status,
        "updated": True
    }


# Host endpoints
@app.get("/v1/hosts", response_model=HostsResponse, tags=["Hosts"])
async def list_hosts() -> HostsResponse:
    """List all registered hosts (agents)"""
    agents = await store.list_agents()
    
    hosts = [
        HostInfo(
            hostname=agent.hostname,
            agent_id=agent.id,
            agent_status=agent.status,
            last_seen=agent.last_heartbeat
        )
        for agent in agents
    ]
    
    return HostsResponse(hosts=hosts)


# Webhook endpoints
@app.post("/v1/webhooks/github", response_model=WebhookResponse, tags=["Webhooks"])
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None)
) -> WebhookResponse:
    """Handle GitHub webhook push events"""
    # Get raw body for signature verification
    body = await request.body()
    
    # Verify signature
    if not webhook_handler.verify_signature(body, x_hub_signature_256 or ""):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse event
    try:
        event_data = await request.json()
        event = GitHubPushEvent(**event_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {str(e)}")
    
    # Process event and create jobs
    job_requests = webhook_handler.process_push_event(event)
    
    created_job_ids = []
    for job_request in job_requests:
        job = await job_queue.enqueue(job_request)
        created_job_ids.append(job.id)
    
    return WebhookResponse(
        received=True,
        jobs_created=created_job_ids,
        message=f"Created {len(created_job_ids)} deployment job(s)"
    )


# Log streaming endpoint (SSE)
@app.get("/v1/logs/stream", tags=["Logs"])
async def stream_logs(
    host: Optional[str] = None,
    app: Optional[str] = None
):
    """Stream logs via Server-Sent Events"""
    async def event_generator():
        # Send initial logs
        logs = await store.get_logs(host=host, app=app, limit=50)
        for log in reversed(logs):
            yield f"data: {log.model_dump_json()}\n\n"
        
        # Keep connection alive and send new logs
        # In production, this would use a pub/sub mechanism
        while True:
            await asyncio.sleep(1)
            # This is a placeholder - in real implementation,
            # you'd subscribe to new log events
            yield f"data: {{}}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# Health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# AI Assistant endpoints
@app.get("/v1/ai/status", tags=["AI Assistant"])
async def ai_status():
    """Check AI assistant status"""
    global ai_assistant
    return {
        "ai_assistant": ai_assistant is not None,
        "ai_assistant_type": str(type(ai_assistant)) if ai_assistant else None,
        "settings": {
            "ai_enabled": settings.ai_enabled,
            "api_key_present": bool(settings.openai_api_key),
            "api_key_length": len(settings.openai_api_key) if settings.openai_api_key else 0
        }
    }

@app.post("/v1/ai/chat", response_model=AIChatResponse, tags=["AI Assistant"])
async def ai_chat(request: AIChatRequest):
    """Chat with AI assistant for natural language commands"""
    if not ai_assistant:
        raise HTTPException(
            status_code=503,
            detail="AI assistant not available. Set OPENAI_API_KEY in .env"
        )
    
    # If session_id is provided, load history and save messages
    if request.session_id:
        # Check if session exists
        session = await store.get_chat_session(request.session_id)
        if not session:
            # Create session if it doesn't exist
            await store.create_chat_session(request.session_id)
        
        # Load history if not provided
        if not request.conversation_history:
            history = await store.get_chat_history(request.session_id, limit=20)
            request.conversation_history = [
                AIMessage(role=msg['role'], content=msg['content'])
                for msg in history
            ]
        
        # Save user message
        await store.save_chat_message(
            request.session_id,
            "user",
            request.message
        )
    
    # Get AI response
    response = await ai_assistant.chat(request)
    
    # Save assistant response if using sessions
    if request.session_id:
        await store.save_chat_message(
            request.session_id,
            "assistant",
            response.response,
            metadata={
                "action_taken": response.action_taken,
                "quick_actions": response.quick_actions
            }
        )
    
    return response


@app.post("/v1/ai/voice", tags=["AI Assistant"])
async def ai_voice_command(audio: bytes = None):
    """Process voice command using Whisper"""
    from fastapi import File, UploadFile
    
    if not ai_assistant:
        raise HTTPException(
            status_code=503,
            detail="AI assistant not available. Set OPENAI_API_KEY in .env"
        )
    
    # This endpoint would receive audio file
    # For now, return instruction
    return {
        "message": "Upload audio file to /v1/ai/voice/upload",
        "supported_formats": ["wav", "mp3", "m4a", "webm"]
    }


@app.post("/v1/ai/voice/upload", tags=["AI Assistant"])
async def ai_voice_upload(audio: UploadFile = File(...)):
    """Upload and transcribe audio file"""
    if not ai_assistant:
        raise HTTPException(
            status_code=503,
            detail="AI assistant not available. Set OPENAI_API_KEY in .env"
        )
    
    try:
        # Read audio file
        audio_bytes = await audio.read()
        
        # Transcribe using Whisper
        text = await ai_assistant.transcribe_audio(audio_bytes, audio.filename)
        
        # Process transcribed text as command
        chat_request = AIChatRequest(message=text, conversation_history=[])
        response = await ai_assistant.chat(chat_request)
        
        return {
            "transcription": text,
            "response": response.response,
            "action_taken": response.action_taken,
            "data": response.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/ai/insights", response_model=list[AIInsight], tags=["AI Assistant"])
async def ai_insights():
    """Get AI-generated insights about system health"""
    if not ai_assistant:
        raise HTTPException(
            status_code=503,
            detail="AI assistant not available. Set OPENAI_API_KEY in .env"
        )
    
    return await ai_assistant.generate_insights()


# ==================== CHAT SESSION ENDPOINTS ====================

@app.post("/v1/ai/sessions", tags=["Chat Sessions"])
async def create_chat_session(
    user_id: str = "default",
    name: Optional[str] = None
):
    """Create a new chat session"""
    import uuid
    session_id = str(uuid.uuid4())
    await store.create_chat_session(session_id, user_id, name)
    return {"session_id": session_id, "user_id": user_id, "name": name}


@app.get("/v1/ai/sessions", tags=["Chat Sessions"])
async def list_chat_sessions(
    user_id: str = "default",
    include_archived: bool = False
):
    """List all chat sessions for a user"""
    sessions = await store.list_chat_sessions(user_id, include_archived)
    return {"sessions": sessions}


@app.get("/v1/ai/sessions/{session_id}", tags=["Chat Sessions"])
async def get_chat_session(session_id: str):
    """Get a specific chat session"""
    session = await store.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/v1/ai/sessions/{session_id}/history", tags=["Chat Sessions"])
async def get_session_history(
    session_id: str,
    limit: Optional[int] = None
):
    """Get chat history for a session"""
    session = await store.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    messages = await store.get_chat_history(session_id, limit)
    return {"session_id": session_id, "messages": messages}


@app.post("/v1/ai/sessions/{session_id}/archive", tags=["Chat Sessions"])
async def archive_session(session_id: str):
    """Archive a chat session"""
    session = await store.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await store.archive_chat_session(session_id)
    return {"message": "Session archived successfully", "session_id": session_id}


@app.post("/v1/ai/sessions/{session_id}/unarchive", tags=["Chat Sessions"])
async def unarchive_session(session_id: str):
    """Unarchive a chat session"""
    session = await store.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await store.unarchive_chat_session(session_id)
    return {"message": "Session unarchived successfully", "session_id": session_id}


@app.delete("/v1/ai/sessions/{session_id}", tags=["Chat Sessions"])
async def delete_session(session_id: str):
    """Delete a chat session and all its messages"""
    session = await store.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await store.delete_chat_session(session_id)
    return {"message": "Session deleted successfully", "session_id": session_id}


# ==================== WORKFLOW ENDPOINTS ====================

@app.post("/v1/ai/workflows/start", tags=["AI Workflows"])
async def start_workflow(
    workflow_name: str,
    context: Dict[str, Any] = None
):
    """Start a new multi-step workflow"""
    if not ai_assistant:
        raise HTTPException(
            status_code=503,
            detail="AI assistant not available"
        )
    
    try:
        response = await ai_assistant.start_workflow(workflow_name, context or {})
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/ai/workflows/{workflow_id}/approve", tags=["AI Workflows"])
async def approve_workflow_step(
    workflow_id: str,
    approved: bool,
    user_input: str = None
):
    """Approve or reject current workflow step"""
    if not ai_assistant:
        raise HTTPException(
            status_code=503,
            detail="AI assistant not available"
        )
    
    try:
        response = await ai_assistant.approve_step(workflow_id, approved, user_input)
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error approving step: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/ai/workflows/definitions", tags=["AI Workflows"])
async def list_workflow_definitions():
    """List available workflow definitions"""
    if not ai_assistant:
        raise HTTPException(
            status_code=503,
            detail="AI assistant not available"
        )
    
    return {
        "workflows": [
            {
                "name": "register_agent",
                "description": "Register a new deployment agent with validation",
                "steps": 4,
                "required_context": ["hostname"]
            },
            {
                "name": "deploy_application",
                "description": "Deploy an application with full validation",
                "steps": 4,
                "required_context": ["repository", "ref"]
            },
            {
                "name": "troubleshoot_failure",
                "description": "Analyze and fix deployment failures",
                "steps": 4,
                "required_context": []
            },
            {
                "name": "health_check",
                "description": "Comprehensive system health check",
                "steps": 4,
                "required_context": []
            }
        ]
    }


@app.get("/v1/ai/workflows/{workflow_id}", tags=["AI Workflows"])
async def get_workflow_status(workflow_id: str):
    """Get workflow status and progress"""
    if not ai_assistant:
        raise HTTPException(
            status_code=503,
            detail="AI assistant not available"
        )
    
    try:
        status = ai_assistant.get_workflow_status(workflow_id)
        return status
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/v1/ai/workflows", tags=["AI Workflows"])
async def list_workflows():
    """List all active workflows"""
    if not ai_assistant:
        raise HTTPException(
            status_code=503,
            detail="AI assistant not available"
        )
    
    return ai_assistant.list_workflows()


@app.post("/v1/ai/workflows/{workflow_id}/cancel", tags=["AI Workflows"])
async def cancel_workflow(workflow_id: str):
    """Cancel a running workflow"""
    if not ai_assistant:
        raise HTTPException(
            status_code=503,
            detail="AI assistant not available"
        )
    
    success = ai_assistant.cancel_workflow(workflow_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return {"status": "cancelled", "workflow_id": workflow_id}


# SSH Deployment Endpoints
@app.post("/v1/deploy/ssh", response_model=SSHDeploymentResponse, tags=["SSH Deployment"])
async def deploy_via_ssh(request: SSHDeploymentRequest) -> SSHDeploymentResponse:
    """
    Deploy an application using SSH (agentless deployment)
    
    This endpoint allows deploying applications without requiring a persistent agent
    on the target server. The controller connects via SSH to execute deployments.
    """
    try:
        logger.info(f"Starting SSH deployment to {request.credentials.hostname}")
        
        # Create SSH credentials
        credentials = SSHCredentials(
            hostname=request.credentials.hostname,
            port=request.credentials.port,
            username=request.credentials.username,
            password=request.credentials.password,
            private_key=request.credentials.private_key,
            private_key_passphrase=request.credentials.private_key_passphrase
        )
        
        # Create connector
        connector = SSHConnector(credentials)
        
        # Connect
        if not await connector.connect():
            return SSHDeploymentResponse(
                success=False,
                message="Failed to connect via SSH",
                error="SSH connection failed"
            )
        
        try:
            # Execute deployment
            result = await connector.execute_deployment(
                repo_url=request.repo_url,
                ref=request.ref,
                container_name=request.container_name
            )
            
            return SSHDeploymentResponse(
                success=result.success,
                message="Deployment completed" if result.success else "Deployment failed",
                output=result.output,
                error=result.error
            )
        
        finally:
            await connector.disconnect()
    
    except Exception as e:
        logger.error(f"SSH deployment error: {e}")
        return SSHDeploymentResponse(
            success=False,
            message="Deployment failed",
            error=str(e)
        )


@app.post("/v1/ssh/execute", tags=["SSH Deployment"])
async def execute_ssh_command(
    hostname: str,
    command: str,
    credentials: SSHDeploymentRequest
) -> Dict[str, Any]:
    """
    Execute a command on a remote host via SSH
    
    Useful for debugging and testing SSH connectivity
    """
    try:
        ssh_creds = SSHCredentials(
            hostname=credentials.credentials.hostname,
            port=credentials.credentials.port,
            username=credentials.credentials.username,
            password=credentials.credentials.password,
            private_key=credentials.credentials.private_key,
            private_key_passphrase=credentials.credentials.private_key_passphrase
        )
        
        connector = SSHConnector(ssh_creds)
        
        if not await connector.connect():
            raise HTTPException(status_code=500, detail="SSH connection failed")
        
        try:
            result = await connector.execute_command(command)
            
            return {
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "exit_code": result.exit_code
            }
        finally:
            await connector.disconnect()
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/ssh/metrics/{hostname}", tags=["SSH Deployment"])
async def get_ssh_host_metrics(
    hostname: str,
    credentials: SSHDeploymentRequest
) -> Dict[str, Any]:
    """
    Get system metrics from a remote host via SSH
    """
    try:
        ssh_creds = SSHCredentials(
            hostname=credentials.credentials.hostname,
            port=credentials.credentials.port,
            username=credentials.credentials.username,
            password=credentials.credentials.password,
            private_key=credentials.credentials.private_key,
            private_key_passphrase=credentials.credentials.private_key_passphrase
        )
        
        connector = SSHConnector(ssh_creds)
        
        if not await connector.connect():
            raise HTTPException(status_code=500, detail="SSH connection failed")
        
        try:
            metrics = await connector.get_system_metrics()
            return metrics
        finally:
            await connector.disconnect()
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )
