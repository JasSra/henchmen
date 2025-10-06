"""
Integration tests for DeployBot Controller
"""
import pytest
import httpx
import asyncio
import hmac
import hashlib
import json
from fastapi.testclient import TestClient

# Override settings before importing app
import os
os.environ['DATABASE_PATH'] = ':memory:'
os.environ['GITHUB_WEBHOOK_SECRET'] = 'test-secret-123'

from controller.app.main import app


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


class FakeAgent:
    """Fake agent for testing"""
    def __init__(self, client: TestClient, hostname: str):
        self.client = client
        self.hostname = hostname
        self.agent_id = None
    
    def register(self):
        """Register agent"""
        response = self.client.post(
            "/v1/agents/register",
            json={
                "hostname": self.hostname,
                "capabilities": {"platform": "linux"}
            }
        )
        assert response.status_code == 200
        data = response.json()
        # New API returns { agent_id, agent_token }
        assert "agent_id" in data and "agent_token" in data
        self.agent_id = data["agent_id"]
        return data
    
    def heartbeat(self):
        """Send heartbeat"""
        assert self.agent_id, "Agent must be registered first"
        response = self.client.post(
            f"/v1/agents/{self.agent_id}/heartbeat",
            json={"status": "online"}
        )
        assert response.status_code == 200
        return response.json()


def test_01_agent_registration_and_heartbeat(client):
    """Test 1: Agent registration and heartbeat with no jobs"""
    # Create fake agent
    agent = FakeAgent(client, "test-host-01.example.com")
    
    # Register agent
    agent_data = agent.register()
    assert "agent_id" in agent_data
    assert isinstance(agent_data["agent_id"], str)
    
    # Send heartbeat - should return no job
    heartbeat_response = agent.heartbeat()
    assert heartbeat_response["acknowledged"] is True
    assert heartbeat_response["job"] is None
    
    print("✓ Test 1 passed: Agent registration and heartbeat")


def test_02_job_creation_and_retrieval(client):
    """Test 2: Create a job and retrieve it"""
    # Create job
    job_data = {
        "repo": "myorg/test-app",
        "ref": "main",
        "host": "test-host-01.example.com",
        "metadata": {"trigger": "test"}
    }
    
    response = client.post("/v1/jobs", json=job_data)
    assert response.status_code == 201
    
    result = response.json()
    job = result["job"]
    job_id = job["id"]
    
    assert job["repo"] == "myorg/test-app"
    assert job["ref"] == "main"
    assert job["host"] == "test-host-01.example.com"
    assert job["status"] == "pending"
    
    # Retrieve job
    response = client.get(f"/v1/jobs/{job_id}")
    assert response.status_code == 200
    
    retrieved_job = response.json()["job"]
    assert retrieved_job["id"] == job_id
    assert retrieved_job["status"] == "pending"
    
    print(f"✓ Test 2 passed: Job created with ID {job_id}")


def test_03_agent_receives_job_on_heartbeat(client):
    """Test 3: Agent receives job on heartbeat"""
    # Create agent
    agent = FakeAgent(client, "test-host-02.example.com")
    agent.register()
    
    # Create job for this host
    job_data = {
        "repo": "myorg/webapp",
        "ref": "feature-branch",
        "host": "test-host-02.example.com",
        "metadata": {"trigger": "test"}
    }
    
    response = client.post("/v1/jobs", json=job_data)
    assert response.status_code == 201
    created_job_id = response.json()["job"]["id"]
    
    # Send heartbeat - should receive the job
    heartbeat_response = agent.heartbeat()
    assert heartbeat_response["acknowledged"] is True
    assert heartbeat_response["job"] is not None
    
    received_job = heartbeat_response["job"]
    assert received_job["id"] == created_job_id
    # New job shape for agent: { id, type, payload }
    assert received_job["type"] == "deploy"
    assert "payload" in received_job
    
    # Second heartbeat should return no job
    heartbeat_response2 = agent.heartbeat()
    assert heartbeat_response2["job"] is None
    
    print("✓ Test 3 passed: Agent received job on heartbeat")


def test_04_job_idempotency(client):
    """Test 4: Idempotency - duplicate job for same repo+ref+host is ignored if one is running"""
    # Create agent
    agent = FakeAgent(client, "test-host-03.example.com")
    agent.register()
    
    job_data = {
        "repo": "myorg/api-service",
        "ref": "abc123",
        "host": "test-host-03.example.com"
    }
    
    # Create first job
    response1 = client.post("/v1/jobs", json=job_data)
    assert response1.status_code == 201
    job1_id = response1.json()["job"]["id"]
    
    # Agent picks up the job (makes it running)
    heartbeat_response = agent.heartbeat()
    assert heartbeat_response["job"]["id"] == job1_id
    assert heartbeat_response["job"]["type"] == "deploy"
    
    # Try to create duplicate job (same repo+ref+host) while first is running
    response2 = client.post("/v1/jobs", json=job_data)
    assert response2.status_code == 201
    job2_id = response2.json()["job"]["id"]
    
    # Should return the same job (idempotency)
    assert job2_id == job1_id
    
    print("✓ Test 4 passed: Job idempotency works")


def test_05_github_webhook_integration(client):
    """Test 5: GitHub webhook creates deployment jobs"""
    # Create test webhook payload
    webhook_payload = {
        "ref": "refs/heads/main",
        "after": "abc123def456",
        "repository": {
            "full_name": "myorg/web-frontend",
            "clone_url": "https://github.com/myorg/web-frontend.git"
        },
        "head_commit": {
            "id": "abc123def456",
            "message": "Update deployment config",
            "timestamp": "2025-10-05T12:00:00Z"
        }
    }
    
    payload_bytes = json.dumps(webhook_payload).encode('utf-8')
    
    # Generate HMAC signature
    secret = "test-secret-123"
    mac = hmac.new(secret.encode('utf-8'), msg=payload_bytes, digestmod=hashlib.sha256)
    signature = f"sha256={mac.hexdigest()}"
    
    # Send webhook
    response = client.post(
        "/v1/webhooks/github",
        json=webhook_payload,
        headers={"X-Hub-Signature-256": signature}
    )
    
    assert response.status_code == 200
    result = response.json()
    
    assert result["received"] is True
    assert len(result["jobs_created"]) > 0
    
    # Verify jobs were created (based on config/apps.yaml)
    # web-frontend should deploy to web-01 and web-02
    jobs_created = result["jobs_created"]
    assert len(jobs_created) == 2  # Two hosts configured
    
    # Verify job details
    for job_id in jobs_created:
        job_response = client.get(f"/v1/jobs/{job_id}")
        assert job_response.status_code == 200
        job = job_response.json()["job"]
        assert job["repo"] == "myorg/web-frontend"
        assert job["ref"] == "abc123def456"
        assert job["host"] in ["web-01.example.com", "web-02.example.com"]
        assert job["metadata"]["trigger"] == "github_webhook"
    
    print(f"✓ Test 5 passed: Webhook created {len(jobs_created)} deployment jobs")


def test_06_list_hosts(client):
    """Test 6: List registered hosts"""
    # Register a few agents
    agent1 = FakeAgent(client, "host-a.example.com")
    agent2 = FakeAgent(client, "host-b.example.com")
    
    agent1.register()
    agent2.register()
    
    # List hosts
    response = client.get("/v1/hosts")
    assert response.status_code == 200
    
    result = response.json()
    hosts = result["hosts"]
    
    assert len(hosts) >= 2
    hostnames = [h["hostname"] for h in hosts]
    assert "host-a.example.com" in hostnames
    assert "host-b.example.com" in hostnames
    
    print("✓ Test 6 passed: List hosts endpoint works")


def test_07_invalid_webhook_signature(client):
    """Test 7: Webhook with invalid signature is rejected"""
    webhook_payload = {
        "ref": "refs/heads/main",
        "repository": {"full_name": "myorg/test"},
        "head_commit": {"id": "abc", "message": "test", "timestamp": "2025-10-05T12:00:00Z"}
    }
    
    # Send webhook with invalid signature
    response = client.post(
        "/v1/webhooks/github",
        json=webhook_payload,
        headers={"X-Hub-Signature-256": "sha256=invalid"}
    )
    
    assert response.status_code == 401
    
    print("✓ Test 7 passed: Invalid webhook signature rejected")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
