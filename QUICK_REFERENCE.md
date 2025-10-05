# DeployBot Quick Reference Card

## 🚀 Quick Start (3 Commands)

```bash
# 1. Start the controller
make run-ui

# 2. Install agent (on target server)
curl -sSL http://localhost:8080/install.sh | bash -s -- http://localhost:8080

# 3. Deploy (via UI at http://localhost:8080 or AI Chat)
# Just talk to the AI: "Deploy my application" or click a workflow card!
```

## 💬 NEW: AI Chat Workflows

### Talk Naturally to Deploy
Open the AI chat (💬 icon) and try:
- **"Help me register a new agent"** → Guided 6-step onboarding
- **"Deploy my application"** → Interactive deployment wizard
- **"Fix this failed deployment"** → AI-powered troubleshooting
- **"Run a health check"** → Comprehensive system analysis
- **"Show workflows"** → See all available workflows as beautiful cards

### Interactive Features
✅ Natural language understanding
✅ **Quick Action Buttons** - Click instead of type! 🎯
✅ Step-by-step guidance  
✅ Smart input prompts (text, choices, numbers, etc.)
✅ Visual progress tracking
✅ Context-aware suggestions
✅ Approval gates for critical actions

### 🎯 Quick Action Buttons (NEW!)
When AI asks questions, **clickable buttons appear automatically**:
```
AI: "Ready to proceed?"
You: [Click] → [✅ Yes, proceed] or [❌ No, cancel]
```

**No typing required!** Just click through workflows. 🚀

## 🎯 Common Commands

### Controller Management

```bash
# Install dependencies (one-time)
make install

# Run controller (API only)
make run

# Run controller + open UI
make run-ui

# Run tests
make test

# Docker mode
docker-compose up -d
```

### Agent Management

```bash
# macOS - Start/stop agent
launchctl start com.deploybot.agent
launchctl stop com.deploybot.agent
launchctl list | grep deploybot

# Linux - Start/stop agent
sudo systemctl start deploybot-agent
sudo systemctl stop deploybot-agent
sudo systemctl status deploybot-agent

# View agent logs
tail -f ~/.deploybot/agent.log

# Check config
cat ~/.deploybot/config.yaml
```

### CLI Operations

```bash
# Deploy
python -m cli.ctl deploy --repo myorg/app --ref main --host web-01

# View logs
python -m cli.ctl logs

# Check job status
python -m cli.ctl status <job-id>
```

## 📍 Key URLs

- **UI Dashboard**: http://localhost:8080
- **API Docs**: http://localhost:8080/docs
- **Agent Installer**: http://localhost:8080/install.sh

## 📁 Important Files

```
~/.deploybot/config.yaml    # Agent configuration
~/.deploybot/agent.log      # Agent logs
config/apps.yaml            # Repo-to-host mappings
data/deploybot.db           # Job/agent database
.env                        # Controller settings
```

## 🔧 Configuration

### Controller (.env)

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/deploybot.db
GITHUB_WEBHOOK_SECRET=your-secret-here
LOG_LEVEL=INFO
```

### Apps (config/apps.yaml)

```yaml
applications:
  - repository: "myorg/web-app"
    hosts:
      - "web-01"
      - "web-02"
    deploy_on_push: true
    branches:
      - "main"
      - "staging"
```

### Agent (~/.deploybot/config.yaml)

```yaml
controller_url: http://localhost:8080
hostname: web-01
poll_interval: 5
```

## 🐛 Troubleshooting

### Agent Not Connecting

```bash
# Check agent is running
launchctl list | grep deploybot          # macOS
sudo systemctl status deploybot-agent    # Linux

# View logs
tail -f ~/.deploybot/agent.log

# Test connectivity
curl http://localhost:8080/v1/agents/register -X POST \
  -H "Content-Type: application/json" \
  -d '{"hostname":"test","version":"1.0.0"}'
```

### Jobs Stuck in Pending

```bash
# Check agent hostname matches job
curl http://localhost:8080/v1/agents
curl http://localhost:8080/v1/jobs

# View agent logs for errors
tail -f ~/.deploybot/agent.log
```

### Controller Won't Start

```bash
# Check port 8080 is available
lsof -i :8080

# Check Python environment
which python
python --version

# Check dependencies
pip list | grep fastapi

# Run with debug logging
LOG_LEVEL=DEBUG make run
```

## 📊 API Endpoints Reference

### Agents
- `POST /v1/agents/register` - Register new agent
- `POST /v1/agents/{id}/heartbeat` - Heartbeat + get jobs
- `GET /v1/agents` - List all agents

### Jobs
- `POST /v1/jobs` - Create deployment job
- `GET /v1/jobs` - List all jobs
- `GET /v1/jobs/{id}` - Get job details
- `GET /v1/jobs/{id}/logs/stream` - Stream logs (SSE)

### Other
- `GET /v1/hosts` - List registered hosts
- `POST /v1/webhooks/github` - GitHub webhook
- `GET /` - Web UI
- `GET /install.sh` - Agent installer

## 🎨 UI Features

- **Auto-refresh**: Every 5 seconds
- **Quick Deploy**: Manual deployments
- **Agent Status**: Real-time health monitoring
- **Job History**: All deployments with status
- **Install Command**: Copy-to-clipboard

## 🔐 Security Checklist (Pre-Production)

- [ ] Add API authentication (JWT/API keys)
- [ ] Enable HTTPS/TLS
- [ ] Set secure GITHUB_WEBHOOK_SECRET
- [ ] Implement rate limiting
- [ ] Add audit logging
- [ ] Configure firewall rules
- [ ] Use secret management (Vault)
- [ ] Enable CORS properly
- [ ] Add input validation
- [ ] Set up monitoring/alerts

## 📚 Documentation Links

- [Complete Solution Summary](SOLUTION_SUMMARY.md)
- [UI Guide](docs/UI_GUIDE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [Quick Start](docs/QUICKSTART.md)

## 💡 Pro Tips

1. **Use UI for quick deploys** - Fastest way to trigger deployments
2. **Monitor agent logs** - First place to check for issues
3. **Configure webhooks** - Automate deployments on push
4. **One agent per host** - Simplifies management
5. **Test with CLI first** - Verify setup before webhooks
6. **Check job status in UI** - Real-time updates every 5s
7. **Use same hostname** - Agent must match job's target host

## 🎯 Success Indicators

✅ Agent appears in UI within 5 seconds of installation
✅ Jobs move from pending → running → success
✅ Logs stream in real-time
✅ GitHub webhooks trigger deployments automatically
✅ Multiple agents can run simultaneously
✅ Job queue processes FIFO per host

## 📞 Quick Help

**Issue**: Agent not showing in UI
**Fix**: Check `~/.deploybot/agent.log` and verify controller URL

**Issue**: Jobs not starting
**Fix**: Ensure agent hostname matches job's target host exactly

**Issue**: Webhook not working
**Fix**: Verify HMAC secret matches in GitHub and .env file

**Issue**: UI not loading
**Fix**: Check controller is running: `curl http://localhost:8080`
