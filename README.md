# DeployBot Controller MVP

A lightweight deployment orchestration controller that manages deployment jobs across multiple hosts via agents or agentless SSH.

## ✨ Features

- 🤖 **AI Assistant** - Natural language commands, voice control, smart monitoring
- 🎨 **Web UI Dashboard** - Real-time monitoring and deployment controls
- 💡 **Smart Insights** - AI-powered health monitoring and proactive alerts
- 🎤 **Voice Commands** - Deploy and manage using speech (Whisper AI)
- 💬 **Chat Interface** - Ask questions and give commands in plain English
- 🔗 **GitHub Webhooks** - Automated deployments on push events
- 📊 **Real-time Logs** - SSE streaming for live deployment feedback
- 💾 **Job Queue** - SQLite persistence with in-memory processing
- 💻 **CLI Tool** - Manual deployments and log viewing
- 🚀 **One-Line Agent Install** - Auto-detects OS, installs dependencies, sets up service
- 🔒 **Hardened Agent Runtime** - HTTPS + cert pinning, encrypted state, policy enforcement, audit trail
- 🛠️ **Interactive First-Run Helper** - Guides operators through creating service accounts, Docker access, and TLS scaffolding
- 🆕 **.NET Agent** - Modern C# agent with token auth, TLS/mTLS, health metrics, state persistence
- 🆕 **Agentless SSH** - Deploy without installing agents using SSH connectivity

## 🚀 Quick Start

### Start the Controller with UI

```bash
# Install dependencies
make install

# Configure OpenAI API key (optional, for AI features)
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Run controller and open UI in browser
make run-ui
```

The UI will automatically open at **http://localhost:8080**

**With AI enabled**, you can:
- Click the 🤖 button to chat with the AI assistant
- Use voice commands by clicking the 🎤 microphone
- Get smart insights and proactive monitoring alerts
- Perform all tasks using natural language

## 📡 Deployment Modes

DeployBot now supports **two deployment modes**:

### 1. Agent-Based Deployment (Traditional)

Install a persistent .NET agent on target servers:

**Quick Install (Auto-configured Python Agent):**
```bash
curl -sSL http://localhost:8080/install.sh | bash -s -- http://localhost:8080
```

**Or Install .NET Agent:**
```bash
# Build .NET agent
make build-dotnet-agent

# Copy to target server and run
# See DOTNET_AGENT_SETUP.md for details
```

The agent will:
- Auto-detect your OS (macOS/Linux)
- Configure itself with your controller URL
- Create a system service (launchd/systemd)
- Start polling for jobs immediately

### 2. Agentless SSH Deployment (NEW)

Deploy without installing agents using SSH:

```bash
# Set up SSH keys
ssh-keygen -t ed25519 -f ~/.ssh/deploybot_key
ssh-copy-id -i ~/.ssh/deploybot_key.pub user@target-server

# Deploy via SSH API
curl -X POST http://localhost:8080/v1/deploy/ssh \
  -H "Content-Type: application/json" \
  -d '{
    "credentials": {
      "hostname": "target-server",
      "username": "deploybot",
      "private_key": "..."
    },
    "repo_url": "https://github.com/myorg/app.git",
    "ref": "main",
    "container_name": "myapp"
  }'
```

**Benefits of SSH Mode:**
- No agent installation required
- Works with any SSH-enabled server
- Simpler infrastructure management
- Perfect for ad-hoc deployments

### Deploy from the UI

1. Open http://localhost:8080
2. Use the **Quick Deploy** form
3. Enter: repository, git ref, target hostname
4. Click **Deploy Now**
5. Watch the job in **Recent Jobs** section

## 📚 Documentation

- **[DOTNET_AGENT_SETUP.md](DOTNET_AGENT_SETUP.md)** - .NET agent and SSH setup guide
- **[MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)** - Migrate from Go to .NET or SSH
- [UI Guide](docs/UI_GUIDE.md) - Dashboard features and agent installation
- [Quick Start](docs/QUICKSTART.md) - Getting started guide
- [Architecture](ARCHITECTURE.md) - System design and components (updated)
- [Agent Operations](docs/agent-usage.md) - Configuration, security controls, capability matrix
- [Deployment](docs/DEPLOYMENT.md) - Production deployment guide
- [Project Summary](docs/PROJECT_SUMMARY.md) - Complete feature overview

## 🎨 Web UI

The dashboard provides:

- **📊 Live Statistics** - Active agents, pending jobs, completion count
- **🚀 Quick Deploy** - One-click manual deployments
- **🤖 Agent Status** - Real-time agent health monitoring
- **📋 Job History** - All deployments with status badges
- **🔄 Auto-Refresh** - Updates every 5 seconds

## API Endpoints

- `GET /` - Web UI dashboard
- `GET /install.sh` - Agent installation script
- `POST /v1/agents/register` - Register a new agent
- `POST /v1/agents/{id}/heartbeat` - Agent heartbeat (receives jobs)
- `POST /v1/jobs` - Create a new job
- `GET /v1/jobs/{job_id}` - Get job details
- `GET /v1/hosts` - List all registered hosts
- `POST /v1/webhooks/github` - GitHub webhook endpoint
- `GET /v1/jobs/{job_id}/logs/stream` - SSE stream for logs

## CLI Usage

```bash
# Deploy manually
python -m cli.ctl deploy --repo myorg/web-frontend --ref main --host web-01

# View logs
python -m cli.ctl logs

# Check job status
python -m cli.ctl status <job-id>
```

## Configuration

Edit `config/apps.yaml` to configure repository-to-host mappings:

```yaml
applications:
  - repository: "myorg/web-app"
    hosts:
      - "web-01"
      - "web-02"
    deploy_on_push: true
    branches:
      - "main"
```

## Testing

```bash
make test
```

## Docker Deployment

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f
```

## Platform Support

- ✅ **macOS** (launchd service)
- ✅ **Linux** (systemd service)
- ✅ **Docker** (any platform)

## Agent Security & Capabilities

- Transport security is HTTPS by default with optional client certs and SHA256 pinning. Set `ALLOW_INSECURE_CONTROLLER=true` only for trusted, air-gapped testing.
- Agent credentials stored in `/var/lib/deploybot/agent.json` are AES-GCM encrypted when `AGENT_STATE_KEY` is supplied. Keys are transparently rotated on start.
- Optional policy gates:
  - `REGISTRY_ALLOWLIST` restricts container sources.
  - `REQUIRE_IMAGE_DIGEST=true` enforces digest-pinned deployments.
  - `ALLOWED_VOLUME_ROOTS` constrains bind mounts.
  - `CLEANUP_WORKSPACES=true` removes git worktrees after jobs.
- Audit log (`AUDIT_LOG_PATH`) records job lifecycle and cleanup events (JSONL).
- New opt-in capabilities `exec` and `query_env` are advertised to the controller yet require `ALLOW_UNSAFE_COMMANDS=true` (or full `SECURITY_BYPASS=true`).
- Capability discovery: the agent includes its supported verbs (`deploy`, `compose`, `logs`, `exec`, etc.) in both registration and heartbeat payloads so the controller can dynamically tailor job offerings.

## Security Note

⚠️ **This MVP has no authentication** - Do not expose to the internet without adding proper security!
