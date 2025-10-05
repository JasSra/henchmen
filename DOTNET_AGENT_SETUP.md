# .NET Agent Setup Guide

## Overview

The DeployBot .NET Agent is a modern replacement for the Go agent, providing the same functionality with the .NET runtime. This guide covers both agent-based and agentless (SSH) deployment modes.

## Deployment Modes

DeployBot now supports two deployment modes:

### 1. Agent-Based Mode (Traditional)
A persistent .NET agent runs on the target server, polls the controller for jobs, and executes deployments locally.

**Pros:**
- Real-time job execution
- Better performance for frequent deployments
- Direct access to local Docker daemon

**Cons:**
- Requires agent installation on each target
- Agent must be kept running
- Requires network access from agent to controller

### 2. Agentless Mode (SSH-based) - **NEW**
The controller connects to target servers via SSH to execute deployments without requiring a persistent agent.

**Pros:**
- No agent installation required
- Works with any SSH-enabled server
- Simpler infrastructure management
- Better for ad-hoc deployments

**Cons:**
- Requires SSH access from controller to targets
- Slightly slower due to SSH connection overhead
- Requires SSH key management

## .NET Agent Installation

### Prerequisites

1. **.NET 9.0 Runtime** (or SDK for building from source)
   ```bash
   # Check if .NET is installed
   dotnet --version
   ```

2. **Docker** (for container deployments)
   ```bash
   docker --version
   ```

### Building the .NET Agent

```bash
# Build the agent
make build-dotnet-agent

# Or manually:
cd src/DeploybotAgent
dotnet build -c Release
```

### Configuration

Set environment variables (or create a `.env` file):

```bash
# Controller URL
export CONTROLLER_URL=http://localhost:8080

# Agent hostname (defaults to machine hostname)
export AGENT_HOSTNAME=my-server-01

# Heartbeat interval in seconds (default: 5)
export HEARTBEAT_INTERVAL=5
```

### Running the Agent

```bash
# Using make
make run-dotnet-agent

# Or manually
cd src/DeploybotAgent
dotnet run

# Or using the built binary
./bin/dotnet-agent/DeploybotAgent
```

### Production Deployment

```bash
# Publish the agent for production
make publish-dotnet-agent

# Copy to target server
scp -r bin/dotnet-agent user@target-server:/opt/deploybot/

# On target server, create systemd service
sudo cat > /etc/systemd/system/deploybot-agent.service <<EOF
[Unit]
Description=DeployBot .NET Agent
After=network.target docker.service

[Service]
Type=simple
User=deploybot
WorkingDirectory=/opt/deploybot/dotnet-agent
ExecStart=/usr/bin/dotnet /opt/deploybot/dotnet-agent/DeploybotAgent.dll
Restart=always
RestartSec=10
Environment="CONTROLLER_URL=http://controller:8080"
Environment="AGENT_HOSTNAME=$(hostname)"

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl enable deploybot-agent
sudo systemctl start deploybot-agent
sudo systemctl status deploybot-agent
```

## SSH-Based Agentless Deployment

### Prerequisites

1. **SSH access** from controller to target servers
2. **SSH key pair** (recommended over password auth)
3. **Docker** installed on target servers

### Setting Up SSH Keys

```bash
# On the controller, generate SSH key pair
ssh-keygen -t ed25519 -f ~/.ssh/deploybot_key -N ""

# Copy public key to target servers
ssh-copy-id -i ~/.ssh/deploybot_key.pub user@target-server

# Test SSH connection
ssh -i ~/.ssh/deploybot_key user@target-server "docker --version"
```

### Configuring SSH Deployment

Create a configuration file for your hosts:

```yaml
# config/ssh_hosts.yaml
hosts:
  - hostname: web-01.example.com
    deployment_mode: ssh
    ssh:
      port: 22
      username: deploybot
      private_key_path: ~/.ssh/deploybot_key
  
  - hostname: web-02.example.com
    deployment_mode: ssh
    ssh:
      port: 22
      username: deploybot
      private_key_path: ~/.ssh/deploybot_key
  
  # Or use agent-based for some hosts
  - hostname: web-03.example.com
    deployment_mode: agent
```

### SSH Deployment via API

```bash
# Deploy using SSH (direct API call)
curl -X POST http://localhost:8080/v1/deploy/ssh \
  -H "Content-Type: application/json" \
  -d '{
    "credentials": {
      "hostname": "web-01.example.com",
      "port": 22,
      "username": "deploybot",
      "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n..."
    },
    "repo_url": "https://github.com/myorg/myapp.git",
    "ref": "main",
    "container_name": "myapp"
  }'
```

### SSH Deployment via Python

```python
from app.ssh_connector import SSHConnector, SSHCredentials

# Create SSH credentials
credentials = SSHCredentials(
    hostname="web-01.example.com",
    username="deploybot",
    private_key="/path/to/key"
)

# Create connector and deploy
connector = SSHConnector(credentials)
await connector.connect()

result = await connector.execute_deployment(
    repo_url="https://github.com/myorg/myapp.git",
    ref="main",
    container_name="myapp"
)

print(f"Deployment {'succeeded' if result.success else 'failed'}")
print(result.output)

await connector.disconnect()
```

## Comparison: Go vs .NET Agent

| Feature | Go Agent | .NET Agent |
|---------|----------|------------|
| Runtime | Go binary (native) | .NET runtime required |
| Binary Size | ~15-20 MB | ~60-80 MB |
| Startup Time | <100ms | ~200-300ms |
| Memory Usage | ~15-30 MB | ~40-60 MB |
| Dependencies | None (static binary) | .NET runtime |
| Development | Go | C# |
| Docker Support | ✓ | ✓ |
| SSH Support | ✗ | ✓ (via agentless mode) |
| Cross-platform | ✓ | ✓ |

## Migration from Go Agent

### Step 1: Install .NET Runtime

On each target server:

```bash
# Ubuntu/Debian
wget https://dot.net/v1/dotnet-install.sh
chmod +x dotnet-install.sh
./dotnet-install.sh --channel 9.0

# Or use package manager
sudo apt-get update
sudo apt-get install -y dotnet-runtime-9.0
```

### Step 2: Stop Go Agent

```bash
# If running as systemd service
sudo systemctl stop deploybot-agent

# Or kill process
pkill deploybot-agent
```

### Step 3: Deploy .NET Agent

```bash
# Copy .NET agent to server
scp -r bin/dotnet-agent user@server:/opt/deploybot/

# Update systemd service (or create new one)
sudo nano /etc/systemd/system/deploybot-agent.service
# Update ExecStart to use dotnet command

# Restart service
sudo systemctl daemon-reload
sudo systemctl start deploybot-agent
```

### Step 4: Verify

```bash
# Check agent status
sudo systemctl status deploybot-agent

# Check logs
sudo journalctl -u deploybot-agent -f

# Test deployment
curl http://localhost:8080/v1/agents
```

## Alternative: Use Agentless Mode

Instead of migrating to .NET agent, you can use SSH-based agentless deployment:

```bash
# Stop Go agent
sudo systemctl stop deploybot-agent
sudo systemctl disable deploybot-agent

# Configure SSH access for controller
ssh-copy-id -i ~/.ssh/deploybot_key.pub user@server

# Update controller configuration to use SSH mode
# No agent needed on target server!
```

## Troubleshooting

### .NET Agent Won't Start

```bash
# Check .NET runtime
dotnet --version

# Check environment variables
env | grep CONTROLLER_URL

# Run in debug mode
cd src/DeploybotAgent
dotnet run
```

### SSH Connection Failed

```bash
# Test SSH connection manually
ssh -i ~/.ssh/deploybot_key user@target-server

# Check SSH key permissions
chmod 600 ~/.ssh/deploybot_key

# Enable SSH debug logging
ssh -vvv -i ~/.ssh/deploybot_key user@target-server
```

### Docker Not Available

```bash
# Check Docker is installed
docker --version

# Check current user has Docker access
docker ps

# Add user to docker group (then re-login)
sudo usermod -aG docker $USER
```

## Next Steps

- See `ARCHITECTURE.md` for system design
- See `QUICK_REFERENCE.md` for common commands
- See `WORKFLOWS.md` for deployment workflows
