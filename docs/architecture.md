# DeployBot Agent MVP Architecture

## Overview
The agent is a long-running daemon that connects to the DeployBot controller, registers itself, and executes jobs dispatched by the controller. The implementation prioritises a single static Go binary capable of running on hosts with Docker installed.

## Key Components

- **cmd/deploybot-agent** – entrypoint that wires configuration, state, controller client, Docker manager, and the job handler.
- **internal/config** – parses environment variables / flags for controller endpoint, bootstrap token, intervals, and data directories.
- **internal/state** – durable storage for agent credentials, deployment history, and TCP port reservations. Stored at `/var/lib/deploybot/agent.json`.
- **internal/controller** – thin HTTP client around the DeployBot controller API (register, heartbeat, job ack, log streaming).
- **internal/metrics** – host CPU, memory, and disk telemetry collection via gopsutil.
- **internal/dockerutil** – wraps Docker SDK interactions (engine version, inventory, container lifecycle, deployments, log streams).
- **internal/git** – shallow clones repositories into timestamped workspaces for job execution.
- **internal/jobs** – domain objects and handler logic that orchestrate cloning, deployment strategy selection, job execution, rollback, and status reporting.
- **internal/audit** – JSONL audit logger capturing job lifecycle, policy denials, and cleanup events.
- **internal/setup** – interactive prerequisite helper that guides first-time hosts through creating service users, Docker membership, and TLS scaffolding.

## Job Flow
1. Agent starts, loads state, gathers metrics, fetches Docker version, registers with controller.
2. Registration response stores persistent agent credentials.
3. A heartbeat loop gathers metrics/inventory and polls for work. When a job is returned:
   - `deploy`: shallow clone repo, select strategy (`deploy.compose.yml` > `docker-compose.yml` > `deploy.json` > `Dockerfile` > direct image). Uses Docker SDK for container lifecycle and port allocation (auto assigns within 20000–65000, persisted in state) and enforces registry/digest/volume policies unless explicitly bypassed.
   - `restart` / `stop` / `remove`: target containers by name/label.
   - `logs`: streams `docker logs` via chunked POST back to controller for the requested duration.
   - `exec`: (opt-in) run a host command with captured stdout/stderr for incident tooling.
   - `query_env`: (opt-in) return selected host environment variables for diagnostics.
4. Deployments maintain rollback data. New containers start alongside previous ones; health gates (Docker health or HTTP probes) guard promotion. Failures revert to the last known good container.

## Security Posture

- **Transport** – HTTPS is mandatory by default. Mutual TLS and certificate pinning are supported via `CLIENT_CERT_FILE`/`CLIENT_KEY_FILE` and `CONTROLLER_CA_PINS`. Plain HTTP or insecure TLS can be enabled only with `ALLOW_INSECURE_CONTROLLER=true` or the global `SECURITY_BYPASS=true` escape hatch.
- **Credential Hygiene** – Agent credentials are stored in `/var/lib/deploybot/agent.json` encrypted with AES-GCM (key sourced from `AGENT_STATE_KEY`) and transparently re-wrapped on startup. Without a key the agent refuses to boot with encryption enabled.
- **Policy Enforcement** – When security enforcement is active the handler checks container images against an allowlist (`REGISTRY_ALLOWLIST`), requires digest-pinned references (`REQUIRE_IMAGE_DIGEST=true`), sanitises bind mounts to `ALLOWED_VOLUME_ROOTS`, and blocks unsafe command jobs unless explicitly allowed (`ALLOW_UNSAFE_COMMANDS=true`).
- **Workspace Hygiene** – Git work trees are discarded after each job when `CLEANUP_WORKSPACES=true`, with audit logs for success/failure.
- **Operator Assist** – An interactive setup mode (TTY only) walks operators through provisioning the `deploybot` service account, Docker group membership, and TLS artifacts, then records progress in the audit log.
- **Audit Trail** – Every job start/finish, policy rejection, and workspace cleanup is appended to `AUDIT_LOG_PATH` (JSONL) for forward shipping.
- **Least Privilege** – The packaged systemd unit runs the binary as a dedicated `deploybot` service account (supplemental `docker` group) and can be further locked down with systemd hardening directives.

## Persistence Layout
```
/var/lib/deploybot
├── agent.json      # credentials, port map, deployment records
└── work/           # git workspaces (repo/ref/timestamp)
```

## Future Enhancements
- Enhanced signature verification (cosign integration) for image provenance.
- Additional health probes (custom commands, script hooks).
- Artifact/image caching and buildkit integration.
- Concurrency limits and job queueing.
- Structured log ingestion and tracing.
