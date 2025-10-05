# DeployBot Controller - Architecture

## System Architecture

```
┌──────────────┐
│   GitHub     │
│  Repository  │
└──────┬───────┘
       │ Push Event
       │ (webhook)
       ▼
┌─────────────────────────────────────────────┐
│         DeployBot Controller                │
│                                             │
│  ┌──────────────┐      ┌─────────────┐    │
│  │   Webhook    │      │    Queue    │    │
│  │   Handler    │─────▶│   Manager   │    │
│  └──────────────┘      └──────┬──────┘    │
│         │                      │           │
│         │ Verify HMAC         │           │
│         │ Map repo→hosts      │           │
│         ▼                      ▼           │
│  ┌──────────────┐      ┌─────────────┐    │
│  │ apps.yaml    │      │  Job Queue  │    │
│  │ Config       │      │  (in-memory)│    │
│  └──────────────┘      └──────┬──────┘    │
│                               │           │
│                               │ Persist   │
│                               ▼           │
│                        ┌─────────────┐    │
│                        │   SQLite    │    │
│                        │  Database   │    │
│                        └─────────────┘    │
│                                           │
│  ┌──────────────────────────────────┐    │
│  │        FastAPI Endpoints         │    │
│  │  • /v1/agents/register           │    │
│  │  • /v1/agents/{id}/heartbeat     │    │
│  │  • /v1/jobs                      │    │
│  │  • /v1/hosts                     │    │
│  │  • /v1/webhooks/github           │    │
│  │  • /v1/logs/stream              │    │
│  └──────────────────────────────────┘    │
└────────────────┬────────────────┬─────────┘
                 │                │
        Heartbeat│                │CLI
        (Polling)│                │
                 ▼                ▼
        ┌─────────────┐  ┌──────────────┐
        │   Agent 1   │  │  CLI Tool    │
        │  (host-01)  │  │   (ctl.py)   │
        └─────────────┘  └──────────────┘
                 │
        ┌─────────────┐
        │   Agent 2   │
        │  (host-02)  │
        └─────────────┘
```

## Data Flow

### 1. Deployment via GitHub Webhook

```
1. Developer pushes to GitHub
   ↓
2. GitHub sends webhook POST to /v1/webhooks/github
   ↓
3. Controller verifies HMAC signature
   ↓
4. Controller reads apps.yaml config
   ↓
5. Controller maps repo → hosts
   ↓
6. Controller creates job for each host
   ↓
7. Jobs added to queue and persisted to SQLite
```

### 2. Job Execution

```
1. Agent sends heartbeat to /v1/agents/{id}/heartbeat
   ↓
2. Controller checks queue for jobs matching agent's hostname
   ↓
3. If job found:
   - Mark job as RUNNING
   - Assign to agent
   - Return job in heartbeat response
   ↓
4. Agent executes deployment
   ↓
5. Agent reports completion (future enhancement)
```

### 3. Manual Deployment via CLI

```
1. User runs: ctl deploy --repo X --ref Y --host Z
   ↓
2. CLI makes POST to /v1/jobs
   ↓
3. Controller creates job
   ↓
4. Job queued and waits for agent heartbeat
```

## Key Components

### WebhookHandler (`app/webhooks.py`)
- Verifies HMAC-SHA256 signatures
- Parses GitHub push events
- Maps repositories to hosts using apps.yaml
- Creates JobCreate objects for queue

### JobQueue (`app/queue.py`)
- In-memory deque for pending jobs
- Dict for all jobs (indexed by ID)
- Idempotency checking (same repo+ref+host)
- Returns max 1 job per agent per heartbeat

### Store (`app/store.py`)
- SQLite persistence layer
- Tables: agents, jobs, logs
- Async operations with aiosqlite
- Indexes for efficient lookups

### Models (`app/models.py`)
- Pydantic models for validation
- Agent, Job, LogEntry entities
- Request/Response schemas
- Enum types for status

### Main App (`app/main.py`)
- FastAPI application
- All REST endpoints
- SSE log streaming
- Lifespan management

## Security Features

1. **HMAC Verification**: GitHub webhooks validated with SHA-256
2. **Input Validation**: Pydantic models validate all inputs
3. **No Auth (MVP)**: Production should add API keys/OAuth

## Scalability Considerations

Current MVP limitations:
- Single instance (in-memory queue)
- SQLite (not suitable for high concurrency)
- No distributed locking

For production scale:
- Use Redis for job queue
- PostgreSQL for persistence
- Multiple controller instances
- Load balancer in front
- Distributed locking (Redis, etcd)

## Monitoring & Observability

Built-in:
- `/health` endpoint for health checks
- SSE log streaming at `/v1/logs/stream`
- OpenAPI docs at `/docs`

Should add:
- Prometheus metrics
- Structured logging (JSON)
- Distributed tracing (OpenTelemetry)
- APM (Datadog, New Relic)
