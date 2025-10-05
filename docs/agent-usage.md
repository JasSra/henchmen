# DeployBot Agent Operations Guide

This guide explains how to configure, secure, and operate the DeployBot agent. It complements the high-level architecture document with practical steps for installing the binary, enabling hardening features, and understanding runtime capabilities.

## 1. Installation Recap

1. Copy the compiled binary to the host (or build via the provided Dockerfile: `docker build -t deploybot-agent .`).
2. Place it at `/usr/local/bin/deploybot-agent` and ensure it is executable.
3. Run `/usr/local/bin/deploybot-agent --interactive-setup` in a terminal; the helper will offer to create the `deploybot` account, join the `docker` group, and scaffold TLS files if they are missing. (The helper automatically skips when no TTY is attached; set `DEPLOYBOT_SKIP_SETUP=1` to suppress it manually.)
4. Copy `packaging/systemd/deploybot-agent.service` into `/etc/systemd/system/`.
5. If you ran non-interactively, create a dedicated service user and grant Docker access:
   ```bash
   sudo useradd --system --home /var/lib/deploybot --shell /usr/sbin/nologin deploybot
   sudo usermod -aG docker deploybot
   mkdir -p /var/lib/deploybot
   chown -R deploybot:deploybot /var/lib/deploybot
   ```
6. (Optional) populate `/etc/deploybot-agent.env` with environment overrides.
7. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now deploybot-agent
   ```

## 2. Core Configuration

| Variable / Flag | Purpose |
| --- | --- |
| `CONTROLLER_URL` / `--controller-url` | HTTPS endpoint of the controller (required) |
| `AGENT_TOKEN` / `--agent-token` | Bootstrap token issued by the controller (required for first registration) |
| `HEARTBEAT_INTERVAL` / `--heartbeat-interval` | Polling cadence in seconds (default `10`) |
| `AGENT_DATA_DIR` / `--data-dir` | Persistent state directory (default `/var/lib/deploybot`) |
| `AGENT_WORK_DIR` / `--work-dir` | Git workspace root (defaults to `$data-dir/work`) |
| `HEALTH_TIMEOUT` / `--health-timeout` | Max time to wait for container health (default `60s`) |
| `LOGS_FOLLOW_DURATION` / `--logs-follow-duration` | Default follow duration for log tail jobs (default `2m`) |
| `AGENT_INTERACTIVE_SETUP` / `--interactive-setup` | Run the interactive prerequisite helper when a TTY is present (default `true`) |

## 3. Transport Security

Transport security is enforced by default. The following options tune TLS behaviour.

| Variable / Flag | Description |
| --- | --- |
| `ALLOW_INSECURE_CONTROLLER` | Permit plain HTTP or skip TLS verification. **Avoid in production.** |
| `CONTROLLER_CA_FILE` | Path to additional CA bundle (PEM) |
| `CONTROLLER_CA_PINS` | Comma-separated SHA256 fingerprints (e.g. `sha256:ABCD...`) |
| `CLIENT_CERT_FILE` / `CLIENT_KEY_FILE` | Client certificate + key for mutual TLS |
| `SECURITY_BYPASS` | Master override that disables all safeguards (tests only) |

The agent refuses to talk to a non-HTTPS controller unless `ALLOW_INSECURE_CONTROLLER=true` or `SECURITY_BYPASS=true`.

## 4. Credential Protection

Set `AGENT_STATE_KEY` (any non-empty secret) to enable AES-GCM encryption of `/var/lib/deploybot/agent.json`. You can also toggle with `STATE_ENCRYPTION` or `--state-encryption`, but supplying a key is mandatory when enabled. Tokens are transparently rewrapped on every start.

## 5. Deployment Policy Controls

| Variable / Flag | Effect |
| --- | --- |
| `REGISTRY_ALLOWLIST` / `--registry-allowlist` | Comma-separated registries allowed for pulls (e.g. `registry.example.com,ghcr.io`) |
| `REQUIRE_IMAGE_DIGEST` / `--require-image-digest` | Reject images not pinned by digest (Compose services must use `image@sha256:` form) |
| `ALLOWED_VOLUME_ROOTS` / `--allowed-volume-roots` | Restrict bind mounts to specific host prefixes (`/srv/apps,/var/data`) |
| `CLEANUP_WORKSPACES` / `--cleanup-workspaces` | Remove git workspaces after jobs (default `true`) |
| `AUDIT_LOG_PATH` / `--audit-log` | Append JSONL audit events to this path |

Policy enforcement is automatically skipped when `SECURITY_BYPASS=true`.

## 6. Optional Jobs & Capabilities

The agent reports its capabilities in both registration and heartbeat payloads. Baseline features include `deploy`, `compose`, `dockerfile`, `image`, `restart`, `stop`, `remove`, and `logs`.

Additional verbs are disabled by default:

| Capability | Job Type | How to enable |
| --- | --- | --- |
| `exec` | `job.type = "exec"` | Set `ALLOW_UNSAFE_COMMANDS=true` (or `SECURITY_BYPASS=true`). Executes host commands, returning stdout/stderr, respecting per-job timeouts. |
| `env-query` | `job.type = "query_env"` | Same toggle as above. Returns the specified environment variables to the controller. |

When unsafe commands are disabled the agent rejects such jobs and records an audit event.

## 7. Audit Trail

Set `AUDIT_LOG_PATH=/var/log/deploybot/audit.log` (for example). The agent produces newline-delimited JSON entries such as:

```json
{"timestamp":"2024-05-19T12:34:56.789Z","event":"job.start","job_id":"abc123","job_type":"deploy"}
{"timestamp":"2024-05-19T12:35:01.102Z","event":"job.finish","job_id":"abc123","job_type":"deploy","status":"succeeded","duration_ms":4313}
{"timestamp":"2024-05-19T12:35:01.115Z","event":"workspace.cleaned","path":"/var/lib/deploybot/work/web/main/20240519T123456Z"}
```

Ship this file to your preferred SIEM for long-term retention.

## 8. Bypass & Testing Modes

- `SECURITY_BYPASS=true` disables TLS enforcement, policy checks, state encryption, and workspace cleanup. This is useful for local development but should **never** be enabled in production.
- `ALLOW_INSECURE_CONTROLLER=true` permits non-TLS controllers without disabling other policy checks.

## 9. Systemd Hardening Tips

The packaged unit runs as `deploybot:deploybot`, joins the `docker` group, clears all capabilities, and enables `NoNewPrivileges`, `ProtectSystem=full`, `ProtectHome=true`, and `PrivateTmp=true`. Depending on your distro you can further tighten isolation, for example:

```
ProtectSystem=strict
RestrictSUIDSGID=true
ProtectKernelModules=true
ProtectKernelTunables=true
SystemCallFilter=@system-service
LockPersonality=true
```

Remember to keep the `deploybot` account in the `docker` group (or use rootless Docker) so the engine remains accessible.

## 10. Troubleshooting Checklist

- Confirm `/etc/deploybot-agent.env` values match controller settings.
- Inspect the audit log for policy violation messages (image digest, volume path, TLS errors).
- Use `journalctl -u deploybot-agent` for service logs.
- Run `docker ps` to verify containers launched with the expected labels (`deploybot.job`, `deploybot.service`).

With these controls in place the agent maintains a secure posture while still offering opt-in escape hatches for legacy environments.
