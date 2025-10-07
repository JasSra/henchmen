"""
SQLite-based persistence layer for DeployBot Controller (moved under controller/app)
"""
import aiosqlite
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable
from pathlib import Path

from app.models import (
	Agent,
	Job,
	JobStatus,
	AgentStatus,
	LogEntry,
	DeploymentRecord,
	CommandTemplate,
	DockerImageTemplate,
	ToastNotification,
	PortMapping,
	VolumeMapping,
	EnvironmentVariable,
	HealthCheckConfig,
	HostMetrics,
	AgentMetricSample,
)


DEFAULT_COMMANDS: List[Dict[str, Any]] = [
	{
		"name": "Tail System Logs",
		"command": "sudo journalctl -n 200 -f",
		"description": "Stream the latest systemd journal entries",
		"tags": ["logs", "linux"],
	},
	{
		"name": "Container Stats",
		"command": "docker stats --no-stream",
		"description": "Snapshot of running container resource usage",
		"tags": ["docker", "ops"],
	},
	{
		"name": "Disk Usage Audit",
		"command": "df -h && du -sh /var/log/*",
		"description": "Check high-level disk consumption",
		"tags": ["maintenance"],
	},
	{
		"name": "Restart Container",
		"command": "docker restart ${CONTAINER:-my-service}",
		"description": "Restart a container by name (set CONTAINER env)",
		"tags": ["docker", "maintenance"],
	},
	{
		"name": "Inspect Processes",
		"command": "ps aux --sort=-%mem | head -n 15",
		"description": "Top processes by memory usage",
		"tags": ["linux", "monitoring"],
	},
	{
		"name": "Clean Docker Images",
		"command": "docker system prune -f",
		"description": "Remove unused Docker images and containers",
		"tags": ["docker", "cleanup"],
	},
	{
		"name": "Network Diagnostics",
		"command": "netstat -tuln && ss -tulw",
		"description": "Show network connections and listening ports",
		"tags": ["network", "diagnostics"],
	},
	{
		"name": "Service Status",
		"command": "systemctl status ${SERVICE:-nginx}",
		"description": "Check systemd service status (set SERVICE env)",
		"tags": ["linux", "services"],
	},
]

DEFAULT_DOCKER_TEMPLATES: List[Dict[str, Any]] = [
	{
		"name": "Nginx Web Server",
		"image": "nginx",
		"tag": "alpine",
		"description": "Lightweight Nginx web server",
		"category": "web",
		"ports": [{"container_port": 80, "host_port": 8080, "protocol": "tcp"}],
		"volumes": [{"source": "/var/www/html", "target": "/usr/share/nginx/html", "read_only": False}],
		"health_check": {"type": "http", "endpoint": "/", "expected_status": 200},
		"usage_notes": "Mount your HTML content to /var/www/html on the host",
		"tags": ["web", "server"],
	},
	{
		"name": "Redis Cache",
		"image": "redis",
		"tag": "7-alpine",
		"description": "Redis in-memory data store",
		"category": "database",
		"ports": [{"container_port": 6379, "host_port": 6379, "protocol": "tcp"}],
		"volumes": [{"source": "/var/lib/redis", "target": "/data", "read_only": False}],
		"health_check": {"type": "tcp", "endpoint": "6379"},
		"usage_notes": "Data persisted to /var/lib/redis on host",
		"tags": ["database", "cache"],
	},
	{
		"name": "PostgreSQL Database",
		"image": "postgres",
		"tag": "15-alpine",
		"description": "PostgreSQL relational database",
		"category": "database",
		"ports": [{"container_port": 5432, "host_port": 5432, "protocol": "tcp"}],
		"volumes": [{"source": "/var/lib/postgresql", "target": "/var/lib/postgresql/data", "read_only": False}],
		"environment": [
			{"key": "POSTGRES_DB", "value": "myapp"},
			{"key": "POSTGRES_USER", "value": "postgres"},
			{"key": "POSTGRES_PASSWORD", "value": "changeme"}
		],
		"health_check": {"type": "command", "command": ["pg_isready", "-U", "postgres"]},
		"usage_notes": "Change POSTGRES_PASSWORD before deploying to production",
		"tags": ["database", "postgresql"],
	},
	{
		"name": "Node.js Application",
		"image": "node",
		"tag": "18-alpine",
		"description": "Node.js runtime for web applications",
		"category": "web",
		"ports": [{"container_port": 3000, "host_port": 3000, "protocol": "tcp"}],
		"volumes": [{"source": "/app", "target": "/usr/src/app", "read_only": False}],
		"environment": [{"key": "NODE_ENV", "value": "production"}],
		"usage_notes": "Mount your Node.js app to /app on the host, ensure package.json exists",
		"tags": ["web", "nodejs"],
	},
	{
		"name": "MySQL Database",
		"image": "mysql",
		"tag": "8.0",
		"description": "MySQL relational database server",
		"category": "database",
		"ports": [{"container_port": 3306, "host_port": 3306, "protocol": "tcp"}],
		"volumes": [{"source": "/var/lib/mysql", "target": "/var/lib/mysql", "read_only": False}],
		"environment": [
			{"key": "MYSQL_ROOT_PASSWORD", "value": "changeme"},
			{"key": "MYSQL_DATABASE", "value": "myapp"}
		],
		"health_check": {"type": "command", "command": ["mysqladmin", "ping", "-h", "localhost"]},
		"usage_notes": "Change MYSQL_ROOT_PASSWORD before deploying",
		"tags": ["database", "mysql"],
	},
	{
		"name": "MongoDB Database",
		"image": "mongo",
		"tag": "6.0",
		"description": "MongoDB NoSQL database",
		"category": "database",
		"ports": [{"container_port": 27017, "host_port": 27017, "protocol": "tcp"}],
		"volumes": [{"source": "/var/lib/mongodb", "target": "/data/db", "read_only": False}],
		"usage_notes": "Data persisted to /var/lib/mongodb on host",
		"tags": ["database", "mongodb"],
	},
	{
		"name": "Apache Web Server",
		"image": "httpd",
		"tag": "2.4-alpine",
		"description": "Apache HTTP Server",
		"category": "web",
		"ports": [{"container_port": 80, "host_port": 8080, "protocol": "tcp"}],
		"volumes": [{"source": "/var/www/html", "target": "/usr/local/apache2/htdocs", "read_only": False}],
		"health_check": {"type": "http", "endpoint": "/", "expected_status": 200},
		"usage_notes": "Mount your web content to /var/www/html on the host",
		"tags": ["web", "apache"],
	},
	{
		"name": "Grafana Monitoring",
		"image": "grafana/grafana",
		"tag": "latest",
		"description": "Grafana monitoring and visualization",
		"category": "monitoring",
		"ports": [{"container_port": 3000, "host_port": 3000, "protocol": "tcp"}],
		"volumes": [{"source": "/var/lib/grafana", "target": "/var/lib/grafana", "read_only": False}],
		"environment": [
			{"key": "GF_SECURITY_ADMIN_PASSWORD", "value": "admin"}
		],
		"health_check": {"type": "http", "endpoint": "/api/health", "expected_status": 200},
		"usage_notes": "Default login: admin/admin, change password after first login",
		"tags": ["monitoring", "grafana"],
	},
]


class Store:
	"""SQLite-based storage for agents, jobs, and logs"""
    
	def __init__(self, db_path: str):
		self.db_path = db_path
		Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
	async def init_db(self):
		"""Initialize database schema"""
		async with aiosqlite.connect(self.db_path) as db:
			await self._create_core_tables(db)
			await self._ensure_jobs_schema(db)
			await self._seed_default_commands(db)
			await self._seed_default_docker_templates(db)
			await db.commit()

	async def _create_core_tables(self, db: aiosqlite.Connection) -> None:
		"""Create base tables if they do not exist"""
		await db.execute("""
			CREATE TABLE IF NOT EXISTS agents (
				id TEXT PRIMARY KEY,
				hostname TEXT NOT NULL,
				capabilities TEXT,
				status TEXT NOT NULL,
				registered_at TEXT NOT NULL,
				last_heartbeat TEXT NOT NULL,
				os_info TEXT,
				hardware_info TEXT,
				network_info TEXT,
				docker_info TEXT,
				current_metrics TEXT,
				uptime_seconds INTEGER,
				agent_version TEXT,
				tags TEXT,
				total_commands INTEGER DEFAULT 0,
				successful_commands INTEGER DEFAULT 0,
				failed_commands INTEGER DEFAULT 0,
				last_command_at TEXT
			)
		""")

		await db.execute("""
			CREATE TABLE IF NOT EXISTS agent_metrics (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				agent_id TEXT NOT NULL,
				recorded_at TEXT NOT NULL,
				cpu_percent REAL,
				mem_percent REAL,
				disk_free_gb REAL,
				raw TEXT
			)
		""")

		await db.execute("""
			CREATE INDEX IF NOT EXISTS idx_agent_metrics_agent
			ON agent_metrics(agent_id, recorded_at)
		""")

		await db.execute("""
			CREATE TABLE IF NOT EXISTS jobs (
				id TEXT PRIMARY KEY,
				job_type TEXT NOT NULL DEFAULT 'deploy',
				repo TEXT,
				ref TEXT,
				host TEXT NOT NULL,
				status TEXT NOT NULL,
				metadata TEXT NOT NULL DEFAULT '{}',
				deployment_id TEXT,
				deployment_spec TEXT,
				created_at TEXT NOT NULL,
				started_at TEXT,
				completed_at TEXT,
				assigned_agent TEXT,
				error TEXT,
				tags TEXT,
				priority INTEGER DEFAULT 5,
				retry_count INTEGER DEFAULT 0,
				max_retries INTEGER DEFAULT 0,
				estimated_duration_seconds INTEGER,
				actual_duration_seconds INTEGER,
				resource_usage TEXT,
				progress_percentage INTEGER,
				progress_message TEXT
			)
		""")

		await db.execute("""
			CREATE INDEX IF NOT EXISTS idx_jobs_lookup
			ON jobs(job_type, repo, ref, host, status)
		""")

		await db.execute("""
			CREATE TABLE IF NOT EXISTS logs (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				timestamp TEXT NOT NULL,
				job_id TEXT,
				host TEXT,
				app TEXT,
				level TEXT NOT NULL,
				message TEXT NOT NULL
			)
		""")

		await db.execute("""
			CREATE TABLE IF NOT EXISTS deployments (
				id TEXT PRIMARY KEY,
				name TEXT NOT NULL,
				kind TEXT NOT NULL,
				spec TEXT NOT NULL,
				description TEXT,
				tags TEXT,
				created_at TEXT NOT NULL,
				updated_at TEXT NOT NULL
			)
		""")

		await db.execute("""
			CREATE INDEX IF NOT EXISTS idx_deployments_name
			ON deployments(name)
		""")

		await db.execute("""
			CREATE TABLE IF NOT EXISTS commands (
				id TEXT PRIMARY KEY,
				name TEXT NOT NULL,
				command TEXT NOT NULL,
				description TEXT,
				tags TEXT,
				is_system INTEGER NOT NULL DEFAULT 0,
				runtime TEXT NOT NULL DEFAULT 'shell',
				created_at TEXT NOT NULL,
				updated_at TEXT NOT NULL
			)
		""")

		await db.execute("""
			CREATE INDEX IF NOT EXISTS idx_commands_name
			ON commands(name)
		""")

		await db.execute("""
			CREATE TABLE IF NOT EXISTS chat_sessions (
				id TEXT PRIMARY KEY,
				user_id TEXT NOT NULL DEFAULT 'default',
				name TEXT,
				created_at TEXT NOT NULL,
				last_activity TEXT NOT NULL,
				archived BOOLEAN NOT NULL DEFAULT 0,
				archived_at TEXT
			)
		""")

		await db.execute("""
			CREATE TABLE IF NOT EXISTS chat_messages (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				session_id TEXT NOT NULL,
				role TEXT NOT NULL,
				content TEXT NOT NULL,
				timestamp TEXT NOT NULL,
				metadata TEXT,
				FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
			)
		""")

		await db.execute("""
			CREATE INDEX IF NOT EXISTS idx_chat_messages_session
			ON chat_messages(session_id, timestamp)
		""")

		await db.execute("""
			CREATE INDEX IF NOT EXISTS idx_chat_sessions_user
			ON chat_sessions(user_id, archived, last_activity DESC)
		""")

		# Docker image templates table
		await db.execute("""
			CREATE TABLE IF NOT EXISTS docker_templates (
				id TEXT PRIMARY KEY,
				name TEXT NOT NULL,
				image TEXT NOT NULL,
				tag TEXT NOT NULL DEFAULT 'latest',
				description TEXT,
				category TEXT NOT NULL DEFAULT 'general',
				ports TEXT, -- JSON array
				volumes TEXT, -- JSON array
				environment TEXT, -- JSON array
				health_check TEXT, -- JSON object
				usage_notes TEXT,
				tags TEXT, -- JSON array
				is_system BOOLEAN NOT NULL DEFAULT 0,
				created_at TEXT NOT NULL,
				updated_at TEXT NOT NULL
			)
		""")

		# Toast notifications table
		await db.execute("""
			CREATE TABLE IF NOT EXISTS notifications (
				id TEXT PRIMARY KEY,
				type TEXT NOT NULL DEFAULT 'info',
				title TEXT NOT NULL,
				message TEXT NOT NULL,
				agent_id TEXT,
				job_id TEXT,
				timestamp TEXT NOT NULL,
				auto_dismiss BOOLEAN NOT NULL DEFAULT 1,
				timeout_seconds INTEGER NOT NULL DEFAULT 5,
				actions TEXT, -- JSON array
				is_dismissed BOOLEAN NOT NULL DEFAULT 0,
				dismissed_at TEXT
			)
		""")

		await db.execute("""
			CREATE INDEX IF NOT EXISTS idx_notifications_timestamp
			ON notifications(timestamp DESC)
		""")

		await db.execute("""
			CREATE INDEX IF NOT EXISTS idx_notifications_agent
			ON notifications(agent_id, timestamp DESC)
		""")

		await db.commit()

	async def _ensure_jobs_schema(self, db: aiosqlite.Connection) -> None:
		"""Migrate jobs table to latest schema if required"""
		db.row_factory = aiosqlite.Row
		async with db.execute("PRAGMA table_info(jobs)") as cursor:
			columns = {row["name"]: row for row in await cursor.fetchall()}

		if not columns:
			return

		requires_migration = False
		for required in ("job_type", "deployment_id", "deployment_spec"):
			if required not in columns:
				requires_migration = True
				break

		if not requires_migration:
			repo_col = columns.get("repo")
			metadata_col = columns.get("metadata")
			if repo_col and repo_col["notnull"]:
				requires_migration = True
			if metadata_col and not metadata_col["notnull"]:
				requires_migration = True

		if not requires_migration:
			return

		await db.execute("ALTER TABLE jobs RENAME TO jobs_legacy")
		await db.execute("""
			CREATE TABLE jobs (
				id TEXT PRIMARY KEY,
				job_type TEXT NOT NULL DEFAULT 'deploy',
				repo TEXT,
				ref TEXT,
				host TEXT NOT NULL,
				status TEXT NOT NULL,
				metadata TEXT NOT NULL DEFAULT '{}',
				deployment_id TEXT,
				deployment_spec TEXT,
				created_at TEXT NOT NULL,
				started_at TEXT,
				completed_at TEXT,
				assigned_agent TEXT,
				error TEXT
			)
		""")

		await db.execute("""
			INSERT INTO jobs (
				id, job_type, repo, ref, host, status, metadata,
				deployment_id, deployment_spec, created_at, started_at,
				completed_at, assigned_agent, error
			)
			SELECT
				id,
				'deploy',
				repo,
				ref,
				host,
				status,
				COALESCE(metadata, '{}'),
				NULL,
				NULL,
				created_at,
				started_at,
				completed_at,
				assigned_agent,
				error
			FROM jobs_legacy
		""")

		await db.execute("DROP TABLE jobs_legacy")
		await db.execute("DROP INDEX IF EXISTS idx_jobs_lookup")
		await db.execute("""
			CREATE INDEX IF NOT EXISTS idx_jobs_lookup
			ON jobs(job_type, repo, ref, host, status)
		""")

	async def _seed_default_commands(self, db: aiosqlite.Connection) -> None:
		"""Populate built-in command templates once"""
		db.row_factory = aiosqlite.Row
		async with db.execute("SELECT COUNT(1) as cnt FROM commands WHERE is_system = 1") as cursor:
			row = await cursor.fetchone()
			if row and row["cnt"]:
				return

		now = datetime.utcnow().isoformat()
		for template in DEFAULT_COMMANDS:
			command_id = str(uuid.uuid4())
			await db.execute(
				"""
				INSERT INTO commands (id, name, command, description, tags, is_system, runtime, created_at, updated_at)
				VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
			""",
				(
					command_id,
					template["name"],
					template["command"],
					template.get("description"),
					json.dumps(template.get("tags", [])),
					template.get("runtime", "shell"),
					now,
					now,
				),
			)

	async def _seed_default_docker_templates(self, db: aiosqlite.Connection) -> None:
		"""Populate built-in Docker templates once"""
		db.row_factory = aiosqlite.Row
		async with db.execute("SELECT COUNT(1) as cnt FROM docker_templates WHERE is_system = 1") as cursor:
			row = await cursor.fetchone()
			if row and row["cnt"]:
				return

		now = datetime.utcnow().isoformat()
		for template in DEFAULT_DOCKER_TEMPLATES:
			template_id = str(uuid.uuid4())
			await db.execute(
				"""
				INSERT INTO docker_templates (id, name, image, tag, description, category, ports, volumes, environment, health_check, usage_notes, tags, is_system, created_at, updated_at)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
			""",
				(
					template_id,
					template["name"],
					template["image"],
					template.get("tag", "latest"),
					template.get("description"),
					template.get("category", "general"),
					json.dumps(template.get("ports", [])),
					json.dumps(template.get("volumes", [])),
					json.dumps(template.get("environment", [])),
					json.dumps(template.get("health_check", {})),
					template.get("usage_notes"),
					json.dumps(template.get("tags", [])),
					now,
					now,
				),
			)

    
	# Agent operations
	async def save_agent(self, agent: Agent) -> None:
		"""Save or update an agent"""
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute("""
				INSERT OR REPLACE INTO agents
				(id, hostname, capabilities, status, registered_at, last_heartbeat,
				os_info, hardware_info, network_info, docker_info, current_metrics,
				uptime_seconds, agent_version, tags, total_commands, successful_commands,
				failed_commands, last_command_at)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			""", (
				agent.id,
				agent.hostname,
				json.dumps(agent.capabilities or {}),
				agent.status.value,
				agent.registered_at.isoformat(),
				agent.last_heartbeat.isoformat(),
				json.dumps(agent.os_info) if agent.os_info is not None else None,
				json.dumps(agent.hardware_info) if agent.hardware_info is not None else None,
				json.dumps(agent.network_info) if agent.network_info is not None else None,
				json.dumps(agent.docker_info) if agent.docker_info is not None else None,
				json.dumps(agent.current_metrics.model_dump()) if agent.current_metrics is not None else None,
				agent.uptime_seconds,
				agent.agent_version,
				json.dumps(agent.tags or []),
				agent.total_commands,
				agent.successful_commands,
				agent.failed_commands,
				agent.last_command_at.isoformat() if agent.last_command_at else None
			))
			await db.commit()
    
	async def get_agent(self, agent_id: str) -> Optional[Agent]:
		"""Get an agent by ID"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			async with db.execute(
				"SELECT * FROM agents WHERE id = ?", (agent_id,)
			) as cursor:
				row = await cursor.fetchone()
				if row:
					return self._row_to_agent(row)
				return None
    
	async def get_agent_by_hostname(self, hostname: str) -> Optional[Agent]:
		"""Get an agent by hostname"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			async with db.execute(
				"SELECT * FROM agents WHERE hostname = ?", (hostname,)
			) as cursor:
				row = await cursor.fetchone()
				if row:
					return self._row_to_agent(row)
				return None
    
	async def list_agents(self) -> List[Agent]:
		"""List all agents"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			async with db.execute("SELECT * FROM agents") as cursor:
				rows = await cursor.fetchall()
				return [self._row_to_agent(row) for row in rows]
    
	def _row_to_agent(self, row) -> Agent:
		"""Convert database row to Agent model"""
		def _loads(value):
			return json.loads(value) if value else None

		capabilities = json.loads(row["capabilities"]) if row["capabilities"] else {}
		os_info = _loads(row["os_info"])
		hardware_info = _loads(row["hardware_info"])
		network_info = _loads(row["network_info"])
		docker_info = _loads(row["docker_info"])
		metrics_payload = _loads(row["current_metrics"])
		current_metrics = HostMetrics(**metrics_payload) if metrics_payload else None
		tags = _loads(row["tags"]) or []

		return Agent(
			id=row["id"],
			hostname=row["hostname"],
			capabilities=capabilities,
			status=AgentStatus(row["status"]),
			registered_at=datetime.fromisoformat(row["registered_at"]),
			last_heartbeat=datetime.fromisoformat(row["last_heartbeat"]),
			os_info=os_info,
			hardware_info=hardware_info,
			network_info=network_info,
			docker_info=docker_info,
			current_metrics=current_metrics,
			uptime_seconds=row["uptime_seconds"],
			agent_version=row["agent_version"],
			tags=tags,
			total_commands=row["total_commands"] or 0,
			successful_commands=row["successful_commands"] or 0,
			failed_commands=row["failed_commands"] or 0,
			last_command_at=datetime.fromisoformat(row["last_command_at"]) if row["last_command_at"] else None,
		)

	async def record_agent_metrics(self, agent_id: str, metrics: Optional[HostMetrics]) -> None:
		"""Persist a snapshot of agent metrics"""
		if not metrics:
			return

		payload = metrics.model_dump() if hasattr(metrics, "model_dump") else metrics.dict()
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute(
				"""
				INSERT INTO agent_metrics (agent_id, recorded_at, cpu_percent, mem_percent, disk_free_gb, raw)
				VALUES (?, ?, ?, ?, ?, ?)
				""",
				(
					agent_id,
					datetime.utcnow().isoformat(),
					payload.get("cpu_percent"),
					payload.get("mem_percent"),
					payload.get("disk_free_gb"),
					json.dumps(payload),
				),
			)
			await db.commit()

	async def list_agent_metrics(self, agent_id: str, limit: int = 50) -> List[AgentMetricSample]:
		"""Return recent metrics samples for an agent"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			async with db.execute(
				"""
				SELECT recorded_at, raw
				FROM agent_metrics
				WHERE agent_id = ?
				ORDER BY recorded_at DESC
				LIMIT ?
				""",
				(agent_id, limit),
			) as cursor:
				rows = await cursor.fetchall()
				samples: List[AgentMetricSample] = []
				for row in rows:
					payload = json.loads(row["raw"]) if row["raw"] else {}
					metrics_obj = HostMetrics(**payload) if payload else HostMetrics()
					samples.append(
						AgentMetricSample(
							recorded_at=datetime.fromisoformat(row["recorded_at"]),
							metrics=metrics_obj,
						)
					)
				return samples

	async def update_agent_command_stats(self, agent_id: str, success: bool) -> None:
		"""Increment command counters for an agent"""
		now = datetime.utcnow().isoformat()
		success_inc = 1 if success else 0
		failure_inc = 0 if success else 1
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute(
				"""
				UPDATE agents
				SET total_commands = COALESCE(total_commands, 0) + 1,
					successful_commands = COALESCE(successful_commands, 0) + ?,
					failed_commands = COALESCE(failed_commands, 0) + ?,
					last_command_at = ?
				WHERE id = ?
				""",
				(success_inc, failure_inc, now, agent_id),
			)
			await db.commit()

	# Job operations
	async def save_job(self, job: Job) -> None:
		"""Save or update a job"""
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute(
				"""
				INSERT OR REPLACE INTO jobs 
				(id, job_type, repo, ref, host, status, metadata, deployment_id, deployment_spec,
				 created_at, started_at, completed_at, assigned_agent, error)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			""",
				(
					job.id,
					job.job_type,
					job.repo,
					job.ref,
					job.host,
					job.status.value,
					json.dumps(job.metadata or {}),
					job.deployment_id,
					json.dumps(job.deployment_spec) if job.deployment_spec is not None else None,
					job.created_at.isoformat(),
					job.started_at.isoformat() if job.started_at else None,
					job.completed_at.isoformat() if job.completed_at else None,
					job.assigned_agent,
					job.error,
				),
			)
			await db.commit()
    
	async def get_job(self, job_id: str) -> Optional[Job]:
		"""Get a job by ID"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			async with db.execute(
				"SELECT * FROM jobs WHERE id = ?", (job_id,)
			) as cursor:
				row = await cursor.fetchone()
				if row:
					return self._row_to_job(row)
				return None
    
	async def list_jobs(self, status: Optional[JobStatus] = None) -> List[Job]:
		"""List jobs, optionally filtered by status"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			if status:
				query = "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC"
				params = (status.value,)
			else:
				query = "SELECT * FROM jobs ORDER BY created_at DESC"
				params = ()
            
			async with db.execute(query, params) as cursor:
				rows = await cursor.fetchall()
				return [self._row_to_job(row) for row in rows]
    
	async def find_running_job(self, repo: Optional[str], ref: Optional[str], host: str) -> Optional[Job]:
		"""Find a running job for the same repo+ref+host (for idempotency)"""
		if not repo or not ref:
			return None

		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			async with db.execute(
				"""
				SELECT * FROM jobs 
				WHERE job_type = 'deploy' AND repo = ? AND ref = ? AND host = ? AND status = ?
				LIMIT 1
			""",
				(repo, ref, host, JobStatus.RUNNING.value),
			) as cursor:
				row = await cursor.fetchone()
				if row:
					return self._row_to_job(row)
				return None
    
	def _row_to_job(self, row) -> Job:
		"""Convert database row to Job model"""
		metadata_raw = row["metadata"] if row["metadata"] else "{}"
		deployment_spec = row["deployment_spec"]
		return Job(
			id=row["id"],
			job_type=row["job_type"] if "job_type" in row.keys() and row["job_type"] else "deploy",
			repo=row["repo"],
			ref=row["ref"],
			host=row["host"],
			status=JobStatus(row["status"]),
			metadata=json.loads(metadata_raw),
			deployment_id=row["deployment_id"] if "deployment_id" in row.keys() else None,
			deployment_spec=json.loads(deployment_spec) if deployment_spec else None,
			created_at=datetime.fromisoformat(row["created_at"]),
			started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
			completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
			assigned_agent=row["assigned_agent"],
			error=row["error"],
		)

	# Deployment operations
	async def create_deployment(
		self,
		name: str,
		kind: str,
		spec: Dict[str, Any],
		description: Optional[str] = None,
		tags: Optional[Iterable[str]] = None
	) -> DeploymentRecord:
		deployment_id = str(uuid.uuid4())
		now = datetime.utcnow()
		tags_list = self._normalize_tags(tags)
		spec_json = self._serialize_json(spec)
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute(
				"""
				INSERT INTO deployments (id, name, kind, spec, description, tags, created_at, updated_at)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?)
			""",
				(
					deployment_id,
					name,
					kind,
					spec_json,
					description,
					json.dumps(tags_list),
					now.isoformat(),
					now.isoformat(),
				),
			)
			await db.commit()

		return DeploymentRecord(
			id=deployment_id,
			name=name,
			kind=kind,
			spec=json.loads(spec_json),
			description=description,
			tags=tags_list,
			created_at=now,
			updated_at=now,
		)

	async def update_deployment(
		self,
		deployment_id: str,
		*,
		name: Optional[str] = None,
		description: Optional[str] = None,
		tags: Optional[Iterable[str]] = None,
		spec: Optional[Dict[str, Any]] = None
	) -> Optional[DeploymentRecord]:
		update_fields = {}
		if name is not None:
			update_fields["name"] = name
		if description is not None:
			update_fields["description"] = description
		if tags is not None:
			update_fields["tags"] = json.dumps(self._normalize_tags(tags))
		if spec is not None:
			update_fields["spec"] = self._serialize_json(spec)

		if not update_fields:
			return await self.get_deployment(deployment_id)

		update_fields["updated_at"] = datetime.utcnow().isoformat()

		set_clause = ", ".join(f"{field} = ?" for field in update_fields.keys())
		values = list(update_fields.values())
		values.append(deployment_id)

		async with aiosqlite.connect(self.db_path) as db:
			await db.execute(
				f"UPDATE deployments SET {set_clause} WHERE id = ?",
				tuple(values),
			)
			await db.commit()

		return await self.get_deployment(deployment_id)

	async def get_deployment(self, deployment_id: str) -> Optional[DeploymentRecord]:
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			async with db.execute(
				"SELECT * FROM deployments WHERE id = ?",
				(deployment_id,),
			) as cursor:
				row = await cursor.fetchone()
				if row:
					return self._row_to_deployment(row)
				return None

	async def list_deployments(self) -> List[DeploymentRecord]:
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			async with db.execute(
				"SELECT * FROM deployments ORDER BY updated_at DESC, name ASC"
			) as cursor:
				rows = await cursor.fetchall()
				return [self._row_to_deployment(row) for row in rows]

	async def delete_deployment(self, deployment_id: str) -> None:
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute("DELETE FROM deployments WHERE id = ?", (deployment_id,))
			await db.commit()

	async def clone_deployment(self, deployment_id: str, *, name: Optional[str] = None) -> Optional[DeploymentRecord]:
		existing = await self.get_deployment(deployment_id)
		if not existing:
			return None

		clone_name = name or f"{existing.name} Copy"
		return await self.create_deployment(
			name=clone_name,
			kind=existing.kind,
			spec=existing.spec,
			description=existing.description,
			tags=existing.tags,
		)

	# Command library operations
	async def create_command(
		self,
		name: str,
		command: str,
		description: Optional[str] = None,
		tags: Optional[Iterable[str]] = None,
		runtime: str = "shell",
		*,
		is_system: bool = False,
	) -> CommandTemplate:
		command_id = str(uuid.uuid4())
		now = datetime.utcnow()
		tags_list = self._normalize_tags(tags)
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute(
				"""
				INSERT INTO commands (id, name, command, description, tags, is_system, runtime, created_at, updated_at)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
			""",
				(
					command_id,
					name,
					command,
					description,
					json.dumps(tags_list),
					1 if is_system else 0,
					runtime,
					now.isoformat(),
					now.isoformat(),
				),
			)
			await db.commit()

		return CommandTemplate(
			id=command_id,
			name=name,
			command=command,
			description=description,
			tags=tags_list,
			is_system=is_system,
			runtime=runtime,
			created_at=now,
			updated_at=now,
		)

	async def update_command(
		self,
		command_id: str,
		*,
		name: Optional[str] = None,
		command: Optional[str] = None,
		description: Optional[str] = None,
		tags: Optional[Iterable[str]] = None,
		runtime: Optional[str] = None
	) -> Optional[CommandTemplate]:
		update_fields = {}
		if name is not None:
			update_fields["name"] = name
		if command is not None:
			update_fields["command"] = command
		if description is not None:
			update_fields["description"] = description
		if tags is not None:
			update_fields["tags"] = json.dumps(self._normalize_tags(tags))
		if runtime is not None:
			update_fields["runtime"] = runtime

		if not update_fields:
			return await self.get_command(command_id)

		update_fields["updated_at"] = datetime.utcnow().isoformat()

		set_clause = ", ".join(f"{field} = ?" for field in update_fields.keys())
		values = list(update_fields.values())
		values.append(command_id)

		async with aiosqlite.connect(self.db_path) as db:
			await db.execute(
				f"UPDATE commands SET {set_clause} WHERE id = ?",
				tuple(values),
			)
			await db.commit()

		return await self.get_command(command_id)

	async def list_commands(self, include_system: bool = True) -> List[CommandTemplate]:
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			query = "SELECT * FROM commands"
			params: List[Any] = []
			if not include_system:
				query += " WHERE is_system = 0"
			query += " ORDER BY is_system DESC, updated_at DESC"
			async with db.execute(query, tuple(params)) as cursor:
				rows = await cursor.fetchall()
				return [self._row_to_command(row) for row in rows]

	async def get_command(self, command_id: str) -> Optional[CommandTemplate]:
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			async with db.execute(
				"SELECT * FROM commands WHERE id = ?",
				(command_id,),
			) as cursor:
				row = await cursor.fetchone()
				if row:
					return self._row_to_command(row)
				return None

	async def delete_command(self, command_id: str) -> None:
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute("DELETE FROM commands WHERE id = ? AND is_system = 0", (command_id,))
			await db.commit()
    
	# Log operations
	async def save_log(self, log_entry: LogEntry) -> None:
		"""Save a log entry"""
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute("""
				INSERT INTO logs (timestamp, job_id, host, app, level, message)
				VALUES (?, ?, ?, ?, ?, ?)
			""", (
				log_entry.timestamp.isoformat(),
				log_entry.job_id,
				log_entry.host,
				log_entry.app,
				log_entry.level,
				log_entry.message
			))
			await db.commit()
    
	async def get_logs(
		self, 
		host: Optional[str] = None, 
		app: Optional[str] = None,
		limit: int = 100
	) -> List[LogEntry]:
		"""Get logs, optionally filtered by host and/or app"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
            
			query = "SELECT * FROM logs WHERE 1=1"
			params = []
            
			if host:
				query += " AND host = ?"
				params.append(host)
            
			if app:
				query += " AND app = ?"
				params.append(app)
            
			query += f" ORDER BY timestamp DESC LIMIT {limit}"
            
			async with db.execute(query, params) as cursor:
				rows = await cursor.fetchall()
				return [self._row_to_log(row) for row in rows]
    
	def _row_to_log(self, row) -> LogEntry:
		"""Convert database row to LogEntry model"""
		return LogEntry(
			timestamp=datetime.fromisoformat(row["timestamp"]),
			job_id=row["job_id"],
			host=row["host"],
			app=row["app"],
			level=row["level"],
			message=row["message"]
		)
    
	# Chat session operations
	async def create_chat_session(self, session_id: str, user_id: str = "default", name: Optional[str] = None) -> None:
		"""Create a new chat session"""
		async with aiosqlite.connect(self.db_path) as db:
			now = datetime.utcnow().isoformat()
			await db.execute("""
				INSERT INTO chat_sessions (id, user_id, name, created_at, last_activity)
				VALUES (?, ?, ?, ?, ?)
			""", (session_id, user_id, name, now, now))
			await db.commit()
    
	async def get_chat_session(self, session_id: str) -> Optional[Dict[str, Any]]:
		"""Get a chat session by ID"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			async with db.execute(
				"SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
			) as cursor:
				row = await cursor.fetchone()
				if row:
					return dict(row)
				return None
    
	async def list_chat_sessions(self, user_id: str = "default", include_archived: bool = False) -> List[Dict[str, Any]]:
		"""List chat sessions for a user"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
            
			query = "SELECT * FROM chat_sessions WHERE user_id = ?"
			params = [user_id]
            
			if not include_archived:
				query += " AND archived = 0"
            
			query += " ORDER BY last_activity DESC"
            
			async with db.execute(query, params) as cursor:
				rows = await cursor.fetchall()
				return [dict(row) for row in rows]
    
	async def update_session_activity(self, session_id: str) -> None:
		"""Update the last activity timestamp for a session"""
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute("""
				UPDATE chat_sessions 
				SET last_activity = ? 
				WHERE id = ?
			""", (datetime.utcnow().isoformat(), session_id))
			await db.commit()
    
	async def archive_chat_session(self, session_id: str) -> None:
		"""Archive a chat session"""
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute("""
				UPDATE chat_sessions 
				SET archived = 1, archived_at = ? 
				WHERE id = ?
			""", (datetime.utcnow().isoformat(), session_id))
			await db.commit()
    
	async def unarchive_chat_session(self, session_id: str) -> None:
		"""Unarchive a chat session"""
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute("""
				UPDATE chat_sessions 
				SET archived = 0, archived_at = NULL 
				WHERE id = ?
			""", (session_id,))
			await db.commit()
    
	async def delete_chat_session(self, session_id: str) -> None:
		"""Delete a chat session and all its messages"""
		async with aiosqlite.connect(self.db_path) as db:
			# Delete messages first (foreign key)
			await db.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
			# Then delete session
			await db.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
			await db.commit()
    
	async def save_chat_message(
		self, 
		session_id: str, 
		role: str, 
		content: str,
		metadata: Optional[Dict[str, Any]] = None
	) -> None:
		"""Save a chat message to a session"""
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute("""
				INSERT INTO chat_messages (session_id, role, content, timestamp, metadata)
				VALUES (?, ?, ?, ?, ?)
			""", (
				session_id,
				role,
				content,
				datetime.utcnow().isoformat(),
				json.dumps(metadata) if metadata else None
			))
			await db.commit()
            
			# Update session activity
			await self.update_session_activity(session_id)
    
	async def get_chat_history(
		self, 
		session_id: str,
		limit: Optional[int] = None
	) -> List[Dict[str, Any]]:
		"""Get chat history for a session"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
            
			query = "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY timestamp ASC"
			params = [session_id]
            
			if limit:
				query += f" LIMIT {limit}"
            
			async with db.execute(query, params) as cursor:
				rows = await cursor.fetchall()
				messages = []
				for row in rows:
					msg = dict(row)
					if msg.get('metadata'):
						msg['metadata'] = json.loads(msg['metadata'])
					messages.append(msg)
				return messages

	# Docker Template Operations
	async def save_docker_template(self, template: DockerImageTemplate) -> None:
		"""Save Docker image template"""
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute("""
				INSERT OR REPLACE INTO docker_templates (
					id, name, image, tag, description, category,
					ports, volumes, environment, health_check,
					is_system, usage_notes, created_at, updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			""", (
				template.id, template.name, template.image, template.tag,
				template.description, template.category,
				json.dumps([p.model_dump() for p in template.ports]),
				json.dumps([v.model_dump() for v in template.volumes]),
				json.dumps([e.model_dump() for e in template.environment]),
				json.dumps(template.health_check.model_dump()) if template.health_check else None,
				template.is_system, template.usage_notes,
				template.created_at.isoformat(), template.updated_at.isoformat()
			))
			await db.commit()

	async def list_docker_templates(self, category: Optional[str] = None) -> List[DockerImageTemplate]:
		"""List Docker image templates"""
		async with aiosqlite.connect(self.db_path) as db:
			query = "SELECT * FROM docker_templates"
			params = []
			if category:
				query += " WHERE category = ?"
				params.append(category)
			query += " ORDER BY name"
			
			async with db.execute(query, params) as cursor:
				rows = await cursor.fetchall()
				return [self._row_to_docker_template(row) for row in rows]

	async def get_docker_template(self, template_id: str) -> Optional[DockerImageTemplate]:
		"""Get Docker template by ID"""
		async with aiosqlite.connect(self.db_path) as db:
			async with db.execute("SELECT * FROM docker_templates WHERE id = ?", (template_id,)) as cursor:
				row = await cursor.fetchone()
				return self._row_to_docker_template(row) if row else None

	async def delete_docker_template(self, template_id: str) -> bool:
		"""Delete Docker template"""
		async with aiosqlite.connect(self.db_path) as db:
			async with db.execute("DELETE FROM docker_templates WHERE id = ?", (template_id,)) as cursor:
				await db.commit()
				return cursor.rowcount > 0

	def _row_to_docker_template(self, row) -> DockerImageTemplate:
		"""Convert database row to DockerImageTemplate"""
		return DockerImageTemplate(
			id=row["id"],
			name=row["name"],
			image=row["image"],
			tag=row["tag"],
			description=row["description"],
			category=row["category"],
			ports=[PortMapping(**p) for p in json.loads(row["ports"] or "[]")],
			volumes=[VolumeMapping(**v) for v in json.loads(row["volumes"] or "[]")],
			environment=[EnvironmentVariable(**e) for e in json.loads(row["environment"] or "[]")],
			health_check=HealthCheckConfig(**json.loads(row["health_check"])) if row["health_check"] else None,
			is_system=bool(row["is_system"]),
			usage_notes=row["usage_notes"],
			created_at=datetime.fromisoformat(row["created_at"]),
			updated_at=datetime.fromisoformat(row["updated_at"])
		)

	# Toast Notification Operations
	async def save_notification(self, notification: ToastNotification) -> None:
		"""Save toast notification"""
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute("""
				INSERT INTO notifications (
					id, type, title, message, agent_id, job_id,
					timestamp, auto_dismiss, timeout_seconds, actions
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			""", (
				notification.id, notification.type, notification.title,
				notification.message, notification.agent_id, notification.job_id,
				notification.timestamp.isoformat(), notification.auto_dismiss,
				notification.timeout_seconds, json.dumps(notification.actions)
			))
			await db.commit()

	async def list_notifications(self, limit: int = 50, agent_id: Optional[str] = None) -> List[ToastNotification]:
		"""List recent notifications"""
		async with aiosqlite.connect(self.db_path) as db:
			query = "SELECT * FROM notifications WHERE is_dismissed = 0"
			params = []
			if agent_id:
				query += " AND agent_id = ?"
				params.append(agent_id)
			query += " ORDER BY timestamp DESC LIMIT ?"
			params.append(limit)
			
			async with db.execute(query, params) as cursor:
				rows = await cursor.fetchall()
				return [self._row_to_notification(row) for row in rows]

	async def dismiss_notification(self, notification_id: str) -> bool:
		"""Dismiss a notification"""
		async with aiosqlite.connect(self.db_path) as db:
			async with db.execute("""
				UPDATE notifications 
				SET dismissed = 1, dismissed_at = ?
				WHERE id = ?
			""", (datetime.utcnow().isoformat(), notification_id)) as cursor:
				await db.commit()
				return cursor.rowcount > 0

	def _row_to_notification(self, row) -> ToastNotification:
		"""Convert database row to ToastNotification"""
		return ToastNotification(
			id=row["id"],
			type=row["type"],
			title=row["title"],
			message=row["message"],
			agent_id=row["agent_id"],
			job_id=row["job_id"],
			timestamp=datetime.fromisoformat(row["timestamp"]),
			auto_dismiss=bool(row["auto_dismiss"]),
			timeout_seconds=row["timeout_seconds"],
			actions=json.loads(row["actions"] or "[]")
		)

	def _row_to_deployment(self, row) -> DeploymentRecord:
		"""Convert row to deployment record"""
		tags = json.loads(row["tags"]) if row["tags"] else []
		spec = json.loads(row["spec"]) if row["spec"] else {}
		return DeploymentRecord(
			id=row["id"],
			name=row["name"],
			kind=row["kind"],
			spec=spec,
			description=row["description"],
			tags=tags,
			created_at=datetime.fromisoformat(row["created_at"]),
			updated_at=datetime.fromisoformat(row["updated_at"]),
		)

	def _row_to_command(self, row) -> CommandTemplate:
		"""Convert row to command template"""
		tags = json.loads(row["tags"]) if row["tags"] else []
		return CommandTemplate(
			id=row["id"],
			name=row["name"],
			command=row["command"],
			description=row["description"],
			tags=tags,
			is_system=bool(row["is_system"]),
			runtime=row["runtime"],
			created_at=datetime.fromisoformat(row["created_at"]),
			updated_at=datetime.fromisoformat(row["updated_at"]),
		)

	def _normalize_tags(self, tags: Optional[Iterable[str]]) -> List[str]:
		if not tags:
			return []
		normalized = []
		for tag in tags:
			if tag is None:
				continue
			text = str(tag).strip()
			if text:
				normalized.append(text)
		return normalized

	def _serialize_json(self, value: Any) -> str:
		if hasattr(value, "model_dump"):
			value = value.model_dump(mode="json")
		if value is None:
			value = {}
		return json.dumps(value)

	# Docker Template operations
	async def save_docker_template(self, template: DockerImageTemplate) -> None:
		"""Save or update a Docker template"""
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute("""
				INSERT OR REPLACE INTO docker_templates 
				(id, name, image, description, ports, volumes, environment, health_check, tags, is_system, created_at, updated_at)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			""", (
				template.id,
				template.name,
				template.image,
				template.description,
				json.dumps(template.ports),
				json.dumps(template.volumes),
				json.dumps(template.environment),
				json.dumps(template.health_check),
				json.dumps(template.tags),
				template.is_system,
				template.created_at.isoformat(),
				template.updated_at.isoformat()
			))
			await db.commit()

	async def list_docker_templates(self, limit: int = 100, offset: int = 0) -> List[DockerImageTemplate]:
		"""List Docker templates with pagination"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			async with db.execute("""
				SELECT * FROM docker_templates 
				ORDER BY is_system DESC, name ASC 
				LIMIT ? OFFSET ?
			""", (limit, offset)) as cursor:
				rows = await cursor.fetchall()
				return [self._row_to_docker_template(row) for row in rows]

	async def get_docker_template(self, template_id: str) -> Optional[DockerImageTemplate]:
		"""Get a Docker template by ID"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			async with db.execute(
				"SELECT * FROM docker_templates WHERE id = ?", (template_id,)
			) as cursor:
				row = await cursor.fetchone()
				return self._row_to_docker_template(row) if row else None

	async def delete_docker_template(self, template_id: str) -> bool:
		"""Delete a Docker template by ID"""
		async with aiosqlite.connect(self.db_path) as db:
			cursor = await db.execute(
				"DELETE FROM docker_templates WHERE id = ? AND is_system = 0", (template_id,)
			)
			await db.commit()
			return cursor.rowcount > 0

	# Notification operations
	async def save_notification(self, notification: ToastNotification) -> None:
		"""Save a notification"""
		async with aiosqlite.connect(self.db_path) as db:
			await db.execute("""
				INSERT OR REPLACE INTO notifications 
				(id, type, title, message, agent_id, job_id, timestamp, auto_dismiss, timeout_seconds, actions, is_dismissed)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			""", (
				notification.id,
				notification.type,
				notification.title,
				notification.message,
				notification.agent_id,
				notification.job_id,
				notification.timestamp.isoformat(),
				notification.auto_dismiss,
				notification.timeout_seconds,
				json.dumps(notification.actions),
				False  # Default to not dismissed
			))
			await db.commit()

	async def list_notifications(self, agent_id: Optional[str] = None, include_dismissed: bool = False, limit: int = 50) -> List[ToastNotification]:
		"""List notifications with optional filtering"""
		async with aiosqlite.connect(self.db_path) as db:
			db.row_factory = aiosqlite.Row
			
			query = "SELECT * FROM notifications WHERE 1=1"
			params = []
			
			if agent_id:
				query += " AND agent_id = ?"
				params.append(agent_id)
			
			if not include_dismissed:
				query += " AND is_dismissed = 0"
			
			query += " ORDER BY timestamp DESC LIMIT ?"
			params.append(limit)
			
			async with db.execute(query, params) as cursor:
				rows = await cursor.fetchall()
				return [self._row_to_notification(row) for row in rows]

	async def dismiss_notification(self, notification_id: str) -> bool:
		"""Mark a notification as dismissed"""
		async with aiosqlite.connect(self.db_path) as db:
			cursor = await db.execute(
				"UPDATE notifications SET is_dismissed = 1 WHERE id = ?", (notification_id,)
			)
			await db.commit()
			return cursor.rowcount > 0

	def _row_to_notification(self, row: aiosqlite.Row) -> ToastNotification:
		"""Convert database row to ToastNotification"""
		return ToastNotification(
			id=row["id"],
			type=row["type"],
			title=row["title"],
			message=row["message"],
			agent_id=row["agent_id"],
			job_id=row["job_id"],
			timestamp=datetime.fromisoformat(row["timestamp"]),
			auto_dismiss=bool(row["auto_dismiss"]),
			timeout_seconds=row["timeout_seconds"],
			actions=json.loads(row["actions"]) if row["actions"] else [],
		)
