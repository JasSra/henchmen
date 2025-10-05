# Deployment Guide

## Local Development

### Prerequisites
- Python 3.11+
- pip
- make (optional, but recommended)

### Setup

1. **Clone and enter directory**
   ```bash
   cd /Users/jas/code/My/Henchmen
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and set GITHUB_WEBHOOK_SECRET
   ```

4. **Start the controller**
   ```bash
   make run
   # Or: python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
   ```

5. **Access the API**
   - API: <http://localhost:8080>
   - Docs: <http://localhost:8080/docs>
   - Health: <http://localhost:8080/health>

## Docker Deployment

### Using Docker Compose (Recommended)

1. **Build the image**
   ```bash
   make docker-build
   ```

2. **Start services**
   ```bash
   make docker-up
   ```

3. **View logs**
   ```bash
   make docker-logs
   ```

4. **Stop services**
   ```bash
   make docker-down
   ```

### Using Docker directly

```bash
# Build
docker build -t deploybot-controller .

# Run
docker run -d \
  -p 8080:8080 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config:/app/config \
  -e GITHUB_WEBHOOK_SECRET=your-secret \
  --name deploybot \
  deploybot-controller

# View logs
docker logs -f deploybot

# Stop
docker stop deploybot
docker rm deploybot
```

## Production Deployment

### Environment Variables

Required:
- `GITHUB_WEBHOOK_SECRET` - Secret for webhook HMAC verification

Optional:
- `HOST` - Bind host (default: 0.0.0.0)
- `PORT` - Bind port (default: 8080)
- `DATABASE_PATH` - SQLite database path (default: ./data/deploybot.db)
- `LOG_LEVEL` - Logging level (default: INFO)

### Using systemd (Linux)

1. **Create service file** `/etc/systemd/system/deploybot.service`:

   ```ini
   [Unit]
   Description=DeployBot Controller
   After=network.target

   [Service]
   Type=simple
   User=deploybot
   WorkingDirectory=/opt/deploybot
   Environment="PATH=/opt/deploybot/venv/bin"
   EnvironmentFile=/opt/deploybot/.env
   ExecStart=/opt/deploybot/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

2. **Enable and start**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable deploybot
   sudo systemctl start deploybot
   sudo systemctl status deploybot
   ```

### Using Kubernetes

Create `deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: deploybot-controller
spec:
  replicas: 1
  selector:
    matchLabels:
      app: deploybot-controller
  template:
    metadata:
      labels:
        app: deploybot-controller
    spec:
      containers:
      - name: controller
        image: deploybot-controller:latest
        ports:
        - containerPort: 8080
        env:
        - name: GITHUB_WEBHOOK_SECRET
          valueFrom:
            secretKeyRef:
              name: deploybot-secrets
              key: webhook-secret
        volumeMounts:
        - name: data
          mountPath: /app/data
        - name: config
          mountPath: /app/config
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: deploybot-data
      - name: config
        configMap:
          name: deploybot-config
---
apiVersion: v1
kind: Service
metadata:
  name: deploybot-controller
spec:
  selector:
    app: deploybot-controller
  ports:
  - port: 80
    targetPort: 8080
  type: LoadBalancer
```

## GitHub Webhook Setup

1. **Generate a webhook secret**:
   ```bash
   openssl rand -hex 32
   ```

2. **Set in environment**:
   ```bash
   export GITHUB_WEBHOOK_SECRET=<generated-secret>
   # Or add to .env file
   ```

3. **Configure in GitHub**:
   - Go to repository Settings > Webhooks > Add webhook
   - Payload URL: `https://your-controller.com/v1/webhooks/github`
   - Content type: `application/json`
   - Secret: (paste the generated secret)
   - Events: "Just the push event"
   - Active: ✓

4. **Test the webhook**:
   - Push a commit to a configured branch
   - Check Recent Deliveries in GitHub webhook settings
   - Verify jobs created: `curl http://localhost:8080/v1/jobs`

## Reverse Proxy (nginx)

For production, use nginx as reverse proxy:

```nginx
server {
    listen 80;
    server_name deploybot.example.com;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSE support for log streaming
    location /v1/logs/stream {
        proxy_pass http://localhost:8080;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_buffering off;
        proxy_cache off;
    }
}
```

With HTTPS (recommended):

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d deploybot.example.com

# Auto-renewal is configured automatically
```

## Monitoring

### Health Checks

```bash
# Basic health check
curl http://localhost:8080/health

# Response: {"status": "healthy", "timestamp": "..."}
```

### Logs

```bash
# View logs
docker logs -f deploybot

# Or with journalctl (systemd)
journalctl -u deploybot -f
```

### Metrics (Future)

Consider adding:
- Prometheus exporter
- Grafana dashboard
- Alert rules for job failures

## Backup & Recovery

### Backup database

```bash
# SQLite backup
cp data/deploybot.db data/deploybot.db.backup

# Or use SQLite backup command
sqlite3 data/deploybot.db ".backup 'data/backup.db'"
```

### Restore database

```bash
# Copy backup
cp data/deploybot.db.backup data/deploybot.db

# Restart controller
systemctl restart deploybot
```

## Scaling Considerations

For high-traffic deployments:

1. **Use PostgreSQL** instead of SQLite
2. **Add Redis** for distributed job queue
3. **Multiple instances** behind load balancer
4. **Distributed locking** with Redis or etcd
5. **Message queue** (RabbitMQ, Kafka) for job distribution

## Troubleshooting

### Controller won't start

```bash
# Check logs
docker logs deploybot

# Check port availability
lsof -i :8080

# Verify dependencies
pip install -r requirements.txt
```

### Webhooks not working

```bash
# Check secret matches
echo $GITHUB_WEBHOOK_SECRET

# Test webhook signature
curl -X POST http://localhost:8080/v1/webhooks/github \
  -H "X-Hub-Signature-256: sha256=test"
# Should return 401

# Check apps.yaml config
cat config/apps.yaml
```

### Jobs not being assigned

```bash
# Check agent registration
curl http://localhost:8080/v1/hosts

# Check job queue
curl http://localhost:8080/v1/jobs

# Verify hostname matches between agent and job
```

## Security Checklist

- [ ] Strong webhook secret (32+ random bytes)
- [ ] HTTPS enabled (use Let's Encrypt)
- [ ] API authentication (add API keys for production)
- [ ] Firewall configured
- [ ] Regular security updates
- [ ] Database backups enabled
- [ ] Rate limiting configured
- [ ] Input validation enabled (Pydantic handles this)
- [ ] CORS configured if needed
- [ ] Log sensitive data redacted
