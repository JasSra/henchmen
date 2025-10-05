"""
SSH Connector for Agentless Deployments

This module provides SSH-based deployment capabilities, allowing the controller
to deploy applications without requiring a persistent agent on the target host.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import asyncssh
from asyncssh import SSHClientConnection, SSHClientConnectionOptions

logger = logging.getLogger(__name__)


@dataclass
class SSHCredentials:
    """SSH connection credentials"""
    hostname: str
    port: int = 22
    username: str = "root"
    password: Optional[str] = None
    private_key: Optional[str] = None
    private_key_passphrase: Optional[str] = None


@dataclass
class DeploymentResult:
    """Result of a deployment operation"""
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0


class SSHConnector:
    """
    SSH-based connector for agentless deployments.
    
    Provides methods to:
    - Connect to remote hosts via SSH
    - Execute Docker commands remotely
    - Clone repositories
    - Deploy applications
    - Check health and metrics
    """
    
    def __init__(self, credentials: SSHCredentials):
        self.credentials = credentials
        self._connection: Optional[SSHClientConnection] = None
    
    async def connect(self) -> bool:
        """Establish SSH connection to the remote host"""
        try:
            logger.info(f"Connecting to {self.credentials.hostname}:{self.credentials.port}")
            
            options = SSHClientConnectionOptions(
                username=self.credentials.username,
                password=self.credentials.password,
                client_keys=[self.credentials.private_key] if self.credentials.private_key else None,
                known_hosts=None  # Accept any host key (for POC - should be configured properly in production)
            )
            
            self._connection = await asyncssh.connect(
                self.credentials.hostname,
                port=self.credentials.port,
                options=options
            )
            
            logger.info(f"✓ Connected to {self.credentials.hostname}")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to connect to {self.credentials.hostname}: {e}")
            return False
    
    async def disconnect(self):
        """Close SSH connection"""
        if self._connection:
            self._connection.close()
            await self._connection.wait_closed()
            self._connection = None
            logger.info(f"Disconnected from {self.credentials.hostname}")
    
    async def execute_command(self, command: str, timeout: int = 300) -> DeploymentResult:
        """
        Execute a command on the remote host
        
        Args:
            command: Command to execute
            timeout: Timeout in seconds
            
        Returns:
            DeploymentResult with output and status
        """
        if not self._connection:
            raise RuntimeError("Not connected. Call connect() first.")
        
        try:
            logger.info(f"Executing: {command}")
            
            result = await asyncio.wait_for(
                self._connection.run(command),
                timeout=timeout
            )
            
            success = result.exit_status == 0
            output = result.stdout if result.stdout else ""
            error = result.stderr if result.stderr else None
            
            if success:
                logger.info(f"✓ Command completed successfully")
            else:
                logger.warning(f"✗ Command failed with exit code {result.exit_status}")
            
            return DeploymentResult(
                success=success,
                output=output,
                error=error,
                exit_code=result.exit_status
            )
            
        except asyncio.TimeoutError:
            logger.error(f"Command timed out after {timeout} seconds")
            return DeploymentResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout} seconds",
                exit_code=-1
            )
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return DeploymentResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1
            )
    
    async def check_docker_installed(self) -> bool:
        """Check if Docker is installed on the remote host"""
        result = await self.execute_command("docker --version")
        return result.success
    
    async def get_docker_containers(self) -> List[Dict[str, Any]]:
        """Get list of Docker containers running on the remote host"""
        result = await self.execute_command("docker ps --format '{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}'")
        
        if not result.success:
            return []
        
        containers = []
        for line in result.output.strip().split('\n'):
            if line:
                parts = line.split('|')
                if len(parts) >= 4:
                    containers.append({
                        'id': parts[0],
                        'name': parts[1],
                        'status': parts[2],
                        'image': parts[3]
                    })
        
        return containers
    
    async def deploy_docker_image(self, image: str, container_name: str, 
                                  ports: Optional[Dict[int, int]] = None,
                                  env_vars: Optional[Dict[str, str]] = None) -> DeploymentResult:
        """
        Deploy a Docker container on the remote host
        
        Args:
            image: Docker image to deploy
            container_name: Name for the container
            ports: Port mappings (host_port: container_port)
            env_vars: Environment variables
            
        Returns:
            DeploymentResult
        """
        # Build docker run command
        cmd_parts = ["docker", "run", "-d", "--name", container_name]
        
        if ports:
            for host_port, container_port in ports.items():
                cmd_parts.extend(["-p", f"{host_port}:{container_port}"])
        
        if env_vars:
            for key, value in env_vars.items():
                cmd_parts.extend(["-e", f"{key}={value}"])
        
        cmd_parts.append(image)
        command = " ".join(cmd_parts)
        
        # Stop and remove existing container if it exists
        await self.execute_command(f"docker stop {container_name} 2>/dev/null || true")
        await self.execute_command(f"docker rm {container_name} 2>/dev/null || true")
        
        # Deploy new container
        return await self.execute_command(command)
    
    async def clone_repository(self, repo_url: str, ref: str = "main", 
                              work_dir: str = "/tmp/deploybot") -> DeploymentResult:
        """
        Clone a Git repository on the remote host
        
        Args:
            repo_url: Repository URL
            ref: Git reference (branch, tag, or commit)
            work_dir: Working directory for cloning
            
        Returns:
            DeploymentResult
        """
        # Create work directory
        await self.execute_command(f"mkdir -p {work_dir}")
        
        # Clone or update repository
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        repo_path = f"{work_dir}/{repo_name}"
        
        # Check if repo already exists
        check_result = await self.execute_command(f"[ -d {repo_path}/.git ] && echo exists || echo new")
        
        if "exists" in check_result.output:
            # Update existing repo
            logger.info(f"Updating existing repository at {repo_path}")
            await self.execute_command(f"cd {repo_path} && git fetch --all")
            return await self.execute_command(f"cd {repo_path} && git checkout {ref} && git pull origin {ref}")
        else:
            # Clone new repo
            logger.info(f"Cloning repository to {repo_path}")
            result = await self.execute_command(f"git clone {repo_url} {repo_path}")
            if result.success:
                return await self.execute_command(f"cd {repo_path} && git checkout {ref}")
            return result
    
    async def get_system_metrics(self) -> Dict[str, Any]:
        """Get system metrics from the remote host"""
        metrics = {}
        
        # CPU usage
        cpu_result = await self.execute_command(
            "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'"
        )
        if cpu_result.success:
            try:
                metrics['cpu_percent'] = float(cpu_result.output.strip())
            except ValueError:
                metrics['cpu_percent'] = 0.0
        
        # Memory usage
        mem_result = await self.execute_command(
            "free | grep Mem | awk '{print ($3/$2) * 100.0}'"
        )
        if mem_result.success:
            try:
                metrics['memory_percent'] = float(mem_result.output.strip())
            except ValueError:
                metrics['memory_percent'] = 0.0
        
        # Disk usage
        disk_result = await self.execute_command(
            "df -h / | tail -1 | awk '{print $4}'"
        )
        if disk_result.success:
            metrics['disk_free'] = disk_result.output.strip()
        
        return metrics
    
    async def execute_deployment(self, repo_url: str, ref: str, 
                                container_name: str) -> DeploymentResult:
        """
        Execute a full deployment workflow
        
        Args:
            repo_url: Repository URL
            ref: Git reference
            container_name: Container name
            
        Returns:
            DeploymentResult
        """
        # Check Docker is available
        if not await self.check_docker_installed():
            return DeploymentResult(
                success=False,
                output="",
                error="Docker is not installed on the remote host"
            )
        
        # Clone repository
        clone_result = await self.clone_repository(repo_url, ref)
        if not clone_result.success:
            return clone_result
        
        # Build Docker image (assuming Dockerfile exists)
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        work_dir = f"/tmp/deploybot/{repo_name}"
        
        build_result = await self.execute_command(
            f"cd {work_dir} && docker build -t {container_name}:latest ."
        )
        if not build_result.success:
            return build_result
        
        # Deploy container
        return await self.deploy_docker_image(
            f"{container_name}:latest",
            container_name,
            ports={8080: 8080}  # Default port mapping
        )


class SSHConnectionPool:
    """Pool of SSH connections for managing multiple hosts"""
    
    def __init__(self):
        self._connections: Dict[str, SSHConnector] = {}
    
    def add_host(self, hostname: str, credentials: SSHCredentials):
        """Add a host to the connection pool"""
        connector = SSHConnector(credentials)
        self._connections[hostname] = connector
    
    async def get_connector(self, hostname: str) -> Optional[SSHConnector]:
        """Get a connector for a specific host"""
        connector = self._connections.get(hostname)
        if connector and not connector._connection:
            await connector.connect()
        return connector
    
    async def disconnect_all(self):
        """Disconnect all SSH connections"""
        for connector in self._connections.values():
            await connector.disconnect()
        self._connections.clear()
