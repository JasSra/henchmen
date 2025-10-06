"""
Data models for DeployBot Controller (moved under controller/app)
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Literal, Union, Annotated
from pydantic import BaseModel, Field, field_validator, model_validator


class PortMapping(BaseModel):
	"""Port mapping configuration for deployments"""
	name: Optional[str] = Field(default=None, description="Friendly name for the port mapping")
	container_port: int = Field(..., description="Container/internal port")
	host_port: Optional[int] = Field(default=None, description="Host port to publish")
	protocol: str = Field(default="tcp", description="Transport protocol")
	publish_mode: str = Field(default="host", description="Publishing mode (host, ingress)")


class VolumeMapping(BaseModel):
	"""Volume mapping configuration for deployments"""
	source: str = Field(..., description="Host path or volume name")
	target: str = Field(..., description="Container mount path")
	read_only: bool = Field(default=False, description="Mount as read-only")


class EnvironmentVariable(BaseModel):
	"""Environment variable entry"""
	key: str
	value: str


class HealthCheckConfig(BaseModel):
	"""Service health check configuration"""
	type: Literal["http", "tcp", "command"] = "http"
	endpoint: Optional[str] = None
	expected_status: Optional[int] = Field(default=200, description="Expected status code for HTTP checks")
	command: Optional[List[str]] = None
	interval_seconds: int = Field(default=10)
	timeout_seconds: int = Field(default=5)
	retries: int = Field(default=3)


class ImageDeploymentSpec(BaseModel):
	"""Deployment spec for container images"""
	type: Literal["image"] = "image"
	image: str = Field(..., description="Image reference, optionally with tag")
	tag: Optional[str] = Field(default=None, description="Explicit tag override")
	command: Optional[str] = Field(default=None, description="Container command")
	entrypoint: Optional[str] = Field(default=None, description="Container entrypoint")
	workdir: Optional[str] = Field(default=None, description="Container working directory")
	environment: Dict[str, str] = Field(default_factory=dict)
	ports: List[PortMapping] = Field(default_factory=list)
	volumes: List[VolumeMapping] = Field(default_factory=list)
	restart_policy: Optional[str] = Field(default=None, description="Docker restart policy")
	health_check: Optional[HealthCheckConfig] = None

	@model_validator(mode="after")
	def ensure_tag(self):
		if self.tag:
			return self
		if ":" in self.image and not self.image.endswith(":"):
			return self
		return self


class RepoDeploymentSpec(BaseModel):
	"""Deployment spec for git repositories"""
	type: Literal["repo"] = "repo"
	repository: str = Field(..., description="Git repository (URL or owner/name)")
	ref: Optional[str] = Field(default="main", description="Git reference")
	launch_script: Optional[str] = Field(default=None, description="Script to launch the service")
	use_ai_launch: bool = Field(default=True, description="Allow AI assistant to propose launch script")
	environment: Dict[str, str] = Field(default_factory=dict)
	ports: List[PortMapping] = Field(default_factory=list)
	volumes: List[VolumeMapping] = Field(default_factory=list)
	compose_file: Optional[str] = None
	dockerfile: Optional[str] = None
	strategy: Optional[str] = Field(default=None, description="Override strategy detection")


DeploymentSpec = Annotated[Union[ImageDeploymentSpec, RepoDeploymentSpec], Field(discriminator="type")]


class JobStatus(str, Enum):
	"""Job execution status"""
	PENDING = "pending"
	RUNNING = "running"
	SUCCESS = "success"
	FAILED = "failed"
	CANCELLED = "cancelled"


class AgentStatus(str, Enum):
	"""Agent connection status"""
	ONLINE = "online"
	OFFLINE = "offline"


# Agent Models
class HostMetrics(BaseModel):
	"""Basic host metrics summary from agent"""
	cpu_percent: Optional[float] = None
	mem_percent: Optional[float] = None
	disk_free_gb: Optional[float] = None


class InventoryResource(BaseModel):
	"""Running container/process inventory item reported by agent"""
	name: str
	image: str
	ports: Dict[str, str] = Field(default_factory=dict)
	status: str
	health: Optional[str] = None


class AgentRegister(BaseModel):
	"""Agent registration request (accepts legacy and new agent payloads)"""
	hostname: str = Field(..., description="Agent hostname")
	capabilities: Dict[str, Any] = Field(default_factory=dict, description="Agent capabilities")
	# Optional fields that newer agents may send; ignored by controller for now
	token: Optional[str] = None
	docker_version: Optional[str] = None
	metrics: Optional[HostMetrics] = None

	@field_validator("capabilities", mode="before")
	@classmethod
	def normalize_capabilities(cls, v):
		if v is None:
			return {}
		if isinstance(v, list):
			# Convert list of capability names to a dict of {name: true}
			return {str(item): True for item in v}
		if isinstance(v, dict):
			return v
		raise TypeError("capabilities must be a dict or list")


class Agent(BaseModel):
	"""Agent entity with enhanced details"""
	id: str = Field(..., description="Unique agent ID")
	hostname: str = Field(..., description="Agent hostname")
	capabilities: Dict[str, Any] = Field(default_factory=dict)
	status: AgentStatus = Field(default=AgentStatus.ONLINE)
	registered_at: datetime = Field(default_factory=datetime.utcnow)
	last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
	
	# Enhanced host information
	os_info: Optional[Dict[str, Any]] = Field(default=None, description="Operating system details")
	hardware_info: Optional[Dict[str, Any]] = Field(default=None, description="Hardware specifications")
	network_info: Optional[Dict[str, Any]] = Field(default=None, description="Network configuration")
	docker_info: Optional[Dict[str, Any]] = Field(default=None, description="Docker daemon details")
	current_metrics: Optional[HostMetrics] = Field(default=None, description="Latest system metrics")
	uptime_seconds: Optional[int] = Field(default=None, description="System uptime in seconds")
	agent_version: Optional[str] = Field(default=None, description="Agent software version")
	tags: List[str] = Field(default_factory=list, description="User-defined tags for organization")
	
	# Communication metrics
	total_commands: int = Field(default=0, description="Total commands executed")
	successful_commands: int = Field(default=0, description="Successful commands")
	failed_commands: int = Field(default=0, description="Failed commands")
	last_command_at: Optional[datetime] = Field(default=None, description="Last command execution time")


class AgentRegisterResponse(BaseModel):
	"""Response returned to agent upon registration"""
	agent_id: str
	agent_token: str


class HeartbeatRequest(BaseModel):
	"""Heartbeat request from agent"""
	status: AgentStatus = Field(default=AgentStatus.ONLINE)
	metrics: Optional[HostMetrics] = None
	inventory: Optional[List[InventoryResource]] = None
	capabilities: Optional[Dict[str, Any]] = None

	@field_validator("capabilities", mode="before")
	@classmethod
	def normalize_hb_capabilities(cls, v):
		if v is None:
			return None
		if isinstance(v, list):
			return {str(item): True for item in v}
		if isinstance(v, dict):
			return v
		raise TypeError("capabilities must be a dict or list")


class HeartbeatResponse(BaseModel):
	"""Heartbeat response with optional job (agent-consumable)"""
	acknowledged: bool = True
	# Return a generic dict job to allow agent-specific schema {id,type,payload}
	job: Optional[Dict[str, Any]] = None


# Job Models
class JobCreate(BaseModel):
	"""Job creation request"""
	host: str = Field(..., description="Target host for deployment")
	job_type: str = Field(default="deploy", description="Job type (deploy, exec, restart, etc)")
	repo: Optional[str] = Field(default=None, description="Repository name (org/repo or URL)")
	ref: Optional[str] = Field(default=None, description="Git ref (branch, tag, or commit)")
	metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
	deployment_id: Optional[str] = Field(default=None, description="Reference to a saved deployment spec")
	deployment: Optional[DeploymentSpec] = Field(default=None, description="Inline deployment specification")
	strategy: Optional[str] = Field(default=None, description="Deployment strategy override")

	@model_validator(mode="after")
	def validate_payload(self):
		if self.job_type == "deploy":
			if any([self.deployment, self.deployment_id]):
				return self
			if not self.repo:
				raise ValueError("deploy jobs require repo or deployment spec")
		if not self.repo and self.job_type == "deploy":
			raise ValueError("repo is required when no deployment spec is provided")
		return self


class Job(BaseModel):
	"""Job entity with enhanced tracking"""
	id: str = Field(..., description="Unique job ID")
	job_type: str = Field(default="deploy", description="Job type")
	repo: Optional[str] = Field(default=None, description="Repository name")
	ref: Optional[str] = Field(default=None, description="Git ref")
	host: str = Field(..., description="Target host")
	status: JobStatus = Field(default=JobStatus.PENDING)
	metadata: Dict[str, Any] = Field(default_factory=dict)
	deployment_id: Optional[str] = Field(default=None, description="Linked deployment ID")
	deployment_spec: Optional[Dict[str, Any]] = Field(default=None, description="Inline deployment spec snapshot")
	created_at: datetime = Field(default_factory=datetime.utcnow)
	started_at: Optional[datetime] = None
	completed_at: Optional[datetime] = None
	assigned_agent: Optional[str] = None
	error: Optional[str] = None
	
	# Enhanced tracking
	tags: List[str] = Field(default_factory=list, description="User-defined tags")
	priority: int = Field(default=5, description="Job priority (1-10, higher = more priority)")
	retry_count: int = Field(default=0, description="Number of retry attempts")
	max_retries: int = Field(default=0, description="Maximum retry attempts")
	estimated_duration_seconds: Optional[int] = Field(default=None, description="Estimated completion time")
	actual_duration_seconds: Optional[int] = Field(default=None, description="Actual execution time")
	resource_usage: Optional[Dict[str, Any]] = Field(default=None, description="Resource consumption metrics")
	progress_percentage: Optional[int] = Field(default=None, description="Job completion percentage (0-100)")
	progress_message: Optional[str] = Field(default=None, description="Current progress description")


class JobResponse(BaseModel):
	"""Job response"""
	job: Job


class JobAckRequest(BaseModel):
	"""Job acknowledgement payload from agent"""
	status: str = Field(..., description="succeeded or failed")
	detail: Optional[Any] = None


# Host Models
class HostInfo(BaseModel):
	"""Host information"""
	hostname: str
	agent_id: Optional[str] = None
	agent_status: Optional[AgentStatus] = None
	last_seen: Optional[datetime] = None


class HostsResponse(BaseModel):
	"""Hosts list response"""
	hosts: List[HostInfo]


# GitHub Webhook Models
class GitHubRepository(BaseModel):
	"""GitHub repository in webhook payload"""
	full_name: str
	clone_url: str


class GitHubCommit(BaseModel):
	"""GitHub commit in webhook payload"""
	id: str
	message: str
	timestamp: str


class GitHubPushEvent(BaseModel):
	"""GitHub push event webhook payload"""
	ref: str  # refs/heads/main
	repository: GitHubRepository
	head_commit: GitHubCommit
	after: str  # commit SHA


class WebhookResponse(BaseModel):
	"""Webhook processing response"""
	received: bool = True
	jobs_created: List[str] = Field(default_factory=list)
	message: str = "Webhook processed"


# Log Models
class LogEntry(BaseModel):
	"""Log entry"""
	timestamp: datetime = Field(default_factory=datetime.utcnow)
	job_id: Optional[str] = None
	host: Optional[str] = None
	app: Optional[str] = None
	level: str = "INFO"
	message: str


class DeploymentRecord(BaseModel):
	"""Stored deployment definition"""
	id: str
	name: str
	kind: str
	spec: Dict[str, Any]
	description: Optional[str] = None
	tags: List[str] = Field(default_factory=list)
	created_at: datetime
	updated_at: datetime


class DeploymentCreate(BaseModel):
	"""Create deployment request"""
	name: str
	kind: Literal["image", "repo"]
	spec: DeploymentSpec
	description: Optional[str] = None
	tags: List[str] = Field(default_factory=list)

	@model_validator(mode="after")
	def ensure_kind_matches(self):
		spec_type = getattr(self.spec, "type", None)
		if spec_type and spec_type != self.kind:
			raise ValueError("spec type and kind must match")
		return self


class DeploymentUpdate(BaseModel):
	"""Update deployment request"""
	name: Optional[str] = None
	description: Optional[str] = None
	tags: Optional[List[str]] = None
	spec: Optional[DeploymentSpec] = None


class DeploymentCloneRequest(BaseModel):
	"""Clone deployment request payload"""
	name: Optional[str] = None


class CommandTemplate(BaseModel):
	"""Stored command template"""
	id: str
	name: str
	command: str
	description: Optional[str] = None
	tags: List[str] = Field(default_factory=list)
	is_system: bool = False
	runtime: Literal["shell", "python", "powershell"] = "shell"
	created_at: datetime
	updated_at: datetime


class DockerImageTemplate(BaseModel):
	"""Stored Docker image template for common applications"""
	id: str
	name: str
	image: str
	tag: str = "latest"
	description: Optional[str] = None
	category: str = Field(default="general", description="Template category (web, database, cache, etc.)")
	ports: List[PortMapping] = Field(default_factory=list)
	volumes: List[VolumeMapping] = Field(default_factory=list)
	environment: List[EnvironmentVariable] = Field(default_factory=list)
	health_check: Optional[HealthCheckConfig] = None
	is_system: bool = False
	usage_notes: Optional[str] = Field(default=None, description="Instructions for using this template")
	created_at: datetime
	updated_at: datetime


class CommandCreate(BaseModel):
	"""Create command template request"""
	name: str
	command: str
	description: Optional[str] = None
	tags: List[str] = Field(default_factory=list)
	runtime: Literal["shell", "python", "powershell"] = "shell"


class DockerImageTemplateCreate(BaseModel):
	"""Create Docker image template request"""
	name: str
	image: str
	tag: str = "latest"
	description: Optional[str] = None
	category: str = "general"
	ports: List[PortMapping] = Field(default_factory=list)
	volumes: List[VolumeMapping] = Field(default_factory=list)
	environment: List[EnvironmentVariable] = Field(default_factory=list)
	health_check: Optional[HealthCheckConfig] = None
	usage_notes: Optional[str] = None


class CommandUpdate(BaseModel):
	"""Update command template request"""
	name: Optional[str] = None
	command: Optional[str] = None
	description: Optional[str] = None
	tags: Optional[List[str]] = None
	runtime: Optional[Literal["shell", "python", "powershell"]] = None


class DockerImageTemplateUpdate(BaseModel):
	"""Update Docker image template request"""
	name: Optional[str] = None
	image: Optional[str] = None
	tag: Optional[str] = None
	description: Optional[str] = None
	category: Optional[str] = None
	ports: Optional[List[PortMapping]] = None
	volumes: Optional[List[VolumeMapping]] = None
	environment: Optional[List[EnvironmentVariable]] = None
	health_check: Optional[HealthCheckConfig] = None
	usage_notes: Optional[str] = None


class CommandRunRequest(BaseModel):
	"""Run command template on host"""
	host: str
	arguments: List[str] = Field(default_factory=list)
	environment: Dict[str, str] = Field(default_factory=dict)
	timeout_seconds: int = Field(default=300)
	working_dir: Optional[str] = None


class CommandRunResponse(BaseModel):
	"""Response after scheduling command run"""
	job: Job


class ToastNotification(BaseModel):
	"""Real-time toast notification"""
	id: str
	type: Literal["info", "success", "warning", "error"] = "info"
	title: str
	message: str
	agent_id: Optional[str] = None
	job_id: Optional[str] = None
	timestamp: datetime = Field(default_factory=datetime.utcnow)
	auto_dismiss: bool = Field(default=True, description="Auto-dismiss after timeout")
	timeout_seconds: int = Field(default=5, description="Auto-dismiss timeout")
	actions: List[Dict[str, str]] = Field(default_factory=list, description="Quick action buttons")


class AgentInteractionRequest(BaseModel):
	"""Request to send command or interact with agent"""
	command: str
	arguments: List[str] = Field(default_factory=list)
	environment: Dict[str, str] = Field(default_factory=dict)
	timeout_seconds: int = Field(default=30)
	expect_response: bool = Field(default=True, description="Wait for command response")


class AgentInteractionResponse(BaseModel):
	"""Response from agent interaction"""
	success: bool
	output: Optional[str] = None
	error: Optional[str] = None
	exit_code: Optional[int] = None
	execution_time_seconds: Optional[float] = None
	timestamp: datetime = Field(default_factory=datetime.utcnow)


# Update forward references
HeartbeatResponse.model_rebuild()
