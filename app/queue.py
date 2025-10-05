"""
In-memory job queue with SQLite persistence for recovery
"""
import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, List
from collections import deque

from app.models import Job, JobCreate, JobStatus
from app.store import Store


class JobQueue:
    """In-memory job queue with persistence"""
    
    def __init__(self, store: Store):
        self.store = store
        self.pending_queue: deque = deque()
        self.jobs: Dict[str, Job] = {}
        self._lock = asyncio.Lock()
    
    async def initialize(self):
        """Load pending and running jobs from database on startup"""
        pending_jobs = await self.store.list_jobs(JobStatus.PENDING)
        running_jobs = await self.store.list_jobs(JobStatus.RUNNING)
        
        # Re-queue pending jobs
        for job in pending_jobs:
            self.jobs[job.id] = job
            self.pending_queue.append(job.id)
        
        # Keep running jobs in memory (agent will report back)
        for job in running_jobs:
            self.jobs[job.id] = job
    
    async def enqueue(self, job_create: JobCreate) -> Job:
        """
        Create and enqueue a new job.
        Returns existing job if idempotency check finds running job.
        """
        async with self._lock:
            # Idempotency check: if same repo+ref+host is running, return it
            existing_job = await self.store.find_running_job(
                job_create.repo,
                job_create.ref,
                job_create.host
            )
            
            if existing_job:
                return existing_job
            
            # Create new job
            job = Job(
                id=str(uuid.uuid4()),
                repo=job_create.repo,
                ref=job_create.ref,
                host=job_create.host,
                metadata=job_create.metadata,
                status=JobStatus.PENDING,
                created_at=datetime.utcnow()
            )
            
            # Save to store
            await self.store.save_job(job)
            
            # Add to in-memory queue
            self.jobs[job.id] = job
            self.pending_queue.append(job.id)
            
            return job
    
    async def get_next_job_for_host(self, hostname: str) -> Optional[Job]:
        """
        Get the next pending job for a specific host.
        Returns at most 1 job per agent per heartbeat.
        """
        async with self._lock:
            # Find first pending job for this host
            for job_id in list(self.pending_queue):
                job = self.jobs.get(job_id)
                if job and job.host == hostname and job.status == JobStatus.PENDING:
                    # Mark as running
                    job.status = JobStatus.RUNNING
                    job.started_at = datetime.utcnow()
                    
                    # Remove from pending queue
                    self.pending_queue.remove(job_id)
                    
                    # Persist
                    await self.store.save_job(job)
                    
                    return job
            
            return None
    
    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID"""
        # Try memory first
        if job_id in self.jobs:
            return self.jobs[job_id]
        
        # Fall back to database
        job = await self.store.get_job(job_id)
        if job:
            self.jobs[job_id] = job
        return job
    
    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error: Optional[str] = None
    ) -> Optional[Job]:
        """Update job status"""
        async with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                job = await self.store.get_job(job_id)
                if job:
                    self.jobs[job_id] = job
            
            if not job:
                return None
            
            job.status = status
            if error:
                job.error = error
            
            if status in [JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED]:
                job.completed_at = datetime.utcnow()
            
            await self.store.save_job(job)
            return job
    
    async def list_jobs(self) -> List[Job]:
        """List all jobs"""
        return await self.store.list_jobs()
