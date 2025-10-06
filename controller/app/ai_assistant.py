"""AI Assistant service for DeployBot Controller.

Moved under controller/app without modification.
"""

# Copied full implementation from original app/ai_assistant.py to avoid cross-package import issues
import json
import logging
import textwrap
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timedelta

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.models import Agent, Job, JobStatus, JobCreate
from app.store import Store
from app.queue import JobQueue

logger = logging.getLogger(__name__)


class AIMessage(BaseModel):
	"""Chat message"""
	role: str  # "user", "assistant", "system"
	content: str


class AIChatRequest(BaseModel):
	"""AI chat request"""
	message: str
	conversation_history: List[AIMessage] = []
	session_id: Optional[str] = None  # Optional session ID for persistence


class AIChatResponse(BaseModel):
	"""AI chat response"""
	response: str
	action_taken: Optional[str] = None
	data: Optional[Dict[str, Any]] = None
	suggestions: Optional[List[str]] = None
	needs_input: Optional[bool] = False
	input_prompt: Optional[str] = None
	quick_actions: Optional[List[Dict[str, str]]] = None  # Quick action buttons: [{label: "Yes", action: "yes"}, ...]
	action_context: Optional[Dict[str, Any]] = None  # Context for the quick actions


class WorkflowStep(BaseModel):
	"""Individual step in a workflow"""
	id: str
	title: str
	description: str
	status: str = "pending"  # pending, in-progress, completed, failed, skipped
	prompt: Optional[str] = None
	result: Optional[Dict[str, Any]] = None
	requires_approval: bool = False
	validation_fn: Optional[str] = None  # Name of validation function
    
	# Interactive input handling
	requires_input: bool = False
	input_type: Optional[str] = None  # choice, text, number, date, secret, email, url, hostname
	input_label: Optional[str] = None  # User-friendly prompt for input
	input_choices: Optional[List[str]] = None  # Available choices for 'choice' type
	input_validation: Optional[str] = None  # Regex pattern or validation rule
	input_placeholder: Optional[str] = None  # Placeholder text
	user_input: Optional[str] = None  # Captured user input
    
    

class WorkflowState(BaseModel):
	"""Workflow execution state"""
	id: str
	name: str
	description: str
	steps: List[WorkflowStep]
	current_step_index: int = 0
	context: Dict[str, Any] = {}
	started_at: Optional[datetime] = None
	completed_at: Optional[datetime] = None
	status: str = "pending"  # pending, running, completed, failed, cancelled
    

class WorkflowResponse(BaseModel):
	"""Workflow execution response"""
	workflow_id: str
	current_step: Optional[WorkflowStep] = None
	message: str
	requires_approval: bool = False
	completed: bool = False
	failed: bool = False


class AIInsight(BaseModel):
	"""AI-generated insight"""
	type: str  # "warning", "info", "success", "error"
	title: str
	message: str
	suggestion: Optional[str] = None
	timestamp: datetime


class AIAssistant:
	"""AI-powered assistant for DeployBot operations"""
    
	def __init__(
		self, 
		api_key: str, 
		store: Store, 
		job_queue: JobQueue,
		model: str = "gpt-4o-mini"
	):
		self.client = AsyncOpenAI(api_key=api_key)
		self.store = store
		self.job_queue = job_queue
		self.model = model
        
		# Workflow management
		self.workflows: Dict[str, WorkflowState] = {}
		self.workflow_definitions = self._init_workflows()
        
		# Define available functions for AI
		self.functions = [
			{
				"name": "list_agents",
				"description": "Get list of all registered agents with their status",
				"parameters": {"type": "object", "properties": {}, "required": []}
			},
			{
				"name": "list_jobs",
				"description": "Get list of deployment jobs, optionally filtered by status or host",
				"parameters": {
					"type": "object",
					"properties": {
						"status": {"type": "string", "enum": ["pending", "running", "success", "failed"]},
						"hostname": {"type": "string"},
						"limit": {"type": "integer", "default": 10}
					}
				}
			},
			{
				"name": "get_job_details",
				"description": "Get detailed information about a specific job by ID",
				"parameters": {
					"type": "object",
					"properties": {
						"job_id": {"type": "string", "description": "Job ID"}
					},
					"required": ["job_id"]
				}
			},
			{
				"name": "create_deployment",
				"description": "Create a new deployment job for a repository to a specific host",
				"parameters": {
					"type": "object",
					"properties": {
						"repository": {"type": "string", "description": "Repository name (e.g., 'myorg/app')"},
						"ref": {"type": "string", "description": "Git reference (branch, tag, or commit)"},
						"hostname": {"type": "string", "description": "Target host name"}
					},
					"required": ["repository", "ref", "hostname"]
				}
			},
			{
				"name": "get_agent_status",
				"description": "Check status and health of a specific agent by hostname",
				"parameters": {
					"type": "object",
					"properties": {
						"hostname": {"type": "string"}
					},
					"required": ["hostname"]
				}
			},
			{
				"name": "get_deployment_stats",
				"description": "Get deployment statistics and metrics",
				"parameters": {
					"type": "object",
					"properties": {
						"hours": {"type": "integer", "default": 24, "description": "Time window in hours"}
					}
				}
			},
			{
				"name": "cancel_job",
				"description": "Cancel a pending or running job",
				"parameters": {
					"type": "object",
					"properties": {
						"job_id": {"type": "string"}
					},
					"required": ["job_id"]
				}
			},
			{
				"name": "get_recent_failures",
				"description": "Get list of recent failed deployments for troubleshooting",
				"parameters": {
					"type": "object",
					"properties": {
						"limit": {"type": "integer", "default": 5}
					}
				}
			},
			{
				"name": "check_agent_health",
				"description": "Check health of all agents and identify issues",
				"parameters": {"type": "object", "properties": {}}
			},
			{
				"name": "get_deployment_history",
				"description": "Get deployment history for a specific repository or host",
				"parameters": {
					"type": "object",
					"properties": {
						"repository": {"type": "string"},
						"hostname": {"type": "string"}
					}
				}
			},
			{
				"name": "start_workflow",
				"description": "Start a guided multi-step workflow",
				"parameters": {
					"type": "object",
					"properties": {
						"workflow_name": {
							"type": "string",
							"enum": [
								"register_agent",
								"deploy_application",
								"troubleshoot_failure",
								"health_check"
							],
							"description": "Workflow to start"
						},
						"context": {
							"type": "object",
							"description": "Additional context required by the workflow (e.g., hostname, repository, ref)"
						}
					},
					"required": ["workflow_name"]
				}
			},
			{
				"name": "approve_workflow_step",
				"description": "Approve or reject the current step in a workflow",
				"parameters": {
					"type": "object",
					"properties": {
						"workflow_id": {"type": "string"},
						"approved": {"type": "boolean"},
						"user_input": {
							"type": "string",
							"description": "Optional additional notes or required input for the step"
						}
					},
					"required": ["workflow_id", "approved"]
				}
			},
			{
				"name": "cancel_workflow",
				"description": "Cancel an active workflow",
				"parameters": {
					"type": "object",
					"properties": {
						"workflow_id": {"type": "string"}
					},
					"required": ["workflow_id"]
				}
			},
			{
				"name": "get_workflow_status",
				"description": "Get the latest status for a workflow",
				"parameters": {
					"type": "object",
					"properties": {
						"workflow_id": {"type": "string"}
					},
					"required": ["workflow_id"]
				}
			},
			{
				"name": "list_workflows",
				"description": "List all active workflows",
				"parameters": {"type": "object", "properties": {}}
			},
			{
				"name": "list_workflow_definitions",
				"description": "List available workflow definitions",
				"parameters": {"type": "object", "properties": {}}
			}
		]
        
		# Map function names to implementations
		self.function_handlers: Dict[str, Callable] = {
			"list_agents": self._list_agents,
			"list_jobs": self._list_jobs,
			"get_job_details": self._get_job_details,
			"create_deployment": self._create_deployment,
			"get_agent_status": self._get_agent_status,
			"get_deployment_stats": self._get_deployment_stats,
			"cancel_job": self._cancel_job,
			"get_recent_failures": self._get_recent_failures,
			"check_agent_health": self._check_agent_health,
			"get_deployment_history": self._get_deployment_history,
			"start_workflow": self._start_workflow_action,
			"approve_workflow_step": self._approve_workflow_step_action,
			"cancel_workflow": self._cancel_workflow_action,
			"get_workflow_status": self._get_workflow_status_action,
			"list_workflows": self._list_workflows_action,
			"list_workflow_definitions": self._list_workflow_definitions_action,
		}
    
	async def chat(self, request: AIChatRequest) -> AIChatResponse:
		"""Process chat message and execute actions"""
		try:
			# Build messages
			system_prompt = """You are a helpful AI assistant for DeployBot, a deployment orchestration system. 

**Core Capabilities:**
- Deploy applications to servers
- Check deployment status and logs
- Manage agents (deployment workers)
- Monitor system health and metrics
- Troubleshoot failed deployments
- Guide users through complex workflows

**Available Workflows:**
1. **Register Agent** - Safely onboard a new deployment agent (requires: hostname)
2. **Deploy Application** - Deploy an app with pre-flight checks (requires: repository, ref)
3. **Troubleshoot Failure** - Diagnose and fix failed deployments
4. **Health Check** - Run comprehensive system health check

**Workflow Guidance - IMPORTANT:**
When a user's request matches a workflow scenario (e.g., "help me add a new agent", "deploy my app", "fix this failure"):
1. Recognize the intent and suggest the appropriate workflow by name
2. Present it as a helpful guided journey: "I can guide you through [workflow name]. This will help you [benefit]."
3. Ask for any required context (hostname, repository, etc.) in a friendly conversational way
4. Once you have required info, call start_workflow with the context
5. Guide the user through each step, explaining what's happening
6. When a step requires_approval, explain what it will do and ask "Ready to proceed?"
7. When a step requires_input, ask for the specific input using the input_label
8. Validate user responses before proceeding
9. Track progress and let them know how many steps remain
10. Celebrate completion or help troubleshoot failures

**Input Types You May Encounter:**
- choice: Present options clearly, ask user to select one
- text: Ask for free-form text input
- number: Request a numeric value with context
- date: Request a date (explain format if needed)
- secret: Remind user input will be handled securely
- hostname: Validate hostname format
- email: Validate email format
- url: Validate URL format

**Communication Style:**
- Be conversational and friendly, not robotic
- Use emojis sparingly (✅ ❌ 🚀 ⚠️) for visual clarity
- Break complex info into digestible chunks
- Confirm actions before executing
- Guide users through their journey step-by-step
- Ask clarifying questions when needed
- Provide context for each workflow step

**CRITICAL - Quick Actions:**
ALWAYS end your responses with actionable choices so users can click instead of type:
- For yes/no questions: End with "Options: [Yes, let's do it] [No, maybe later]"
- For approvals: "Ready to proceed? [✅ Yes, proceed] [❌ No, cancel]"
- For choices: List each option on a new line starting with "→"
- For next steps: "What would you like to do? [Continue] [Skip] [Cancel]"

The system will automatically convert these into clickable buttons. Make it obvious what the options are!

**Example Interaction:**
User: "I need to add a new server"
You: "I can help you register a new agent! 🚀 I'll guide you through a 4-step process to safely onboard your server. First, what's the hostname of the server you want to add?"
User: "web-server-01"
You: [starts workflow] "Great! Starting the agent registration workflow for **web-server-01**. 

Step 1/4: Validating hostname format... ✅ 
The hostname looks good and isn't already registered. 

Step 2/4: Checking connectivity...
Ready to test the connection? This will verify the agent can reach the controller.

[✅ Yes, proceed] [❌ No, cancel]"

Remember: You're a helpful guide making complex DevOps tasks simple and approachable! Always provide clickable options!"""

			messages = [{"role": "system", "content": system_prompt}]
            
			# Check for active workflows and add context
			active_workflows = [w for w in self.workflows.values() if w.status == "running"]
			if active_workflows:
				workflow_context = "\n\n**ACTIVE WORKFLOWS IN THIS SESSION:**\n"
				for workflow in active_workflows:
					current_step = workflow.steps[workflow.current_step_index] if workflow.current_step_index < len(workflow.steps) else None
					workflow_context += f"\n- **{workflow.name}** (ID: {workflow.id})\n"
					workflow_context += f"  Status: {workflow.status}\n"
					workflow_context += f"  Progress: Step {workflow.current_step_index + 1}/{len(workflow.steps)}\n"
					if current_step:
						workflow_context += f"  Current: {current_step.title} - {current_step.description}\n"
						if current_step.requires_approval:
							workflow_context += f"  ⚠️ Awaiting approval: Ask user if they want to proceed\n"
						if current_step.requires_input:
							workflow_context += f"  📝 Needs input ({current_step.input_type}): {current_step.input_label}\n"
							if current_step.input_choices:
								workflow_context += f"  Options: {', '.join(current_step.input_choices)}\n"
				workflow_context += "\n**Remember to reference the active workflow and guide the user through their current step!**"
                
				messages[0]["content"] += workflow_context
            
			# Add conversation history
			for msg in request.conversation_history:
				messages.append({"role": msg.role, "content": msg.content})
            
			# Add user message
			messages.append({"role": "user", "content": request.message})
            
			# Call OpenAI with function calling
			response = await self.client.chat.completions.create(
				model=self.model,
				messages=messages,
				tools=[{"type": "function", "function": f} for f in self.functions],
				tool_choice="auto"
			)
            
			message = response.choices[0].message
			action_taken = None
			data = None
            
			# Handle function calls
			if message.tool_calls:
				for tool_call in message.tool_calls:
					function_name = tool_call.function.name
					function_args = json.loads(tool_call.function.arguments)
                    
					logger.info(f"AI calling function: {function_name} with args: {function_args}")
                    
					# Execute function
					if function_name in self.function_handlers:
						result = await self.function_handlers[function_name](**function_args)
						action_taken = function_name
						data = result
                        
						# Add function result to messages for final response
						messages.append({
							"role": "assistant",
							"content": None,
							"tool_calls": [tool_call.model_dump()]
						})
						messages.append({
							"role": "tool",
							"tool_call_id": tool_call.id,
							"content": json.dumps(result)
						})
                
				# Get final response with function results
				final_response = await self.client.chat.completions.create(
					model=self.model,
					messages=messages
				)
                
				response_text = final_response.choices[0].message.content
			else:
				response_text = message.content
            
			# Generate contextual suggestions
			suggestions = await self._generate_suggestions(request.message, response_text, action_taken, data)
            
			# Check if AI is asking for input
			needs_input = self._check_needs_input(response_text)
			input_prompt = self._extract_input_prompt(response_text) if needs_input else None
            
			# Extract quick action buttons from response
			quick_actions = self._extract_quick_actions(response_text)
            
			# Build action context
			action_context = None
			active_workflows = [w for w in self.workflows.values() if w.status == "running"]
			if active_workflows or quick_actions:
				action_context = {
					"workflow_active": len(active_workflows) > 0,
					"has_quick_actions": len(quick_actions) > 0 if quick_actions else False
				}
            
			return AIChatResponse(
				response=response_text,
				action_taken=action_taken,
				data=data,
				suggestions=suggestions,
				needs_input=needs_input,
				input_prompt=input_prompt,
				quick_actions=quick_actions if quick_actions else None,
				action_context=action_context
			)
            
		except Exception as e:
			logger.error(f"AI chat error: {e}")
			return AIChatResponse(
				response=f"Sorry, I encountered an error: {str(e)}",
				action_taken=None,
				data=None,
				suggestions=["Try rephrasing your question", "Check system status", "View recent jobs"]
			)
    
	async def transcribe_audio(self, audio_file: bytes, filename: str = "audio.wav") -> str:
		"""Transcribe audio using Whisper"""
		try:
			# Create a file-like object
			from io import BytesIO
			audio_buffer = BytesIO(audio_file)
			audio_buffer.name = filename
            
			transcript = await self.client.audio.transcriptions.create(
				model="whisper-1",
				file=audio_buffer
			)
            
			return transcript.text
		except Exception as e:
			logger.error(f"Audio transcription error: {e}")
			raise
    
	async def generate_insights(self) -> List[AIInsight]:
		"""Generate AI insights about system health and performance"""
		insights = []
        
		try:
			# Get recent data
			agents = await self.store.list_agents()
			jobs = await self.store.list_jobs()
            
			# Analyze agent health
			now = datetime.now()
			stale_agents = [
				a for a in agents 
				if (now - a.last_heartbeat).total_seconds() > 30
			]
            
			if stale_agents:
				insights.append(AIInsight(
					type="warning",
					title="Stale Agents Detected",
					message=f"{len(stale_agents)} agent(s) haven't sent heartbeat in 30+ seconds",
					suggestion="Check if agents are running: " + ", ".join([a.hostname for a in stale_agents]),
					timestamp=now
				))
            
			# Analyze recent failures
			recent_jobs = [j for j in jobs if (now - j.created_at).total_seconds() < 3600]
			failed_jobs = [j for j in recent_jobs if j.status == JobStatus.FAILED]
            
			if len(failed_jobs) > 3:
				insights.append(AIInsight(
					type="error",
					title="High Failure Rate",
					message=f"{len(failed_jobs)} deployments failed in the last hour",
					suggestion="Check recent error logs and agent connectivity",
					timestamp=now
				))
            
			# Check for pending jobs piling up
			pending_jobs = [j for j in jobs if j.status == JobStatus.PENDING]
			if len(pending_jobs) > 10:
				insights.append(AIInsight(
					type="warning",
					title="Job Queue Buildup",
					message=f"{len(pending_jobs)} jobs pending execution",
					suggestion="Ensure agents are connected and polling regularly",
					timestamp=now
				))
            
			# Success insights
			if len(agents) > 0 and len(stale_agents) == 0:
				insights.append(AIInsight(
					type="success",
					title="All Agents Healthy",
					message=f"{len(agents)} agent(s) active and responding",
					timestamp=now
				))
            
			success_rate = 0
			if recent_jobs:
				success_jobs = [j for j in recent_jobs if j.status == JobStatus.SUCCESS]
				success_rate = (len(success_jobs) / len(recent_jobs)) * 100
                
				if success_rate > 90:
					insights.append(AIInsight(
						type="success",
						title="High Success Rate",
						message=f"{success_rate:.1f}% success rate in the last hour",
						timestamp=now
					))
            
			return insights
            
		except Exception as e:
			logger.error(f"Error generating insights: {e}")
			return insights
    
	# Function implementations
	async def _list_agents(self, **kwargs) -> Dict[str, Any]:
		"""List all agents"""
		agents = await self.store.list_agents()
		return {
			"count": len(agents),
			"agents": [
				{
					"hostname": a.hostname,
					"version": a.version,
					"last_heartbeat": a.last_heartbeat.isoformat(),
					"seconds_since_heartbeat": (datetime.now() - a.last_heartbeat).total_seconds()
				}
				for a in agents
			]
		}
    
	async def _list_jobs(self, status: Optional[str] = None, hostname: Optional[str] = None, limit: int = 10, **kwargs) -> Dict[str, Any]:
		"""List jobs with optional filters"""
		jobs = await self.store.list_jobs()
        
		# Filter
		if status:
			jobs = [j for j in jobs if j.status.value == status]
		if hostname:
			jobs = [j for j in jobs if j.hostname == hostname]
        
		# Sort by created_at desc and limit
		jobs = sorted(jobs, key=lambda j: j.created_at, reverse=True)[:limit]
        
		return {
			"count": len(jobs),
			"jobs": [
				{
					"id": j.id,
					"repository": j.repository,
					"ref": j.ref,
					"hostname": j.hostname,
					"status": j.status.value,
					"created_at": j.created_at.isoformat(),
					"updated_at": j.updated_at.isoformat() if j.updated_at else None
				}
				for j in jobs
			]
		}
    
	async def _get_job_details(self, job_id: str, **kwargs) -> Dict[str, Any]:
		"""Get job details"""
		job = await self.store.get_job(job_id)
		if not job:
			return {"error": "Job not found"}
        
		logs = await self.store.get_logs(job_id)
        
		return {
			"id": job.id,
			"repository": job.repository,
			"ref": job.ref,
			"hostname": job.hostname,
			"status": job.status.value,
			"created_at": job.created_at.isoformat(),
			"updated_at": job.updated_at.isoformat() if job.updated_at else None,
			"started_at": job.started_at.isoformat() if job.started_at else None,
			"completed_at": job.completed_at.isoformat() if job.completed_at else None,
			"log_count": len(logs)
		}
    
	async def _create_deployment(self, repository: str, ref: str, hostname: str, **kwargs) -> Dict[str, Any]:
		"""Create a deployment"""
		job = JobCreate(repository=repository, ref=ref, hostname=hostname)
		created_job = await self.job_queue.enqueue(job)
        
		return {
			"success": True,
			"job_id": created_job.id,
			"repository": created_job.repository,
			"ref": created_job.ref,
			"hostname": created_job.hostname,
			"status": created_job.status.value
		}
    
	async def _get_agent_status(self, hostname: str, **kwargs) -> Dict[str, Any]:
		"""Get agent status"""
		agent = await self.store.get_agent_by_hostname(hostname)
		if not agent:
			return {"error": "Agent not found"}
        
		seconds_since = (datetime.now() - agent.last_heartbeat).total_seconds()
		is_healthy = seconds_since < 30
        
		return {
			"hostname": agent.hostname,
			"version": agent.version,
			"last_heartbeat": agent.last_heartbeat.isoformat(),
			"seconds_since_heartbeat": seconds_since,
			"healthy": is_healthy
		}
    
	async def _get_deployment_stats(self, hours: int = 24, **kwargs) -> Dict[str, Any]:
		"""Get deployment statistics"""
		jobs = await self.store.list_jobs()
		cutoff = datetime.now() - timedelta(hours=hours)
        
		recent_jobs = [j for j in jobs if j.created_at >= cutoff]
        
		total = len(recent_jobs)
		success = len([j for j in recent_jobs if j.status == JobStatus.SUCCESS])
		failed = len([j for j in recent_jobs if j.status == JobStatus.FAILED])
		running = len([j for j in recent_jobs if j.status == JobStatus.RUNNING])
		pending = len([j for j in recent_jobs if j.status == JobStatus.PENDING])
        
		return {
			"time_window_hours": hours,
			"total_deployments": total,
			"success": success,
			"failed": failed,
			"running": running,
			"pending": pending,
			"success_rate": (success / total * 100) if total > 0 else 0
		}
    
	async def _cancel_job(self, job_id: str, **kwargs) -> Dict[str, Any]:
		"""Cancel a job"""
		job = await self.store.get_job(job_id)
		if not job:
			return {"error": "Job not found"}
        
		if job.status in [JobStatus.SUCCESS, JobStatus.FAILED]:
			return {"error": "Job already completed"}
        
		# Update status to failed
		job.status = JobStatus.FAILED
		job.completed_at = datetime.now()
		await self.store.update_job(job)
        
		return {
			"success": True,
			"job_id": job_id,
			"message": "Job cancelled"
		}
    
	async def _get_recent_failures(self, limit: int = 5, **kwargs) -> Dict[str, Any]:
		"""Get recent failures"""
		jobs = await self.store.list_jobs()
		failed = [j for j in jobs if j.status == JobStatus.FAILED]
		failed = sorted(failed, key=lambda j: j.completed_at or j.created_at, reverse=True)[:limit]
        
		return {
			"count": len(failed),
			"failures": [
				{
					"id": j.id,
					"repository": j.repository,
					"ref": j.ref,
					"hostname": j.hostname,
					"failed_at": (j.completed_at or j.created_at).isoformat()
				}
				for j in failed
			]
		}
    
	async def _check_agent_health(self, **kwargs) -> Dict[str, Any]:
		"""Check agent health"""
		agents = await self.store.list_agents()
		now = datetime.now()
        
		healthy = []
		unhealthy = []
        
		for agent in agents:
			seconds_since = (now - agent.last_heartbeat).total_seconds()
			if seconds_since < 30:
				healthy.append(agent.hostname)
			else:
				unhealthy.append({
					"hostname": agent.hostname,
					"seconds_since_heartbeat": seconds_since
				})
        
		return {
			"total_agents": len(agents),
			"healthy_count": len(healthy),
			"unhealthy_count": len(unhealthy),
			"healthy_agents": healthy,
			"unhealthy_agents": unhealthy
		}
    
	async def _get_deployment_history(self, repository: Optional[str] = None, hostname: Optional[str] = None, **kwargs) -> Dict[str, Any]:
		"""Get deployment history"""
		jobs = await self.store.list_jobs()
        
		if repository:
			jobs = [j for j in jobs if j.repository == repository]
		if hostname:
			jobs = [j for j in jobs if j.hostname == hostname]
        
		jobs = sorted(jobs, key=lambda j: j.created_at, reverse=True)[:20]
        
		return {
			"count": len(jobs),
			"repository": repository,
			"hostname": hostname,
			"history": [
				{
					"id": j.id,
					"repository": j.repository,
					"ref": j.ref,
					"hostname": j.hostname,
					"status": j.status.value,
					"created_at": j.created_at.isoformat()
				}
				for j in jobs
			]
		}

	async def _start_workflow_action(self, workflow_name: str, context: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
		"""Start a workflow and return execution metadata"""
		response = await self.start_workflow(workflow_name, context or {})
		return response.model_dump(mode="json")

	async def _approve_workflow_step_action(
		self,
		workflow_id: str,
		approved: bool,
		user_input: Optional[str] = None,
		**kwargs
	) -> Dict[str, Any]:
		"""Approve or reject a workflow step"""
		response = await self.approve_step(workflow_id, approved, user_input)
		return response.model_dump(mode="json")

	async def _cancel_workflow_action(self, workflow_id: str, **kwargs) -> Dict[str, Any]:
		"""Cancel a workflow"""
		success = self.cancel_workflow(workflow_id)
		return {
			"workflow_id": workflow_id,
			"cancelled": success
		}

	async def _get_workflow_status_action(self, workflow_id: str, **kwargs) -> Dict[str, Any]:
		"""Get workflow status"""
		status = self.get_workflow_status(workflow_id)
		return status.model_dump(mode="json")

	async def _list_workflows_action(self, **kwargs) -> Dict[str, Any]:
		"""List active workflows"""
		workflows = self.list_workflows()
		return {
			"workflows": [workflow.model_dump(mode="json") for workflow in workflows]
		}

	async def _list_workflow_definitions_action(self, **kwargs) -> Dict[str, Any]:
		"""List workflow definitions"""
		definitions = []
		descriptions = {
			"register_agent": "Safely onboard a new deployment agent",
			"deploy_application": "Deploy an application with pre-flight checks",
			"troubleshoot_failure": "Diagnose and remediate failed deployments",
			"health_check": "Run a comprehensive system health check"
		}
		for name, steps in self.workflow_definitions.items():
			required_context = []
			if name == "register_agent":
				required_context = ["hostname"]
			elif name == "deploy_application":
				required_context = ["repository", "ref"]

			definitions.append({
				"name": name,
				"steps": len(steps),
				"description": descriptions.get(name, ""),
				"required_context": required_context
			})

		return {"workflows": definitions}
    
	async def _generate_suggestions(self, user_message: str, ai_response: str, action_taken: Optional[str], data: Optional[Dict]) -> List[str]:
		"""Generate contextual suggestions based on conversation"""
		suggestions = []
        
		# Check for active workflows first
		active_workflows = [w for w in self.workflows.values() if w.status == "running"]
		if active_workflows:
			workflow = active_workflows[0]
			current_step = workflow.steps[workflow.current_step_index] if workflow.current_step_index < len(workflow.steps) else None
            
			if current_step:
				if current_step.requires_approval:
					suggestions.extend([
						"✅ Yes, proceed",
						"❌ No, cancel",
						"⏸️ Skip this step"
					])
				elif current_step.requires_input and current_step.input_type == "choice":
					suggestions.extend(current_step.input_choices[:4] if current_step.input_choices else [])
				else:
					suggestions.extend([
						f"Continue {workflow.name}",
						"Show workflow status",
						"Cancel workflow"
					])
            
			return suggestions[:4]
        
		user_lower = user_message.lower()
        
		# Workflow trigger suggestions
		if any(word in user_lower for word in ["help", "guide", "how to", "need to", "want to"]):
			if "agent" in user_lower or "server" in user_lower or "add" in user_lower:
				suggestions.append("🚀 Register a new agent")
			if "deploy" in user_lower or "app" in user_lower:
				suggestions.append("📦 Deploy an application")
			if "fail" in user_lower or "broken" in user_lower or "error" in user_lower:
				suggestions.append("🔧 Troubleshoot failures")
			suggestions.append("💊 Run health check")
        
		# Context-based suggestions
		elif "agent" in user_lower or "host" in user_lower:
			suggestions.extend([
				"Show me deployment stats",
				"List all jobs",
				"Check for failures"
			])
		elif "job" in user_lower or "deploy" in user_lower:
			suggestions.extend([
				"Show running jobs",
				"Check recent failures",
				"View deployment history"
			])
		elif "stat" in user_lower or "metric" in user_lower:
			suggestions.extend([
				"Check agent health",
				"View last 24 hours",
				"Show success rate"
			])
		elif "fail" in user_lower or "error" in user_lower:
			suggestions.extend([
				"Show error logs",
				"List failed jobs",
				"Check agent connectivity"
			])
		else:
			# Default helpful suggestions with workflows
			suggestions.extend([
				"🚀 Register a new agent",
				"📦 Deploy an application",
				"Show all agents",
				"List recent jobs"
			])

		# Limit to 4 suggestions
		return suggestions[:4]
    
	def _check_needs_input(self, response: str) -> bool:
		"""Check if AI is asking for input from user"""
		question_indicators = [
			"which", "what", "please specify", "please provide",
			"can you provide", "could you specify", "need to know",
			"would you like", "do you want", "choose"
		]
		response_lower = response.lower()
		return any(indicator in response_lower for indicator in question_indicators) and "?" in response
    
	def _extract_input_prompt(self, response: str) -> str:
		"""Extract the question being asked"""
		# Find the last question in the response
		sentences = response.split(".")
		for sentence in reversed(sentences):
			if "?" in sentence:
				return sentence.strip()
		return "Please provide your input:"
    
	def _extract_quick_actions(self, response: str) -> List[Dict[str, str]]:
		"""Extract quick action buttons from AI response
        
		Looks for patterns like:
		- [✅ Yes, proceed] [❌ No, cancel]
		- Options: [Choice 1] [Choice 2]
		- [Button Text]
        
		Returns list of {label, action} dicts for rendering as buttons
		"""
		import re
        
		actions = []
        
		# Pattern 1: Look for text within square brackets (button format)
		# Matches: [✅ Yes, proceed] or [No, cancel]
		bracket_pattern = r'\[([^\]]+)\]'
		matches = re.findall(bracket_pattern, response)
        
		for match in matches:
			# Skip if it looks like a code reference or markdown link
			if match.startswith('http') or '(' in match or ')' in match:
				continue
            
			# Clean up the text (remove emojis for action, keep for label)
			label = match.strip()
			# Create action from label (lowercase, remove emojis and special chars)
			action = re.sub(r'[^\w\s-]', '', label).strip().lower().replace(' ', '_')
            
			if label and action:
				actions.append({
					"label": label,
					"action": action
				})
        
		# Limit to reasonable number of buttons
		return actions[:6]
    
	# ==================== WORKFLOW ENGINE ====================
    
	def _init_workflows(self) -> Dict[str, List[WorkflowStep]]:
		"""Initialize workflow definitions"""
		return {
			"register_agent": [
				WorkflowStep(
					id="get_hostname",
					title="Get Hostname",
					description="Request the hostname for the new agent",
					prompt="Ask the user for the hostname of the agent they want to register",
					requires_input=True,
					input_type="hostname",
					input_label="What's the hostname of the server you want to add?",
					input_placeholder="e.g., web-server-01",
					input_validation=r"^[a-zA-Z0-9\-\.]+$"
				),
				WorkflowStep(
					id="validate_hostname",
					title="Validate Hostname",
					description="Verify hostname format and check for duplicates",
					prompt="Validate that the hostname '{hostname}' is properly formatted and not already registered",
					requires_approval=False
				),
				WorkflowStep(
					id="select_environment",
					title="Select Environment",
					description="Choose the environment type for this agent",
					prompt="Ask user to select the environment",
					requires_input=True,
					input_type="choice",
					input_label="What environment will this agent serve?",
					input_choices=["production", "staging", "development", "qa"]
				),
				WorkflowStep(
					id="check_connectivity",
					title="Check Connectivity",
					description="Verify the agent can connect to the controller",
					prompt="Attempt to establish connection with host '{hostname}' and verify it can reach the controller",
					requires_approval=True
				),
				WorkflowStep(
					id="register",
					title="Register Agent",
					description="Add the agent to the database",
					prompt="Register agent '{hostname}' with the provided configuration",
					requires_approval=True
				),
				WorkflowStep(
					id="configure",
					title="Configure Agent",
					description="Set up agent environment and verify installation",
					prompt="Configure agent '{hostname}' with default settings and verify the installation is complete",
					requires_approval=False
				)
			],
			"deploy_application": [
				WorkflowStep(
					id="get_repository",
					title="Get Repository",
					description="Request repository details",
					prompt="Ask the user for the repository they want to deploy",
					requires_input=True,
					input_type="text",
					input_label="What repository would you like to deploy? (e.g., owner/repo)",
					input_placeholder="myorg/my-app"
				),
				WorkflowStep(
					id="get_ref",
					title="Get Git Reference",
					description="Request branch, tag, or commit",
					prompt="Ask the user for the git reference (branch, tag, or commit)",
					requires_input=True,
					input_type="text",
					input_label="Which branch, tag, or commit? (default: main)",
					input_placeholder="main"
				),
				WorkflowStep(
					id="select_agent",
					title="Select Target Agent",
					description="Choose deployment target",
					prompt="List available agents and ask the user to select one, or auto-select the best available agent based on health and availability.",
					requires_input=True,
					input_type="choice",
					input_label="Which server should host this deployment?"
				),
				WorkflowStep(
					id="validate_repository",
					title="Validate Repository",
					description="Check repository exists and ref is valid",
					prompt="Validate that repository '{repository}' exists and ref '{ref}' is valid",
					requires_approval=False
				),
				WorkflowStep(
					id="create_job",
					title="Create Deployment Job",
					description="Queue the deployment job",
					prompt="Create deployment job for {repository}@{ref} on agent {hostname}",
					requires_approval=True
				),
				WorkflowStep(
					id="monitor",
					title="Monitor Deployment",
					description="Watch deployment progress",
					prompt="Monitor the deployment job and report status",
					requires_approval=False
				)
			],
			"troubleshoot_failure": [
				WorkflowStep(
					id="identify_issue",
					title="Identify Issue",
					description="Analyze the failure",
					prompt="Analyze recent failures and identify the root cause. Check logs, agent status, and job history.",
					requires_approval=False
				),
				WorkflowStep(
					id="gather_logs",
					title="Gather Logs",
					description="Collect relevant logs and data",
					prompt="Gather logs and diagnostic information related to the identified issue",
					requires_approval=False
				),
				WorkflowStep(
					id="suggest_fix",
					title="Suggest Fix",
					description="Recommend remediation steps",
					prompt="Based on the logs and analysis, suggest specific steps to fix the issue",
					requires_approval=True
				),
				WorkflowStep(
					id="verify_fix",
					title="Verify Fix",
					description="Confirm issue is resolved",
					prompt="Verify that the suggested fix resolved the issue by checking system status",
					requires_approval=False
				)
			],
			"health_check": [
				WorkflowStep(
					id="check_agents",
					title="Check All Agents",
					description="Verify agent connectivity",
					prompt="Check the health status of all registered agents",
					requires_approval=False
				),
				WorkflowStep(
					id="check_jobs",
					title="Check Running Jobs",
					description="Review active deployments",
					prompt="List all running jobs and check for any stuck or failed deployments",
					requires_approval=False
				),
				WorkflowStep(
					id="analyze_metrics",
					title="Analyze Metrics",
					description="Review system performance",
					prompt="Analyze deployment metrics, success rates, and identify any patterns or issues",
					requires_approval=False
				),
				WorkflowStep(
					id="generate_report",
					title="Generate Report",
					description="Create health summary",
					prompt="Generate a comprehensive health report with recommendations",
					requires_approval=False
				)
			]
		}
    
	async def start_workflow(self, workflow_name: str, context: Dict[str, Any] = None) -> WorkflowResponse:
		"""Start a new workflow execution"""
		if workflow_name not in self.workflow_definitions:
			raise ValueError(f"Unknown workflow: {workflow_name}")
        
		# Create workflow instance
		workflow_id = f"{workflow_name}_{datetime.now().timestamp()}"
		steps = [WorkflowStep(**step.dict()) for step in self.workflow_definitions[workflow_name]]
        
		workflow = WorkflowState(
			id=workflow_id,
			name=workflow_name,
			description=f"Executing {workflow_name.replace('_', ' ').title()} workflow",
			steps=steps,
			context=context or {},
			started_at=datetime.now(),
			status="running"
		)
        
		self.workflows[workflow_id] = workflow
        
		# Execute first step
		return await self._execute_workflow_step(workflow_id)
    
	async def approve_step(self, workflow_id: str, approved: bool, user_input: str = None) -> WorkflowResponse:
		"""Approve or reject a workflow step"""
		if workflow_id not in self.workflows:
			raise ValueError(f"Unknown workflow: {workflow_id}")
        
		workflow = self.workflows[workflow_id]
		current_step = workflow.steps[workflow.current_step_index]
        
		if not approved:
			current_step.status = "failed"
			workflow.status = "failed"
			return WorkflowResponse(
				workflow_id=workflow_id,
				current_step=current_step,
				message=f"Workflow cancelled at step: {current_step.title}",
				completed=False,
				failed=True
			)
        
		# Add user input to context
		if user_input:
			workflow.context[f"step_{current_step.id}_input"] = user_input
        
		# Mark step as completed and move to next
		current_step.status = "completed"
		workflow.current_step_index += 1
        
		# Execute next step
		return await self._execute_workflow_step(workflow_id)
    
	async def _execute_workflow_step(self, workflow_id: str) -> WorkflowResponse:
		"""Execute the current workflow step"""
		workflow = self.workflows[workflow_id]
        
		# Check if workflow is complete
		if workflow.current_step_index >= len(workflow.steps):
			workflow.status = "completed"
			workflow.completed_at = datetime.now()
			return WorkflowResponse(
				workflow_id=workflow_id,
				message=f"Workflow '{workflow.name}' completed successfully!",
				completed=True,
				failed=False
			)
        
		current_step = workflow.steps[workflow.current_step_index]
		current_step.status = "in-progress"
        
		# Build prompt with context
		prompt = current_step.prompt
		for key, value in workflow.context.items():
			prompt = prompt.replace(f"{{{key}}}", str(value))
        
		# Build context message for AI
		context_msg = f"Workflow: {workflow.name}\nStep {workflow.current_step_index + 1}/{len(workflow.steps)}: {current_step.title}\n"
		if workflow.current_step_index > 0:
			context_msg += "\nPrevious steps results:\n"
			for i in range(workflow.current_step_index):
				prev_step = workflow.steps[i]
				if prev_step.result:
					context_msg += f"- {prev_step.title}: {prev_step.result.get('summary', 'completed')}\n"
        
		# Execute step using AI
		try:
			messages = [
				{"role": "system", "content": "You are executing a workflow step. Provide concise, actionable results."},
				{"role": "user", "content": context_msg + "\n" + prompt}
			]
            
			response = await self.client.chat.completions.create(
				model=self.model,
				messages=messages,
				functions=self.functions,
				function_call="auto"
			)
            
			message = response.choices[0].message
            
			# Handle function calls
			if message.function_call:
				function_name = message.function_call.name
				function_args = json.loads(message.function_call.arguments)
                
				# Execute the function
				function_map = {
					"list_agents": self._list_agents,
					"list_jobs": self._list_jobs,
					"get_job_details": self._get_job_details,
					"create_deployment": self._create_deployment,
					"get_deployment_stats": self._get_deployment_stats,
					"get_recent_failures": self._get_recent_failures,
					"get_deployment_history": self._get_deployment_history,
					"check_agent_health": self._check_agent_health
				}
                
				if function_name in function_map:
					result = await function_map[function_name](**function_args)
					current_step.result = result
                    
					# Get AI interpretation of result
					follow_up = await self.client.chat.completions.create(
						model=self.model,
						messages=messages + [
							{"role": "assistant", "content": None, "function_call": message.function_call},
							{"role": "function", "name": function_name, "content": json.dumps(result)}
						]
					)
                    
					step_message = follow_up.choices[0].message.content
				else:
					step_message = f"Function {function_name} not available"
			else:
				step_message = message.content
				current_step.result = {"summary": step_message}
            
			# Check if step requires approval
			if current_step.requires_approval:
				return WorkflowResponse(
					workflow_id=workflow_id,
					current_step=current_step,
					message=step_message,
					requires_approval=True,
					completed=False,
					failed=False
				)
			else:
				# Auto-approve and continue
				current_step.status = "completed"
				workflow.current_step_index += 1
				return await self._execute_workflow_step(workflow_id)
                
		except Exception as e:
			logger.error(f"Error executing workflow step: {e}")
			current_step.status = "failed"
			current_step.result = {"error": str(e)}
			workflow.status = "failed"
			return WorkflowResponse(
				workflow_id=workflow_id,
				current_step=current_step,
				message=f"Step failed: {str(e)}",
				completed=False,
				failed=True
			)
    
	def get_workflow_status(self, workflow_id: str) -> WorkflowState:
		"""Get current workflow status"""
		if workflow_id not in self.workflows:
			raise ValueError(f"Unknown workflow: {workflow_id}")
		return self.workflows[workflow_id]
    
	def list_workflows(self) -> List[WorkflowState]:
		"""List all active workflows"""
		return list(self.workflows.values())
    
	def cancel_workflow(self, workflow_id: str) -> bool:
		"""Cancel a running workflow"""
		if workflow_id not in self.workflows:
			return False
       
		workflow = self.workflows[workflow_id]
		workflow.status = "cancelled"
		if workflow.current_step_index < len(workflow.steps):
			workflow.steps[workflow.current_step_index].status = "skipped"
		return True

	async def enhance_launch_script(self, repo_url: str, ref: Optional[str], base_script: Optional[str]) -> Optional[str]:
		"""Refine an auto-generated launch script using the configured AI model"""
		if not base_script:
			return None
		if not self.client:
			return base_script
		system_prompt = textwrap.dedent(
			"""
			You are a senior DevOps engineer. Improve deployment launch scripts while keeping them safe,
			idempotent, and production ready. Only output the script content.
			"""
		)
		user_prompt = textwrap.dedent(
			f"""
			Repository: {repo_url}
			Reference: {ref or 'main'}
			Current script:
			```bash
			{base_script.strip()}
			```
			Provide an improved bash script. Do not add explanations outside of the code block.
			"""
		)
		try:
			response = await self.client.chat.completions.create(
				model=self.model,
				messages=[
					{"role": "system", "content": system_prompt},
					{"role": "user", "content": user_prompt},
				],
				max_tokens=600,
			)
			message = response.choices[0].message.content if response.choices else None
			if message:
				code = self._extract_code_block(message)
				if code:
					return code
				return message.strip()
		except Exception as exc:
			logger.debug("Launch script enhancement failed: %s", exc)
		return base_script

	async def generate_launch_script(self, repo_url: str, ref: Optional[str]) -> Optional[str]:
		"""Generate a conservative launch script when heuristics are unavailable"""
		if not self.client:
			return None
		system_prompt = textwrap.dedent(
			"""
			You are a DevOps assistant creating initial deployment scripts.
			If repository internals are unknown, produce a safe scaffold with TODOs.
			"""
		)
		user_prompt = textwrap.dedent(
			f"""
			Repository: {repo_url}
			Reference: {ref or 'main'}
			Provide a bash script that clones the repository, checks out the ref, and leaves TODO comments
			for dependency installation and app startup.
			"""
		)
		try:
			response = await self.client.chat.completions.create(
				model=self.model,
				messages=[
					{"role": "system", "content": system_prompt},
					{"role": "user", "content": user_prompt},
				],
				max_tokens=500,
			)
			message = response.choices[0].message.content if response.choices else None
			if message:
				code = self._extract_code_block(message)
				return code or message.strip()
		except Exception as exc:
			logger.debug("Launch script fallback generation failed: %s", exc)
		return None

	def _extract_code_block(self, text: str) -> Optional[str]:
		if not text or "```" not in text:
			return None
		segments = text.split("```")
		if len(segments) < 3:
			return None
		block = segments[1]
		if "\n" in block:
			first_line, remainder = block.split("\n", 1)
			if first_line.strip().lower() in {"bash", "sh", "shell"}:
				block = remainder
		return block.strip()
