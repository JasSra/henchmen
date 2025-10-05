"""
Data models for DeployBot Controller
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


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
class AgentRegister(BaseModel):
    """Agent registration request"""
    hostname: str = Field(..., description="Agent hostname")
    capabilities: Dict[str, Any] = Field(default_factory=dict, description="Agent capabilities")


class Agent(BaseModel):
    """Agent entity"""
    id: str = Field(..., description="Unique agent ID")
    hostname: str = Field(..., description="Agent hostname")
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    status: AgentStatus = Field(default=AgentStatus.ONLINE)
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)


class HeartbeatRequest(BaseModel):
    """Heartbeat request from agent"""
    status: AgentStatus = Field(default=AgentStatus.ONLINE)


class HeartbeatResponse(BaseModel):
    """Heartbeat response with optional job"""
    acknowledged: bool = True
    job: Optional["Job"] = None


# Job Models
class JobCreate(BaseModel):
    """Job creation request"""
    repo: str = Field(..., description="Repository name (org/repo)")
    ref: str = Field(..., description="Git ref (branch, tag, or commit)")
    host: str = Field(..., description="Target host for deployment")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class Job(BaseModel):
    """Job entity"""
    id: str = Field(..., description="Unique job ID")
    repo: str = Field(..., description="Repository name")
    ref: str = Field(..., description="Git ref")
    host: str = Field(..., description="Target host")
    status: JobStatus = Field(default=JobStatus.PENDING)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    assigned_agent: Optional[str] = None
    error: Optional[str] = None


class JobResponse(BaseModel):
    """Job response"""
    job: Job


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


# SSH Deployment Models
class SSHDeploymentMode(str, Enum):
    """Deployment mode"""
    AGENT = "agent"  # Use persistent agent
    SSH = "ssh"      # Use agentless SSH


class SSHCredentialsModel(BaseModel):
    """SSH credentials for agentless deployment"""
    hostname: str = Field(..., description="Target hostname")
    port: int = Field(default=22, description="SSH port")
    username: str = Field(default="root", description="SSH username")
    password: Optional[str] = Field(None, description="SSH password (use key auth when possible)")
    private_key: Optional[str] = Field(None, description="SSH private key content")
    private_key_passphrase: Optional[str] = Field(None, description="Private key passphrase")


class SSHDeploymentRequest(BaseModel):
    """SSH-based deployment request"""
    credentials: SSHCredentialsModel
    repo_url: str = Field(..., description="Repository URL to clone")
    ref: str = Field(default="main", description="Git reference (branch, tag, or commit)")
    container_name: str = Field(..., description="Container name to deploy")


class SSHDeploymentResponse(BaseModel):
    """SSH deployment response"""
    success: bool
    message: str
    output: Optional[str] = None
    error: Optional[str] = None


class HostConfigurationModel(BaseModel):
    """Host configuration for deployment"""
    hostname: str
    deployment_mode: SSHDeploymentMode = Field(default=SSHDeploymentMode.AGENT)
    ssh_credentials: Optional[SSHCredentialsModel] = None


# Update forward references
HeartbeatResponse.model_rebuild()
