"""
DeployBot Controller - FastAPI Application (moved under controller/)
"""
import os
import uuid
import asyncio
import asyncio.subprocess
import logging
import json
import textwrap
import tempfile
import shutil
import shlex
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Header, Response, File, UploadFile
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from app.models import (
	Agent,
	AgentRegister,
	AgentRegisterResponse,
	AgentStatus,
	HeartbeatRequest,
	HeartbeatResponse,
	Job,
	JobCreate,
	JobResponse,
	JobStatus,
	HostInfo,
	HostsResponse,
	GitHubPushEvent,
	WebhookResponse,
	LogEntry,
	JobAckRequest,
	DeploymentRecord,
	DeploymentCreate,
	DeploymentUpdate,
	DeploymentCloneRequest,
	PortMapping,
	VolumeMapping,
	HealthCheckConfig,
	ImageDeploymentSpec,
	RepoDeploymentSpec,
	DeploymentSpec,
	CommandTemplate,
	CommandCreate,
	CommandUpdate,
	CommandRunRequest,
	CommandRunResponse,
	DockerImageTemplate,
	ToastNotification,
	AgentInteractionRequest,
	AgentInteractionResponse,
)
from app.store import Store
from app.queue import JobQueue
from app.webhooks import WebhookHandler
from app.ai_assistant import AIAssistant, AIChatRequest, AIChatResponse, AIInsight, AIMessage

logger = logging.getLogger(__name__)


DEFAULT_LAUNCH_HEADER = "#!/bin/bash\nset -euo pipefail\n\n"


def normalize_repository_url(repo: str) -> str:
	"""Convert short repo notation to cloneable URL"""
	if not repo:
		return repo
	repo = repo.strip()
	if "://" in repo:
		return repo if repo.endswith(".git") else repo + ".git"
	base = repo.strip("/")
	if base.endswith(".git"):
		return f"https://github.com/{base}"
	return f"https://github.com/{base}.git"


def derive_name_from_repo(repo: Optional[str], metadata: Dict[str, Any]) -> str:
	"""Derive a friendly deployment name"""
	for key in ("name", "app", "service"):
		candidate = metadata.get(key)
		if isinstance(candidate, str) and candidate.strip():
			return candidate.strip()
	if not repo:
		return "deploy"
	base = repo.strip("/")
	if "/" in base:
		base = base.split("/")[-1]
	return base or "deploy"


def convert_ports_for_agent(ports: List[PortMapping]) -> List[Dict[str, Any]]:
	result: List[Dict[str, Any]] = []
	for idx, port in enumerate(ports):
		key = port.name or f"port-{port.container_port}-{idx}"
		published = "" if port.host_port is None else str(port.host_port)
		result.append({
			"key": key,
			"target": port.container_port,
			"published": published,
			"protocol": (port.protocol or "tcp").lower(),
		})
	return result


def convert_volumes_for_agent(volumes: List[VolumeMapping]) -> List[Dict[str, Any]]:
	result: List[Dict[str, Any]] = []
	for volume in volumes:
		entry = {"source": volume.source, "target": volume.target}
		if volume.read_only:
			entry["mode"] = "ro"
		result.append(entry)
	return result


def health_check_to_payload(health: Optional[HealthCheckConfig]) -> Optional[Dict[str, Any]]:
	if not health:
		return None
	payload = {
		"type": health.type,
		"endpoint": health.endpoint,
		"expected_status": health.expected_status,
		"interval_seconds": health.interval_seconds,
		"timeout_seconds": health.timeout_seconds,
		"retries": health.retries,
	}
	if health.command:
		payload["command"] = health.command
	return payload


def merge_metadata(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
	merged = dict(base)
	for key, value in overrides.items():
		if value is None:
			continue
		merged[key] = value
	return merged


def deployment_spec_to_metadata(spec: DeploymentSpec) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
	"""Convert deployment spec to job metadata"""
	metadata: Dict[str, Any] = {}
	if isinstance(spec, ImageDeploymentSpec):
		image_ref = spec.image
		if spec.tag and ":" not in image_ref:
			image_ref = f"{image_ref}:{spec.tag}"
		metadata["strategy"] = "image"
		metadata["image"] = image_ref
		image_base = image_ref.split("/")[-1].split(":")[0]
		metadata.setdefault("name", image_base or "image-deploy")
		if spec.environment:
			metadata["environment"] = dict(spec.environment)
		if spec.volumes:
			metadata["volumes"] = convert_volumes_for_agent(spec.volumes)
		if spec.ports:
			metadata["ports"] = convert_ports_for_agent(spec.ports)
		if spec.restart_policy:
			metadata["restart_policy"] = spec.restart_policy
		health_payload = health_check_to_payload(spec.health_check)
		if health_payload:
			metadata["health_check"] = health_payload
		if spec.workdir:
			metadata["workdir"] = spec.workdir
		if spec.command:
			metadata["container_command"] = spec.command
		if spec.entrypoint:
			metadata["container_entrypoint"] = spec.entrypoint
		return None, None, metadata

	if isinstance(spec, RepoDeploymentSpec):
		repo_url = normalize_repository_url(spec.repository)
		metadata["strategy"] = spec.strategy or "auto"
		metadata.setdefault("name", spec.repository.split("/")[-1] if spec.repository else "deploy")
		if spec.environment:
			metadata["environment"] = dict(spec.environment)
		if spec.volumes:
			metadata["volumes"] = convert_volumes_for_agent(spec.volumes)
		if spec.ports:
			metadata["ports"] = convert_ports_for_agent(spec.ports)
		if spec.compose_file:
			metadata["compose_file"] = spec.compose_file
		if spec.dockerfile:
			metadata["dockerfile"] = spec.dockerfile
		if spec.launch_script:
			metadata["launch_script"] = spec.launch_script
		metadata["use_ai_launch"] = spec.use_ai_launch
		health_payload = health_check_to_payload(None)
		if health_payload:
			metadata["health_check"] = health_payload
		return repo_url, spec.ref, metadata

	# Unknown spec type fallback
	return None, None, metadata


def deployment_record_to_spec(record: DeploymentRecord) -> DeploymentSpec:
	if record.kind == "image":
		return ImageDeploymentSpec.model_validate(record.spec)
	if record.kind == "repo":
		return RepoDeploymentSpec.model_validate(record.spec)
	raise ValueError(f"Unsupported deployment kind: {record.kind}")


async def plan_launch_script(repo_url: str, ref: Optional[str]) -> Optional[str]:
	"""Clone repository and derive launch script heuristically"""
	tmp_dir = tempfile.mkdtemp(prefix="deploybot-launch-")
	try:
		clone_cmd = ["git", "clone", "--depth", "1"]
		if ref:
			clone_cmd.extend(["--branch", ref])
		clone_cmd.extend([repo_url, tmp_dir])
		proc = await asyncio.create_subprocess_exec(
			*clone_cmd,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
		)
		stdout, stderr = await proc.communicate()
		if proc.returncode != 0:
			stderr_text = (stderr or b"").decode(errors="ignore")
			logger.warning("Failed to clone %s for launch script: %s", repo_url, stderr_text.strip())
			return None

		repo_path = Path(tmp_dir)
		script_body = detect_launch_script(repo_path)
		if not script_body:
			return None
		return DEFAULT_LAUNCH_HEADER + script_body.strip() + "\n"
	finally:
		shutil.rmtree(tmp_dir, ignore_errors=True)


def detect_launch_script(repo_path: Path) -> Optional[str]:
	"""Apply heuristics to derive repo launch script"""
	for detector in (_detect_compose_launch, _detect_node_launch, _detect_python_launch,
					_detect_go_launch, _detect_dotnet_launch, _detect_shell_launcher):
		script = detector(repo_path)
		if script:
			return script
	return None


def _detect_compose_launch(repo_path: Path) -> Optional[str]:
	for filename in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
		compose_file = repo_path / filename
		if compose_file.exists():
			return textwrap.dedent(f"""
			# Launch using Docker Compose
			docker compose -f {filename} pull
			docker compose -f {filename} up --build -d
			""")
	return None


def _detect_node_launch(repo_path: Path) -> Optional[str]:
	package_json = repo_path / "package.json"
	if not package_json.exists():
		return None
	try:
		package_data = json.loads(package_json.read_text(encoding="utf-8"))
	except Exception:
		package_data = {}
	start_script = None
	scripts = package_data.get("scripts") or {}
	for key in ("start", "dev", "serve"):
		val = scripts.get(key)
		if isinstance(val, str):
			start_script = key
			break
	manager = "npm"
	if (repo_path / "yarn.lock").exists():
		manager = "yarn"
	elif (repo_path / "pnpm-lock.yaml").exists():
		manager = "pnpm"
	install_cmd = {
		"npm": "npm install",
		"yarn": "yarn install",
		"pnpm": "pnpm install",
	}.get(manager, "npm install")
	if manager == "pnpm" and (repo_path / "pnpm-lock.yaml").exists():
		install_cmd = "pnpm install --frozen-lockfile"
	elif manager == "npm" and (repo_path / "package-lock.json").exists():
		install_cmd = "npm ci"
	start_cmd = {
		"npm": f"npm run {start_script}" if start_script else "npm start",
		"yarn": f"yarn {start_script}" if start_script else "yarn start",
		"pnpm": f"pnpm {start_script}" if start_script else "pnpm start",
	}[manager]
	return textwrap.dedent(f"""
	# Install dependencies and start Node.js service
	{install_cmd}
	{start_cmd}
	""")


def _detect_python_launch(repo_path: Path) -> Optional[str]:
	requirements = repo_path / "requirements.txt"
	pyproject = repo_path / "pyproject.toml"
	if not requirements and not pyproject:
		return None
	entry = None
	for candidate in ["manage.py", "app.py", "main.py"]:
		if (repo_path / candidate).exists():
			entry = candidate
			break
	venv_cmds = [
		"python -m venv .venv",
		"source .venv/bin/activate",
	]
	install_cmds: List[str] = []
	if requirements.exists():
		install_cmds.append("pip install -r requirements.txt")
	if pyproject.exists():
		install_cmds.append("pip install .")
	if not install_cmds:
		install_cmds.append("pip install -r requirements.txt")
	if entry == "manage.py":
		run_cmd = "python manage.py migrate && python manage.py runserver 0.0.0.0:8000"
	elif entry:
		run_cmd = f"python {entry}"
	else:
		run_cmd = "python -m app"
	commands = "\n".join(venv_cmds + install_cmds + [run_cmd])
	return textwrap.dedent(f"""
	# Bootstrap Python application
	{commands}
	""")


def _detect_go_launch(repo_path: Path) -> Optional[str]:
	go_mod = repo_path / "go.mod"
	if not go_mod.exists():
		return None
	return textwrap.dedent("""
	# Build and run Go service
	go mod tidy
	go build -o bin/app ./...
	./bin/app
	""")


def _detect_dotnet_launch(repo_path: Path) -> Optional[str]:
	csproj = list(repo_path.glob("**/*.csproj"))
	sln = list(repo_path.glob("*.sln"))
	if not csproj and not sln:
		return None
	return textwrap.dedent("""
	# Run .NET application
	dotnet restore
	dotnet build
	dotnet run
	""")


def _detect_shell_launcher(repo_path: Path) -> Optional[str]:
	for candidate in ["run.sh", "start.sh", "scripts/start.sh"]:
		script_path = repo_path / candidate
		if script_path.exists():
			return textwrap.dedent(f"""
		# Use provided launch script
		chmod +x {candidate}
		./{candidate}
		""")
	return textwrap.dedent("""
	# Fallback launch - customize as needed
	echo "Please provide a launch script or specify container strategy"
	""")


async def ensure_launch_script(metadata: Dict[str, Any], repo_url: str, ref: Optional[str], use_ai: bool) -> None:
	"""Populate launch script via AI/heuristics when missing"""
	if metadata.get("launch_script"):
		return
	if not use_ai:
		return
	script: Optional[str] = await plan_launch_script(repo_url, ref)
	if ai_assistant:
		try:
			refined = await ai_assistant.enhance_launch_script(repo_url, ref, script)
			if refined:
				script = refined
		except Exception as exc:
			logger.warning("AI launch script refinement failed: %s", exc)
	if not script and ai_assistant:
		try:
			script = await ai_assistant.generate_launch_script(repo_url, ref)
		except Exception as exc:
			logger.warning("AI launch script generation failed: %s", exc)
	if script:
		metadata["launch_script"] = script
		metadata.setdefault("launch_shell", "bash")
		metadata["launch_generated"] = True


def build_exec_metadata(template: CommandTemplate, request: CommandRunRequest) -> Dict[str, Any]:
	"""Prepare metadata payload for exec job"""
	arguments = request.arguments or []
	if template.runtime == "shell":
		quoted_args = " ".join(shlex.quote(arg) for arg in arguments)
		command_line = template.command
		if quoted_args:
			command_line = f"{command_line} {quoted_args}".strip()
		exec_command = ["bash", "-lc", command_line]
	elif template.runtime == "powershell":
		quoted_args = " ".join(arguments)
		command_script = template.command
		if quoted_args:
			command_script = f"{command_script} {quoted_args}".strip()
		exec_command = ["powershell", "-Command", command_script]
	elif template.runtime == "python":
		exec_command = ["python", "-c", template.command, *arguments]
	else:
		exec_command = ["bash", "-lc", template.command]

	metadata = {
		"command": exec_command,
		"environment": dict(request.environment or {}),
		"timeout_seconds": request.timeout_seconds,
		"command_template_id": template.id,
		"command_template_name": template.name,
		"command_runtime": template.runtime,
	}
	if template.description:
		metadata["command_description"] = template.description
	if arguments:
		metadata["command_arguments"] = arguments
	if request.working_dir:
		metadata["working_dir"] = request.working_dir
	return metadata
class Settings(BaseSettings):
	"""Application settings"""
	host: str = "0.0.0.0"
	port: int = 8080
	# default DB path under controller directory
	database_path: str = str(Path(__file__).resolve().parent.parent / "data" / "deploybot.db")
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
	config_path = Path(__file__).resolve().parent.parent / "config" / "apps.yaml"
	webhook_handler = WebhookHandler(
		secret=settings.github_webhook_secret,
		config_path=str(config_path)
	)
    
	# Initialize AI assistant if enabled and API key provided
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


# Mount static files for UI using path relative to controller directory
ui_dir = Path(__file__).resolve().parent.parent / "ui"
app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")


# UI Routes
@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def serve_ui():
	"""Serve the main UI dashboard (AI-enhanced if enabled)"""
	# Serve AI-enhanced UI if AI is enabled (even without valid API key for UI structure)
	# or if .env file exists indicating user wants AI features
	env_file_exists = Path(".env").exists()
	ui_file = ui_dir / ("index_ai.html" if (ai_assistant or env_file_exists) else "index.html")
	with open(ui_file, "r") as f:
		return HTMLResponse(content=f.read())


@app.get("/install.sh", response_class=Response, tags=["UI"])
async def serve_install_script(request: Request, token: str = None):
	"""Serve the enhanced agent installation script with auto-configuration"""
	print("DEBUG: serve_install_script function called!")
	
	# Read the template script
	script_path = ui_dir / "install.sh"
	print(f"DEBUG: Reading script from {script_path}")
	with open(script_path, "r", newline='') as f:
		script_content = f.read()

@app.get("/test-route", tags=["UI"])
async def test_route():
	"""Test route to check if routes are working"""
	return {"message": "Test route working!"}

@app.get("/install-enhanced.sh", response_class=Response, tags=["UI"])
async def serve_enhanced_install_script(request: Request, token: str = None):
	"""Serve the enhanced agent installation script with auto-configuration - TEST VERSION"""
	print("DEBUG: serve_enhanced_install_script function called!")
	
	# Read the template script
	script_path = ui_dir / "install.sh"
	print(f"DEBUG: Reading script from {script_path}")
	with open(script_path, "r", newline='') as f:
		script_content = f.read()
	
	# Normalize line endings to Unix format (LF only)
	script_content = script_content.replace('\r\n', '\n').replace('\r', '\n')
	
	# Auto-detect the controller URL from the request
	controller_url = f"{request.url.scheme}://{request.url.netloc}"
	print(f"DEBUG: Controller URL: {controller_url}")
	
	# Inject the controller URL and token into the script
	# This makes the script auto-configure when downloaded from the controller
	script_lines = script_content.split('\n')
	
	enhanced_script = '\n'.join(script_lines)
	
	# Add a header comment to show auto-configuration and set the URL directly
	header = f"""#!/bin/bash
# DeployBot Agent Auto-Install Script (Enhanced)
# Auto-configured for: {controller_url}
# Downloaded: {datetime.utcnow().isoformat()}Z
#
# Usage Examples:
#   curl -sSL {controller_url}/install.sh | bash
#   curl -sSL {controller_url}/install.sh | bash -s -- {controller_url}
#   curl -sSL {controller_url}/install.sh | bash -s -- {controller_url} <token>
#

# Auto-injected configuration
DEPLOYBOT_CONTROLLER_URL="{controller_url}"
"""
	
	# Add the token if provided
	if token:
		header += f'DEPLOYBOT_AGENT_TOKEN="{token}"\n'
	
	header += "\n"
	
	# Just replace the first shebang line, keep everything else
	lines = enhanced_script.split('\n')
	if lines[0].startswith('#!/bin/bash'):
		lines[0] = ''  # Remove original shebang, will be replaced by header
	
	final_script = header + '\n'.join(lines)
	
	return Response(
		content=final_script,
		media_type="text/x-shellscript",
		headers={
			"Content-Disposition": "attachment; filename=install.sh",
			"Cache-Control": "no-cache, no-store, must-revalidate",
			"Pragma": "no-cache",
			"Expires": "0"
        }
    )
	
	# Normalize line endings to Unix format (LF only)
	script_content = script_content.replace('\r\n', '\n').replace('\r', '\n')
	
	# Auto-detect the controller URL from the request
	controller_url = f"{request.url.scheme}://{request.url.netloc}"
	
	# Inject the controller URL and token into the script
	# This makes the script auto-configure when downloaded from the controller
	script_lines = script_content.split('\n')
	
	enhanced_script = '\n'.join(script_lines)
	
	# Add a header comment to show auto-configuration and set the URL directly
	header = f"""#!/bin/bash
# DeployBot Agent Auto-Install Script (Enhanced)
# Auto-configured for: {controller_url}
# Downloaded: {datetime.utcnow().isoformat()}Z
#
# Usage Examples:
#   curl -sSL {controller_url}/install.sh | bash
#   curl -sSL {controller_url}/install.sh | bash -s -- {controller_url}
#   curl -sSL {controller_url}/install.sh | bash -s -- {controller_url} <token>
#

# Auto-injected configuration
DEPLOYBOT_CONTROLLER_URL="{controller_url}"
"""
	
	# Add the token if provided
	if token:
		header += f'DEPLOYBOT_AGENT_TOKEN="{token}"\n'
	
	header += "\n"
	
	# Just replace the first shebang line, keep everything else
	lines = enhanced_script.split('\n')
	if lines[0].startswith('#!/bin/bash'):
		lines[0] = ''  # Remove original shebang, will be replaced by header
	
	final_script = header + '\n'.join(lines)
	
	return Response(
		content=final_script,
		media_type="text/x-shellscript",
		headers={
			"Content-Disposition": "attachment; filename=install.sh",
			"Cache-Control": "no-cache, no-store, must-revalidate",
			"Pragma": "no-cache",
			"Expires": "0"
        }
    )


@app.get("/install-cmd", tags=["UI"])
async def get_install_command(request: Request, token: Optional[str] = None):
	"""Generate a one-line install command for copying"""
	controller_url = f"{request.url.scheme}://{request.url.netloc}"
	
	if token:
		cmd = f"curl -sSL {controller_url}/install.sh | bash -s -- {controller_url} {token}"
	else:
		cmd = f"curl -sSL {controller_url}/install.sh | bash"
	
	return {
		"install_command": cmd,
		"controller_url": controller_url,
		"has_token": bool(token),
		"description": "Run this command on your server to install and connect a DeployBot agent"
	}


@app.get("/test-endpoint", tags=["UI"])
async def test_endpoint():
	"""Test endpoint to verify routing works"""
	return {"message": "Test endpoint works!", "timestamp": datetime.utcnow().isoformat()}


# Agent endpoints
@app.post("/v1/agents/register", response_model=AgentRegisterResponse, tags=["Agents"])
async def register_agent(agent_data: AgentRegister) -> AgentRegisterResponse:
	"""Register a new agent"""
	# Check if agent already exists by hostname
	existing_agent = await store.get_agent_by_hostname(agent_data.hostname)
    
	# Generate or reuse token (simple demo token since we don't yet enforce auth)
	def generate_token() -> str:
		return uuid.uuid4().hex

	token = generate_token()

	if existing_agent:
		# Update existing agent
		existing_agent.last_heartbeat = datetime.utcnow()
		existing_agent.status = AgentStatus.ONLINE
		existing_agent.capabilities = agent_data.capabilities
		await store.save_agent(existing_agent)
		return AgentRegisterResponse(agent_id=existing_agent.id, agent_token=token)
    
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
	return AgentRegisterResponse(agent_id=agent.id, agent_token=token)


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

		meta: Dict[str, Any] = dict(next_job.metadata or {})
		job_type = next_job.job_type or "deploy"

		if job_type == "deploy":
			ref_value = next_job.ref or meta.get("ref") or "main"
			name_value = derive_name_from_repo(next_job.repo, meta)
			payload: Dict[str, Any] = {"name": meta.get("name", name_value), "ref": ref_value}
			payload.update(meta)
			repo_value = next_job.repo or payload.get("repository") or payload.get("repository_url")
			strategy_val = str(payload.get("strategy", "")).lower()
			if strategy_val == "image" or payload.get("image"):
				payload.setdefault("strategy", "image")
			else:
				if repo_value:
					payload["repository_url"] = normalize_repository_url(str(repo_value))
			payload.setdefault("ref", ref_value)
			payload.pop("use_ai_launch", None)
			if next_job.deployment_id:
				payload.setdefault("deployment_id", next_job.deployment_id)
			agent_job = {
				"id": next_job.id,
				"type": "deploy",
				"payload": payload,
			}
		elif job_type == "exec":
			command_value = meta.get("command", [])
			if isinstance(command_value, list):
				exec_command = command_value
			elif isinstance(command_value, str):
				exec_command = ["bash", "-lc", command_value]
			else:
				exec_command = []
			command_payload = {
				"command": exec_command,
				"environment": meta.get("environment", {}),
				"timeout_seconds": meta.get("timeout_seconds", 300),
			}
			if meta.get("working_dir"):
				command_payload["working_dir"] = meta.get("working_dir")
			agent_job = {
				"id": next_job.id,
				"type": "exec",
				"payload": command_payload,
			}
		else:
			agent_job = {
				"id": next_job.id,
				"type": job_type,
				"payload": meta,
			}
		return HeartbeatResponse(acknowledged=True, job=agent_job)
    
	return HeartbeatResponse(acknowledged=True, job=None)


@app.post("/v1/agents/{agent_id}/jobs/{job_id}", tags=["Agents"])
async def ack_job(agent_id: str, job_id: str, payload: JobAckRequest):
	"""Agent acknowledges job completion"""
	job = await job_queue.get_job(job_id)
	if not job:
		raise HTTPException(status_code=404, detail="Job not found")
	# Update status based on ack
	if payload.status.lower() == "succeeded":
		job.status = JobStatus.SUCCESS
		job.completed_at = datetime.utcnow()
		job.error = None
	else:
		job.status = JobStatus.FAILED
		job.completed_at = datetime.utcnow()
		job.error = str(payload.detail) if payload.detail is not None else ""
	await store.save_job(job)
	return {"ok": True}


@app.post("/v1/agents/{agent_id}/jobs/{job_id}/logs", tags=["Agents"])
async def receive_logs(agent_id: str, job_id: str, request: Request):
	"""Receive streamed logs from agent for a job"""
	# Read raw text body
	try:
		body = await request.body()
		text = body.decode("utf-8", errors="replace")
	except Exception as e:
		raise HTTPException(status_code=400, detail=f"Failed to read log stream: {e}")

	# Save as a single log entry for now
	await store.save_log(LogEntry(job_id=job_id, host=agent_id, app="agent", level="INFO", message=text))
	return {"received": True}


# Job endpoints
@app.post("/v1/jobs", response_model=JobResponse, tags=["Jobs"], status_code=201)
async def create_job(job_data: JobCreate) -> JobResponse:
	"""Create a new deployment job"""
	metadata = dict(job_data.metadata or {})
	deployment_spec: Optional[DeploymentSpec] = None
	repo = job_data.repo
	ref = job_data.ref

	if job_data.job_type == "deploy":
		if job_data.deployment_id:
			record = await store.get_deployment(job_data.deployment_id)
			if not record:
				raise HTTPException(status_code=404, detail="Deployment not found")
			try:
				deployment_spec = deployment_record_to_spec(record)
			except ValueError as exc:
				raise HTTPException(status_code=400, detail=str(exc))
			metadata.setdefault("deployment_name", record.name)
			if record.tags:
				metadata.setdefault("deployment_tags", record.tags)
		elif job_data.deployment:
			deployment_spec = job_data.deployment

		if deployment_spec:
			repo_from_spec, ref_from_spec, spec_metadata = deployment_spec_to_metadata(deployment_spec)
			metadata = merge_metadata(spec_metadata, metadata)
			repo = repo or repo_from_spec
			ref = ref or ref_from_spec

		if job_data.strategy:
			metadata["strategy"] = job_data.strategy

		if deployment_spec and isinstance(deployment_spec, RepoDeploymentSpec):
			target_repo = repo or deployment_spec.repository
			if target_repo:
				repo_url = normalize_repository_url(target_repo)
				await ensure_launch_script(
					metadata,
					repo_url,
					ref or deployment_spec.ref,
					deployment_spec.use_ai_launch,
				)
			metadata.pop("use_ai_launch", None)

		strategy = metadata.get("strategy", "deploy")
		if strategy == "image":
			if not metadata.get("image"):
				raise HTTPException(status_code=400, detail="Image deployments require an image reference")
		else:
			if not repo:
				raise HTTPException(status_code=400, detail="Repository reference required for deployment job")
	else:
		if job_data.job_type == "exec" and not metadata.get("command"):
			raise HTTPException(status_code=400, detail="Exec jobs require command metadata")

	prepared_job = job_data.model_copy(
		update={
			"repo": repo,
			"ref": ref,
			"metadata": metadata,
			"deployment": deployment_spec,
		}
	)
	job = await job_queue.enqueue(prepared_job)
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


# Deployment endpoints
@app.get("/v1/deployments", response_model=List[DeploymentRecord], tags=["Deployments"])
async def list_deployments() -> List[DeploymentRecord]:
	return await store.list_deployments()


@app.post("/v1/deployments", response_model=DeploymentRecord, tags=["Deployments"], status_code=201)
async def create_deployment_endpoint(payload: DeploymentCreate) -> DeploymentRecord:
	spec_payload = payload.spec.model_dump(mode="json") if hasattr(payload.spec, "model_dump") else payload.spec
	return await store.create_deployment(
		name=payload.name,
		kind=payload.kind,
		spec=spec_payload,
		description=payload.description,
		tags=payload.tags,
	)


@app.get("/v1/deployments/{deployment_id}", response_model=DeploymentRecord, tags=["Deployments"])
async def get_deployment_endpoint(deployment_id: str) -> DeploymentRecord:
	record = await store.get_deployment(deployment_id)
	if not record:
		raise HTTPException(status_code=404, detail="Deployment not found")
	return record


@app.put("/v1/deployments/{deployment_id}", response_model=DeploymentRecord, tags=["Deployments"])
async def update_deployment_endpoint(deployment_id: str, payload: DeploymentUpdate) -> DeploymentRecord:
	spec_payload = None
	if payload.spec is not None:
		spec_payload = payload.spec.model_dump(mode="json") if hasattr(payload.spec, "model_dump") else payload.spec
	record = await store.update_deployment(
		deployment_id,
		name=payload.name,
		description=payload.description,
		tags=payload.tags,
		spec=spec_payload,
	)
	if not record:
		raise HTTPException(status_code=404, detail="Deployment not found")
	return record


@app.delete("/v1/deployments/{deployment_id}", status_code=204, tags=["Deployments"])
async def delete_deployment_endpoint(deployment_id: str) -> Response:
	await store.delete_deployment(deployment_id)
	return Response(status_code=204)


@app.post("/v1/deployments/{deployment_id}/clone", response_model=DeploymentRecord, tags=["Deployments"], status_code=201)
async def clone_deployment_endpoint(
	deployment_id: str,
	payload: DeploymentCloneRequest | None = None
) -> DeploymentRecord:
	record = await store.clone_deployment(deployment_id, name=payload.name if payload else None)
	if not record:
		raise HTTPException(status_code=404, detail="Deployment not found")
	return record


# Command library endpoints
@app.get("/v1/commands", response_model=List[CommandTemplate], tags=["Commands"])
async def list_command_templates(include_system: bool = True) -> List[CommandTemplate]:
	return await store.list_commands(include_system=include_system)


@app.post("/v1/commands", response_model=CommandTemplate, tags=["Commands"], status_code=201)
async def create_command_template(payload: CommandCreate) -> CommandTemplate:
	return await store.create_command(
		name=payload.name,
		command=payload.command,
		description=payload.description,
		tags=payload.tags,
		runtime=payload.runtime,
	)


@app.put("/v1/commands/{command_id}", response_model=CommandTemplate, tags=["Commands"])
async def update_command_template(command_id: str, payload: CommandUpdate) -> CommandTemplate:
	record = await store.update_command(
		command_id,
		name=payload.name,
		command=payload.command,
		description=payload.description,
		tags=payload.tags,
		runtime=payload.runtime,
	)
	if not record:
		raise HTTPException(status_code=404, detail="Command not found")
	return record


@app.delete("/v1/commands/{command_id}", status_code=204, tags=["Commands"])
async def delete_command_template(command_id: str) -> Response:
	await store.delete_command(command_id)
	return Response(status_code=204)


@app.post("/v1/commands/{command_id}/run", response_model=CommandRunResponse, tags=["Commands"], status_code=201)
async def run_command_template(command_id: str, payload: CommandRunRequest) -> CommandRunResponse:
	command_template = await store.get_command(command_id)
	if not command_template:
		raise HTTPException(status_code=404, detail="Command not found")

	command_metadata = build_exec_metadata(command_template, payload)
	job_request = JobCreate(
		host=payload.host,
		job_type="exec",
		repo=None,
		ref=None,
		metadata=command_metadata,
	)
	job = await job_queue.enqueue(job_request)
	return CommandRunResponse(job=job)


# Docker Template endpoints
@app.get("/v1/templates/docker", response_model=List[DockerImageTemplate], tags=["Templates"])
async def list_docker_templates(limit: int = 100, offset: int = 0) -> List[DockerImageTemplate]:
	"""List Docker image templates"""
	return await store.list_docker_templates(limit=limit, offset=offset)


@app.post("/v1/templates/docker", response_model=DockerImageTemplate, tags=["Templates"], status_code=201)
async def create_docker_template(template_data: dict) -> DockerImageTemplate:
	"""Create a new Docker template"""
	template = DockerImageTemplate(
		id=str(uuid.uuid4()),
		name=template_data["name"],
		image=template_data["image"],
		description=template_data.get("description", ""),
		ports=template_data.get("ports", []),
		volumes=template_data.get("volumes", []),
		environment=template_data.get("environment", {}),
		health_check=template_data.get("health_check", {}),
		tags=template_data.get("tags", []),
		is_system=False,
		created_at=datetime.utcnow(),
		updated_at=datetime.utcnow()
	)
	await store.save_docker_template(template)
	return template


@app.get("/v1/templates/docker/{template_id}", response_model=DockerImageTemplate, tags=["Templates"])
async def get_docker_template(template_id: str) -> DockerImageTemplate:
	"""Get a Docker template by ID"""
	template = await store.get_docker_template(template_id)
	if not template:
		raise HTTPException(status_code=404, detail="Template not found")
	return template


@app.put("/v1/templates/docker/{template_id}", response_model=DockerImageTemplate, tags=["Templates"])
async def update_docker_template(template_id: str, template_data: dict) -> DockerImageTemplate:
	"""Update a Docker template"""
	existing = await store.get_docker_template(template_id)
	if not existing:
		raise HTTPException(status_code=404, detail="Template not found")
	
	# Update fields
	existing.name = template_data.get("name", existing.name)
	existing.image = template_data.get("image", existing.image)
	existing.description = template_data.get("description", existing.description)
	existing.ports = template_data.get("ports", existing.ports)
	existing.volumes = template_data.get("volumes", existing.volumes)
	existing.environment = template_data.get("environment", existing.environment)
	existing.health_check = template_data.get("health_check", existing.health_check)
	existing.tags = template_data.get("tags", existing.tags)
	existing.updated_at = datetime.utcnow()
	
	await store.save_docker_template(existing)
	return existing


@app.delete("/v1/templates/docker/{template_id}", status_code=204, tags=["Templates"])
async def delete_docker_template(template_id: str) -> Response:
	"""Delete a Docker template"""
	deleted = await store.delete_docker_template(template_id)
	if not deleted:
		raise HTTPException(status_code=404, detail="Template not found or cannot delete system template")
	return Response(status_code=204)


# Agent Interaction endpoints
@app.post("/v1/agents/{agent_id}/interact", response_model=AgentInteractionResponse, tags=["Agents"])
async def interact_with_agent(agent_id: str, request: AgentInteractionRequest) -> AgentInteractionResponse:
	"""Send command to agent and get response"""
	agent = await store.get_agent(agent_id)
	if not agent:
		raise HTTPException(status_code=404, detail="Agent not found")
	
	if agent.status != AgentStatus.ONLINE:
		raise HTTPException(status_code=400, detail="Agent is not online")
	
	# Create a job for the interaction
	job_request = JobCreate(
		host=agent.hostname,
		job_type="exec",
		repo=None,
		ref=None,
		metadata={
			"command": request.command,
			"working_dir": request.working_dir,
			"environment": request.environment or {},
			"timeout": request.timeout or 30
		}
	)
	
	job = await job_queue.enqueue(job_request)
	
	# For now, return the job reference - in a full implementation,
	# we'd wait for completion or use WebSockets for real-time response
	return AgentInteractionResponse(
		request_id=request.request_id,
		job_id=job.id,
		status="submitted",
		output="",
		error="",
		exit_code=None
	)


# Notification endpoints
@app.get("/v1/notifications", response_model=List[ToastNotification], tags=["Notifications"])
async def list_notifications(
	agent_id: Optional[str] = None, 
	include_dismissed: bool = False, 
	limit: int = 50
) -> List[ToastNotification]:
	"""List notifications with optional filtering"""
	return await store.list_notifications(agent_id=agent_id, include_dismissed=include_dismissed, limit=limit)


@app.post("/v1/notifications", response_model=ToastNotification, tags=["Notifications"], status_code=201)
async def create_notification(notification_data: dict) -> ToastNotification:
	"""Create a new notification"""
	notification = ToastNotification(
		id=str(uuid.uuid4()),
		agent_id=notification_data.get("agent_id"),
		message=notification_data["message"],
		notification_type=notification_data.get("notification_type", "info"),
		is_dismissed=False,
		actions=notification_data.get("actions", []),
		auto_dismiss_after=notification_data.get("auto_dismiss_after"),
		created_at=datetime.utcnow()
	)
	await store.save_notification(notification)
	return notification


@app.put("/v1/notifications/{notification_id}/dismiss", tags=["Notifications"])
async def dismiss_notification(notification_id: str) -> dict:
	"""Mark a notification as dismissed"""
	dismissed = await store.dismiss_notification(notification_id)
	if not dismissed:
		raise HTTPException(status_code=404, detail="Notification not found")
	return {"status": "dismissed"}


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


@app.get("/v1/ai/status", tags=["AI Assistant"])
async def ai_status():
	"""Check AI assistant availability"""
	return {
		"enabled": ai_assistant is not None,
		"model": settings.ai_model if ai_assistant else None,
		"features": {
			"chat": ai_assistant is not None,
			"voice": ai_assistant is not None,
			"insights": ai_assistant is not None,
			"workflows": ai_assistant is not None
		}
	}


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


if __name__ == "__main__":
	import uvicorn
	uvicorn.run(
		"app.main:app",
		host=settings.host,
		port=settings.port,
		reload=True
	)


# Simple test endpoint added at the end
@app.get("/simple-test")
async def simple_test():
	return {"test": "working"}

