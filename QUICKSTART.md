# Quick Start Guide

## Prerequisites

- Python 3.11+
- pip

## Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env and set GITHUB_WEBHOOK_SECRET
   ```

3. **Start the controller:**
   ```bash
   make run
   ```

   The controller will start on http://localhost:8080

## Testing the Installation

Run the acceptance tests:
```bash
# In another terminal (while controller is running)
bash test_acceptance.sh
```

Or manually test with curl:

```bash
# 1. Register an agent
curl -X POST http://localhost:8080/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"hostname":"my-server-01","capabilities":{}}'

# Note the agent ID from the response

# 2. Send heartbeat (replace AGENT_ID)
curl -X POST http://localhost:8080/v1/agents/AGENT_ID/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"status":"online"}'

# 3. Create a job
curl -X POST http://localhost:8080/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "myorg/my-app",
    "ref": "main",
    "host": "my-server-01"
  }'

# Note the job_id from the response

# 4. Get job status
curl http://localhost:8080/v1/jobs/JOB_ID

# 5. List all hosts
curl http://localhost:8080/v1/hosts
```

## Using the CLI

```bash
# Deploy manually
python -m cli.ctl deploy --repo myorg/web-app --ref main --host web-01.example.com

# Check job status
python -m cli.ctl status JOB_ID

# View logs
python -m cli.ctl logs --host web-01.example.com
```

## Docker Usage

```bash
# Build and start
make docker-build
make docker-up

# View logs
make docker-logs

# Stop
make docker-down
```

## Running Tests

```bash
make test
```

## API Documentation

Once running, visit:
- Interactive docs: http://localhost:8080/docs
- OpenAPI schema: http://localhost:8080/openapi.json

## Configuration

Edit `config/apps.yaml` to configure which repositories should auto-deploy to which hosts:

```yaml
apps:
  - name: "my-app"
    repo: "myorg/my-app"
    hosts:
      - "server-01.example.com"
    deploy_on_push: true
    branches:
      - "main"
```

## GitHub Webhook Setup

1. In your GitHub repository, go to Settings > Webhooks
2. Add webhook:
   - Payload URL: `https://your-controller.com/v1/webhooks/github`
   - Content type: `application/json`
   - Secret: (same as GITHUB_WEBHOOK_SECRET in .env)
   - Events: "Just the push event"
