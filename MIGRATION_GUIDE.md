# Migration Guide: Go Agent to .NET Agent

## Overview

This guide provides step-by-step instructions for migrating from the Go-based DeployBot agent to either:
1. The new .NET agent
2. The agentless SSH-based deployment mode

Choose the migration path that best fits your infrastructure and requirements.

## Pre-Migration Checklist

Before migrating, ensure you have:

- [ ] Current Go agent version documented
- [ ] List of all servers running Go agents
- [ ] Backup of current agent configuration
- [ ] Test environment for validation
- [ ] Rollback plan documented
- [ ] Maintenance window scheduled (if needed)

## Migration Path 1: Go Agent → .NET Agent

### Advantages
- Similar architecture to Go agent
- Persistent agent for real-time deployments
- Better performance for frequent deployments
- Direct Docker access

### Step 1: Prerequisites

On each target server:

```bash
# Install .NET 9.0 Runtime
# Ubuntu/Debian
wget https://dot.net/v1/dotnet-install.sh
chmod +x dotnet-install.sh
./dotnet-install.sh --channel 9.0 --runtime dotnet

# Verify installation
dotnet --version
```

### Step 2: Build .NET Agent

On your development machine or CI server:

```bash
# Clone repository (if not already)
git clone https://github.com/JasSra/henchmen.git
cd henchmen

# Build .NET agent
make build-dotnet-agent

# Or build for production deployment
make publish-dotnet-agent
```

This creates the agent in `bin/dotnet-agent/`.

### Step 3: Deploy .NET Agent

Copy the agent to each target server:

```bash
# Create deployment directory
ssh user@target-server 'sudo mkdir -p /opt/deploybot && sudo chown $USER /opt/deploybot'

# Copy agent files
scp -r bin/dotnet-agent/* user@target-server:/opt/deploybot/

# Verify
ssh user@target-server 'ls -la /opt/deploybot/'
```

### Step 4: Configure .NET Agent

On each target server, create configuration:

```bash
ssh user@target-server

# Create environment file
cat > /opt/deploybot/.env <<EOF
CONTROLLER_URL=http://your-controller:8080
AGENT_HOSTNAME=$(hostname)
HEARTBEAT_INTERVAL=5
EOF
```

### Step 5: Create systemd Service

```bash
# On target server, create service file
sudo cat > /etc/systemd/system/deploybot-dotnet-agent.service <<EOF
[Unit]
Description=DeployBot .NET Agent
After=network.target docker.service

[Service]
Type=simple
User=deploybot
WorkingDirectory=/opt/deploybot
ExecStart=/usr/bin/dotnet /opt/deploybot/DeploybotAgent.dll
Restart=always
RestartSec=10
EnvironmentFile=/opt/deploybot/.env

[Install]
WantedBy=multi-user.target
EOF

# Note: Keep old Go agent service name different to avoid conflicts
```

### Step 6: Test .NET Agent (Without Stopping Go Agent)

```bash
# Start .NET agent
sudo systemctl enable deploybot-dotnet-agent
sudo systemctl start deploybot-dotnet-agent

# Check status
sudo systemctl status deploybot-dotnet-agent

# Check logs
sudo journalctl -u deploybot-dotnet-agent -f

# Verify agent registered with controller
curl http://your-controller:8080/v1/agents
```

### Step 7: Gradual Migration

Test deployments with the .NET agent before fully migrating:

```bash
# Deploy a test job to the .NET agent
curl -X POST http://your-controller:8080/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "myorg/test-app",
    "ref": "main",
    "host": "target-server"
  }'

# Monitor deployment
curl http://your-controller:8080/v1/jobs/{job-id}
```

### Step 8: Stop Go Agent and Switch Over

Once .NET agent is validated:

```bash
# Stop and disable Go agent
sudo systemctl stop deploybot-agent
sudo systemctl disable deploybot-agent

# Verify .NET agent is handling jobs
sudo journalctl -u deploybot-dotnet-agent -f
```

### Step 9: Cleanup (Optional)

After successful migration:

```bash
# Remove Go agent binary
sudo rm -f /usr/local/bin/deploybot-agent

# Remove Go agent service file
sudo rm -f /etc/systemd/system/deploybot-agent.service
sudo systemctl daemon-reload

# Remove Go-related files
rm -rf /opt/go
```

## Migration Path 2: Go Agent → Agentless SSH

### Advantages
- No agent installation required
- Simpler infrastructure
- Works with any SSH-enabled server
- Easier to manage at scale

### Step 1: Prerequisites

Ensure SSH access from controller to all target servers:

```bash
# On controller, generate SSH key pair
ssh-keygen -t ed25519 -f ~/.ssh/deploybot_key -N ""

# Copy to all target servers
for host in server1 server2 server3; do
    ssh-copy-id -i ~/.ssh/deploybot_key.pub user@$host
done

# Test SSH connection
ssh -i ~/.ssh/deploybot_key user@server1 "docker --version"
```

### Step 2: Configure SSH Credentials

Store SSH credentials securely. Options:

**Option A: Environment Variables (Simple)**

```bash
# On controller
export SSH_PRIVATE_KEY=$(cat ~/.ssh/deploybot_key)
export SSH_USERNAME=deploybot
```

**Option B: Configuration File**

Create `config/ssh_hosts.yaml`:

```yaml
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
```

### Step 3: Install SSH Support on Controller

```bash
# Install asyncssh library
pip install asyncssh==2.14.2

# Or use requirements.txt
pip install -r requirements.txt
```

### Step 4: Test SSH Deployment

```bash
# Test SSH deployment via API
curl -X POST http://localhost:8080/v1/deploy/ssh \
  -H "Content-Type: application/json" \
  -d '{
    "credentials": {
      "hostname": "web-01.example.com",
      "port": 22,
      "username": "deploybot",
      "private_key": "'"$(cat ~/.ssh/deploybot_key)"'"
    },
    "repo_url": "https://github.com/myorg/test-app.git",
    "ref": "main",
    "container_name": "test-app"
  }'
```

### Step 5: Stop Go Agents

Once SSH deployments are working:

```bash
# On each target server
sudo systemctl stop deploybot-agent
sudo systemctl disable deploybot-agent

# Verify agents stopped
for host in server1 server2 server3; do
    ssh user@$host "sudo systemctl status deploybot-agent"
done
```

### Step 6: Update Deployment Workflows

Update your deployment scripts/workflows to use SSH mode:

**Before (Agent-based):**
```bash
# Job created, agent picks it up via heartbeat
curl -X POST http://localhost:8080/v1/jobs \
  -d '{"repo": "myorg/app", "ref": "main", "host": "web-01"}'
```

**After (SSH-based):**
```bash
# Direct SSH deployment
curl -X POST http://localhost:8080/v1/deploy/ssh \
  -d '{
    "credentials": {...},
    "repo_url": "https://github.com/myorg/app.git",
    "ref": "main",
    "container_name": "app"
  }'
```

### Step 7: Cleanup

Remove Go agent files from target servers:

```bash
# On each target server
sudo rm -f /usr/local/bin/deploybot-agent
sudo rm -f /etc/systemd/system/deploybot-agent.service
sudo rm -rf /var/lib/deploybot
```

## Hybrid Approach (Recommended for Large Deployments)

You can use both modes simultaneously:

- **Critical/Production Servers**: Use .NET agents for real-time deployments
- **Development/Testing Servers**: Use SSH for ad-hoc deployments
- **Temporary Servers**: Use SSH (no agent installation needed)

Configuration example:

```yaml
# config/deployment_strategy.yaml
production:
  - hostname: prod-web-01
    mode: agent
    agent_type: dotnet
  - hostname: prod-web-02
    mode: agent
    agent_type: dotnet

staging:
  - hostname: staging-web-01
    mode: ssh
    ssh_username: deploybot

development:
  - hostname: dev-*
    mode: ssh
    ssh_username: developer
```

## Rollback Procedures

### If .NET Agent Migration Fails

```bash
# Restart Go agent
sudo systemctl start deploybot-agent
sudo systemctl status deploybot-agent

# Stop .NET agent
sudo systemctl stop deploybot-dotnet-agent
sudo systemctl disable deploybot-dotnet-agent
```

### If SSH Migration Fails

```bash
# Restart Go agents on all servers
for host in server1 server2 server3; do
    ssh user@$host "sudo systemctl start deploybot-agent"
done

# Verify
for host in server1 server2 server3; do
    ssh user@$host "sudo systemctl status deploybot-agent"
done
```

## Verification & Testing

### Verify .NET Agent

```bash
# Check agent registered
curl http://controller:8080/v1/agents | jq '.[] | select(.hostname=="your-server")'

# Test deployment
curl -X POST http://controller:8080/v1/jobs \
  -d '{"repo": "myorg/test", "ref": "main", "host": "your-server"}'

# Monitor logs
ssh user@your-server "sudo journalctl -u deploybot-dotnet-agent -f"
```

### Verify SSH Deployment

```bash
# Test SSH connectivity
curl -X POST http://controller:8080/v1/ssh/execute \
  -d '{
    "hostname": "your-server",
    "command": "docker ps",
    "credentials": {...}
  }'

# Test full deployment
curl -X POST http://controller:8080/v1/deploy/ssh \
  -d '{...}'
```

## Troubleshooting

### .NET Agent Issues

**Agent won't start:**
```bash
# Check .NET runtime
dotnet --version

# Check dependencies
ldd /opt/deploybot/DeploybotAgent.dll

# Run manually for debugging
cd /opt/deploybot
dotnet DeploybotAgent.dll
```

**Agent not registering:**
```bash
# Check network connectivity
curl http://controller:8080/v1/status

# Check environment variables
cat /opt/deploybot/.env

# Check logs
sudo journalctl -u deploybot-dotnet-agent -n 100
```

### SSH Deployment Issues

**SSH connection refused:**
```bash
# Test SSH manually
ssh -i ~/.ssh/deploybot_key user@server

# Check SSH service
ssh user@server "sudo systemctl status sshd"

# Check firewall
ssh user@server "sudo ufw status"
```

**Permission denied:**
```bash
# Check key permissions
ls -la ~/.ssh/deploybot_key  # Should be 600

# Check authorized_keys on server
ssh user@server "cat ~/.ssh/authorized_keys | grep deploybot"
```

## Support

- See `DOTNET_AGENT_SETUP.md` for detailed .NET agent setup
- See `ARCHITECTURE.md` for system architecture
- See `QUICK_REFERENCE.md` for common commands
- Check GitHub Issues for known problems
