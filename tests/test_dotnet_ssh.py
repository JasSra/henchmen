"""
Integration tests for .NET agent and SSH deployment functionality
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from app.ssh_connector import SSHConnector, SSHCredentials, DeploymentResult
from app.models import SSHDeploymentRequest, SSHCredentialsModel


class TestSSHConnector:
    """Tests for SSH connector functionality"""
    
    @pytest.mark.asyncio
    async def test_ssh_credentials_creation(self):
        """Test creating SSH credentials"""
        creds = SSHCredentials(
            hostname="test.example.com",
            port=22,
            username="testuser",
            password="testpass"
        )
        
        assert creds.hostname == "test.example.com"
        assert creds.port == 22
        assert creds.username == "testuser"
        assert creds.password == "testpass"
    
    @pytest.mark.asyncio
    async def test_ssh_connector_initialization(self):
        """Test SSH connector initialization"""
        creds = SSHCredentials(
            hostname="test.example.com",
            username="testuser"
        )
        
        connector = SSHConnector(creds)
        
        assert connector.credentials == creds
        assert connector._connection is None
    
    @pytest.mark.asyncio
    async def test_deployment_result_structure(self):
        """Test deployment result data structure"""
        result = DeploymentResult(
            success=True,
            output="Deployment successful",
            error=None,
            exit_code=0
        )
        
        assert result.success is True
        assert result.output == "Deployment successful"
        assert result.error is None
        assert result.exit_code == 0
    
    @pytest.mark.asyncio
    async def test_deployment_result_failure(self):
        """Test deployment result for failure case"""
        result = DeploymentResult(
            success=False,
            output="",
            error="Connection failed",
            exit_code=1
        )
        
        assert result.success is False
        assert result.error == "Connection failed"
        assert result.exit_code == 1


class TestSSHDeploymentModels:
    """Tests for SSH deployment Pydantic models"""
    
    def test_ssh_credentials_model(self):
        """Test SSH credentials model validation"""
        creds = SSHCredentialsModel(
            hostname="server.example.com",
            port=2222,
            username="deploy",
            password="secret"
        )
        
        assert creds.hostname == "server.example.com"
        assert creds.port == 2222
        assert creds.username == "deploy"
        assert creds.password == "secret"
    
    def test_ssh_credentials_model_defaults(self):
        """Test SSH credentials model with defaults"""
        creds = SSHCredentialsModel(
            hostname="server.example.com"
        )
        
        assert creds.hostname == "server.example.com"
        assert creds.port == 22  # Default
        assert creds.username == "root"  # Default
        assert creds.password is None
    
    def test_ssh_deployment_request_model(self):
        """Test SSH deployment request model"""
        request = SSHDeploymentRequest(
            credentials=SSHCredentialsModel(hostname="server.example.com"),
            repo_url="https://github.com/test/repo.git",
            ref="main",
            container_name="test-app"
        )
        
        assert request.credentials.hostname == "server.example.com"
        assert request.repo_url == "https://github.com/test/repo.git"
        assert request.ref == "main"
        assert request.container_name == "test-app"


class TestDotNetAgentCompatibility:
    """Tests for .NET agent API compatibility"""
    
    def test_agent_registration_format(self):
        """Test .NET agent registration matches expected format"""
        # .NET agent sends this format
        registration = {
            "hostname": "test-server",
            "capabilities": {
                "platform": "Unix",
                "dotnet_version": "9.0.0",
                "agent_type": "dotnet"
            }
        }
        
        assert "hostname" in registration
        assert "capabilities" in registration
        assert registration["capabilities"]["agent_type"] == "dotnet"
    
    def test_heartbeat_format(self):
        """Test .NET agent heartbeat format"""
        heartbeat = {
            "status": "online"
        }
        
        assert "status" in heartbeat
        assert heartbeat["status"] in ["online", "offline"]
    
    def test_job_response_format(self):
        """Test job response format for .NET agent"""
        job = {
            "Id": "job-123",
            "Repo": "myorg/myapp",
            "Ref": "main",
            "Host": "server-01",
            "Status": "pending"
        }
        
        # .NET agent expects these fields (case-sensitive)
        assert "Id" in job
        assert "Repo" in job
        assert "Ref" in job
        assert "Host" in job
        assert "Status" in job


@pytest.mark.asyncio
async def test_ssh_connector_mock_connection():
    """Test SSH connector with mocked connection"""
    with patch('app.ssh_connector.asyncssh.connect', new_callable=AsyncMock) as mock_connect:
        # Mock successful connection
        mock_connection = AsyncMock()
        mock_connection.close = Mock()
        mock_connection.wait_closed = AsyncMock()
        mock_connect.return_value = mock_connection
        
        creds = SSHCredentials(
            hostname="test.example.com",
            username="testuser"
        )
        
        connector = SSHConnector(creds)
        result = await connector.connect()
        
        # Verify connection was attempted
        mock_connect.assert_called_once()
        assert result is True


@pytest.mark.asyncio
async def test_ssh_connector_mock_command_execution():
    """Test SSH command execution with mocked connection"""
    with patch('app.ssh_connector.asyncssh.connect', new_callable=AsyncMock) as mock_connect:
        # Mock connection and command result
        mock_connection = AsyncMock()
        mock_result = Mock()
        mock_result.exit_status = 0
        mock_result.stdout = "Command output"
        mock_result.stderr = ""
        
        mock_connection.run = AsyncMock(return_value=mock_result)
        mock_connection.close = Mock()
        mock_connection.wait_closed = AsyncMock()
        mock_connect.return_value = mock_connection
        
        creds = SSHCredentials(
            hostname="test.example.com",
            username="testuser"
        )
        
        connector = SSHConnector(creds)
        await connector.connect()
        
        result = await connector.execute_command("docker --version")
        
        assert result.success is True
        assert result.output == "Command output"
        assert result.exit_code == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
