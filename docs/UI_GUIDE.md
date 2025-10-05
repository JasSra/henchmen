# DeployBot UI Guide

## Quick Start

### 1. Start the Controller with UI

```bash
make run-ui
```

This will:
- Start the FastAPI controller on port 8080
- Automatically open the UI in your default browser
- Enable live reload for development

### 2. Access the Dashboard

Open your browser to: **http://localhost:8080**

## Dashboard Features

### 📊 Statistics Overview
- **Active Agents**: Number of currently connected agents
- **Pending Jobs**: Jobs waiting to be executed
- **Completed Jobs**: Successfully finished deployments

### 🚀 Quick Deploy
Trigger a manual deployment:
1. Enter repository (e.g., `myorg/web-app`)
2. Enter git reference (e.g., `main`, `v1.2.3`)
3. Enter target hostname (e.g., `web-01`)
4. Click **Deploy Now**

### 🤖 Connected Agents
Real-time list of all registered agents with:
- Hostname
- Agent version
- Last heartbeat timestamp
- Status indicator (green = healthy)

### 📋 Recent Jobs
View all deployment jobs with:
- Status badges (pending, running, success, failed)
- Repository and git reference
- Target host
- Timestamps
- Job IDs for tracking

### 🔄 Auto-Refresh
Dashboard updates every 5 seconds automatically.

## Installing Agents

### Option 1: One-Line Install (Recommended)

Copy the command from the UI dashboard and run on your target server:

```bash
curl -sSL http://localhost:8080/install.sh | bash -s -- http://localhost:8080
```

**What it does:**
- Auto-detects your operating system (macOS/Linux)
- Installs Python 3 if not present
- Creates `~/.deploybot` directory
- Writes agent configuration
- Creates system service (launchd/systemd)
- Starts the agent automatically
- Agent begins polling immediately

### Option 2: Manual Download

```bash
# Download the installer
curl -sSL http://localhost:8080/install.sh > install.sh
chmod +x install.sh

# Run with controller URL
./install.sh http://localhost:8080
```

### Option 3: Interactive Install

```bash
# Run without arguments - will prompt for controller URL
curl -sSL http://localhost:8080/install.sh | bash
```

## Agent Configuration

The installer creates: `~/.deploybot/config.yaml`

```yaml
controller_url: http://localhost:8080
hostname: my-server
poll_interval: 5
```

You can manually edit this file and restart the agent:

**macOS:**
```bash
launchctl stop com.deploybot.agent
launchctl start com.deploybot.agent
```

**Linux:**
```bash
sudo systemctl restart deploybot-agent
```

## Verifying Installation

### Check Agent Status

**In the UI:**
- Go to **Connected Agents** section
- Your hostname should appear within 5 seconds
- Status should show green indicator

**On the agent machine (macOS):**
```bash
launchctl list | grep deploybot
tail -f ~/.deploybot/agent.log
```

**On the agent machine (Linux):**
```bash
sudo systemctl status deploybot-agent
journalctl -u deploybot-agent -f
```

### Test a Deployment

1. In the UI, use the **Quick Deploy** form
2. Enter your repository, branch, and the agent's hostname
3. Click **Deploy Now**
4. Watch the job appear in **Recent Jobs**
5. Status should change: `pending` → `running` → `success`

## Troubleshooting

### Agent Not Appearing in UI

1. Check agent is running:
   ```bash
   # macOS
   launchctl list | grep deploybot
   
   # Linux
   sudo systemctl status deploybot-agent
   ```

2. Check agent logs:
   ```bash
   tail -f ~/.deploybot/agent.log
   ```

3. Verify controller URL in config:
   ```bash
   cat ~/.deploybot/config.yaml
   ```

4. Test connectivity:
   ```bash
   curl http://localhost:8080/v1/agents/register -X POST \
     -H "Content-Type: application/json" \
     -d '{"hostname":"test","version":"1.0.0"}'
   ```

### Jobs Stuck in Pending

- Verify the hostname in the job matches an active agent
- Check agent logs for errors
- Ensure agent has proper permissions to execute deployments

### UI Not Loading

1. Check controller is running:
   ```bash
   curl http://localhost:8080/
   ```

2. Verify port 8080 is not in use:
   ```bash
   lsof -i :8080
   ```

3. Check controller logs for errors

## API Endpoints (for advanced users)

The UI uses these REST endpoints:

- `GET /v1/agents` - List all agents
- `GET /v1/jobs` - List all jobs  
- `POST /v1/jobs` - Create new job
- `GET /v1/jobs/{job_id}/logs/stream` - Stream job logs (SSE)
- `POST /v1/webhooks/github` - GitHub webhook endpoint

See `/docs` for interactive API documentation (Swagger UI).

## GitHub Webhook Integration

### Configure in Repository Settings

1. Go to **Settings** → **Webhooks** → **Add webhook**
2. **Payload URL**: `http://your-controller:8080/v1/webhooks/github`
3. **Content type**: `application/json`
4. **Secret**: Your `GITHUB_WEBHOOK_SECRET` from `.env`
5. **Events**: Select "Just the push event"
6. Click **Add webhook**

### Configure Apps Mapping

Edit `config/apps.yaml`:

```yaml
applications:
  - repository: "myorg/web-app"
    hosts:
      - "web-01"
      - "web-02"
    deploy_on_push: true
    branches:
      - "main"
      - "production"
```

Now pushes to these branches will auto-deploy to the specified hosts!

## Security Notes

⚠️ **This MVP has no authentication** - Do not expose to the internet!

For production use:
- Add API authentication (JWT, API keys)
- Use HTTPS/TLS
- Implement RBAC
- Add audit logging
- Use secure secret management
- Network isolation (VPN, firewall rules)

## Next Steps

- Configure automatic deployments via GitHub webhooks
- Set up multiple agents across your infrastructure
- Create custom deployment scripts per application
- Monitor job success rates and deploy times
- Integrate with your CI/CD pipeline
