"""
SQLite-based persistence layer for DeployBot Controller
"""
import aiosqlite
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from app.models import Agent, Job, JobStatus, AgentStatus, LogEntry


class Store:
    """SQLite-based storage for agents, jobs, and logs"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    async def init_db(self):
        """Initialize database schema"""
        async with aiosqlite.connect(self.db_path) as db:
            # Agents table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    hostname TEXT NOT NULL,
                    capabilities TEXT,
                    status TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    last_heartbeat TEXT NOT NULL
                )
            """)
            
            # Jobs table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    repo TEXT NOT NULL,
                    ref TEXT NOT NULL,
                    host TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    assigned_agent TEXT,
                    error TEXT
                )
            """)
            
            # Create index for idempotency checks
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_lookup 
                ON jobs(repo, ref, host, status)
            """)
            
            # Logs table
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
            
            # Chat sessions table
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
            
            # Chat messages table
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
            
            # Create indices for chat queries
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session 
                ON chat_messages(session_id, timestamp)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user 
                ON chat_sessions(user_id, archived, last_activity DESC)
            """)
            
            await db.commit()
    
    # Agent operations
    async def save_agent(self, agent: Agent) -> None:
        """Save or update an agent"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO agents 
                (id, hostname, capabilities, status, registered_at, last_heartbeat)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                agent.id,
                agent.hostname,
                json.dumps(agent.capabilities),
                agent.status.value,
                agent.registered_at.isoformat(),
                agent.last_heartbeat.isoformat()
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
        return Agent(
            id=row["id"],
            hostname=row["hostname"],
            capabilities=json.loads(row["capabilities"]),
            status=AgentStatus(row["status"]),
            registered_at=datetime.fromisoformat(row["registered_at"]),
            last_heartbeat=datetime.fromisoformat(row["last_heartbeat"])
        )
    
    # Job operations
    async def save_job(self, job: Job) -> None:
        """Save or update a job"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO jobs 
                (id, repo, ref, host, status, metadata, created_at, started_at, 
                 completed_at, assigned_agent, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.id,
                job.repo,
                job.ref,
                job.host,
                job.status.value,
                json.dumps(job.metadata),
                job.created_at.isoformat(),
                job.started_at.isoformat() if job.started_at else None,
                job.completed_at.isoformat() if job.completed_at else None,
                job.assigned_agent,
                job.error
            ))
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
    
    async def find_running_job(self, repo: str, ref: str, host: str) -> Optional[Job]:
        """Find a running job for the same repo+ref+host (for idempotency)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM jobs 
                WHERE repo = ? AND ref = ? AND host = ? AND status = ?
                LIMIT 1
            """, (repo, ref, host, JobStatus.RUNNING.value)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_job(row)
                return None
    
    def _row_to_job(self, row) -> Job:
        """Convert database row to Job model"""
        return Job(
            id=row["id"],
            repo=row["repo"],
            ref=row["ref"],
            host=row["host"],
            status=JobStatus(row["status"]),
            metadata=json.loads(row["metadata"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            assigned_agent=row["assigned_agent"],
            error=row["error"]
        )
    
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
