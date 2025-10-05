# DeployBot Agent - Quick Setup Guide

## What is the Agent?

The DeployBot Agent is a Go application that runs on your deployment targets (servers/machines). It:
- Receives deployment jobs from the Controller
- Executes Docker deployments locally
- Reports health and metrics back
- Handles git repository cloning and Docker builds

## Prerequisites

### 1. Install Go

**Option A: Using the Install Script (Recommended)**
```bash
./install-go.sh
```

**Option B: Manual Installation**
1. Visit [https://go.dev/dl/](https://go.dev/dl/)
2. Download the macOS installer (.pkg file)
3. Run the installer
4. Verify: `go version`

**Option C: Using Homebrew** (if installed)
```bash
brew install go
```

### 2. Verify Installation
```bash
go version
# Should output: go version go1.22.x darwin/arm64 (or amd64)
```

## Building the Agent

```bash
# Install Go dependencies
make install-agent-deps

# Build the agent binary
make build-agent

# This creates: bin/deploybot-agent
```

## Configuration

Edit your `.env` file and set:

```bash
# Agent Configuration
AGENT_HOSTNAME=my-server-01
CONTROLLER_URL=http://localhost:8080
AGENT_DATA_DIR=./data/agent
AGENT_WORK_DIR=./data/agent/work

# Optional: Enable encryption
ENCRYPTION_KEY=your-32-character-encryption-key-here
```

## Running the Agent

### Development Mode (Interactive)
```bash
make run-agent
```

### Production Mode (Background)
```bash
# Start as background process
./bin/deploybot-agent &

# Or use nohup
nohup ./bin/deploybot-agent > agent.log 2>&1 &
```

### Docker Mode
```bash
# Build agent container
docker build -f Dockerfile.agent -t deploybot-agent .

# Run agent container
docker run -d \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e CONTROLLER_URL=http://host.docker.internal:8080 \
  -e AGENT_HOSTNAME=docker-agent-01 \
  --name deploybot-agent \
  deploybot-agent
```

## Agent Features

### 1. Job Execution
- Pulls code from Git repositories
- Builds Docker images
- Deploys containers
- Runs health checks

### 2. Health Reporting
- CPU, Memory, Disk metrics
- Docker container status
- Network connectivity

### 3. Security
- Optional state encryption
- Secure communication with Controller
- Audit logging

## Troubleshooting

### Go Not Found
```bash
# Add Go to PATH in ~/.zshrc or ~/.bash_profile
export PATH=$PATH:/usr/local/go/bin
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin

# Reload shell
source ~/.zshrc
```

### Build Errors
```bash
# Clean and rebuild
rm -rf bin/
make install-agent-deps
make build-agent
```

### Agent Won't Start
```bash
# Check logs
tail -f agent.log

# Verify Controller is running
curl http://localhost:8080/v1/status

# Check configuration
cat .env | grep AGENT
```

## Agent Commands

```bash
# Show all available commands
make help

# Install dependencies
make install-agent-deps

# Build agent
make build-agent

# Run agent
make run-agent

# Show setup instructions
make agent-help
```

## Architecture

```
┌─────────────────────┐
│   Controller        │  (Python FastAPI)
│   localhost:8080    │
└──────────┬──────────┘
           │ HTTP/WebSocket
           │
┌──────────▼──────────┐
│   Agent             │  (Go Application)
│   deploybot-agent   │
├─────────────────────┤
│ - Job Handler       │
│ - Docker Manager    │
│ - Git Client        │
│ - Metrics Collector │
│ - Health Reporter   │
└──────────┬──────────┘
           │
    ┌──────▼──────┐
    │   Docker    │
    │   Engine    │
    └─────────────┘
```

## Next Steps

1. Install Go: `./install-go.sh`
2. Build agent: `make build-agent`
3. Configure: Edit `.env`
4. Run agent: `make run-agent`
5. Register agent via UI: http://localhost:8080
6. Deploy your first application!

## Support

- See `WORKFLOWS.md` for workflow-based agent registration
- See `ARCHITECTURE.md` for system design
- Check logs in `data/agent/` directory
