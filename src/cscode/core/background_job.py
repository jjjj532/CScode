from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """A background job."""

    job_type: str
    params: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: JobStatus = JobStatus.PENDING
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return end - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status.value,
            "params": self.params,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration": self.duration,
        }


JobHandler = Callable[["Job"], Awaitable[Any]]


class JobStore:
    """In-memory job store with async access."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def add(self, job: Job) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def get(self, job_id: str) -> Job | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job: Job) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def list(
        self,
        status: JobStatus | None = None,
        job_type: str | None = None,
        limit: int = 50,
    ) -> list[Job]:
        async with self._lock:
            jobs = list(self._jobs.values())
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        if job_type is not None:
            jobs = [j for j in jobs if j.job_type == job_type]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    async def remove(self, job_id: str) -> bool:
        async with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    async def clear(self) -> None:
        async with self._lock:
            self._jobs.clear()


class BackgroundJobQueue:
    """Background job queue with in-memory storage and async execution."""

    def __init__(self, store: JobStore | None = None) -> None:
        self.store = store or JobStore()
        self._handlers: dict[str, JobHandler] = {}
        self._running = False
        self._worker_task: asyncio.Task[Any] | None = None
        self._pending: asyncio.Queue[Job] = asyncio.Queue()

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        """Register a handler for a job type."""
        self._handlers[job_type] = handler
        logger.debug("Registered handler for job type: %s", job_type)

    async def enqueue(
        self,
        job_type: str,
        params: dict[str, Any] | None = None,
    ) -> Job:
        """Enqueue a new background job."""
        job = Job(job_type=job_type, params=params or {})
        await self.store.add(job)
        await self._pending.put(job)
        logger.info("Enqueued job: %s (%s)", job.id, job_type)
        return job

    async def get_job(self, job_id: str) -> Job | None:
        return await self.store.get(job_id)

    async def list_jobs(
        self,
        status: JobStatus | None = None,
        job_type: str | None = None,
        limit: int = 50,
    ) -> list[Job]:
        return await self.store.list(status=status, job_type=job_type, limit=limit)

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or running job."""
        job = await self.store.get(job_id)
        if job is None:
            return False
        if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
            job.status = JobStatus.CANCELLED
            await self.store.update(job)
            logger.info("Cancelled job: %s", job_id)
            return True
        return False

    async def start(self) -> None:
        """Start the background worker."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Background job worker started")

    async def stop(self) -> None:
        """Stop the background worker."""
        self._running = False
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        logger.info("Background job worker stopped")

    async def _worker_loop(self) -> None:
        """Main worker loop - processes jobs from the queue."""
        while self._running:
            try:
                job = await asyncio.wait_for(self._pending.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            await self._execute_job(job)

    async def _execute_job(self, job: Job) -> None:
        """Execute a single job."""
        handler = self._handlers.get(job.job_type)
        if handler is None:
            job.status = JobStatus.FAILED
            job.error = f"No handler registered for job type: {job.job_type}"
            job.completed_at = time.time()
            await self.store.update(job)
            logger.error("No handler for job type: %s", job.job_type)
            return

        job.status = JobStatus.RUNNING
        job.started_at = time.time()
        await self.store.update(job)
        logger.info("Running job: %s (%s)", job.id, job.job_type)

        try:
            result = await handler(job)
            job.status = JobStatus.COMPLETED
            job.result = result
        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = f"{type(e).__name__}: {e}"
            logger.exception("Job failed: %s", job.id)
        finally:
            job.completed_at = time.time()
            await self.store.update(job)
            logger.info(
                "Job finished: %s status=%s duration=%.2fs",
                job.id,
                job.status.value,
                job.duration or 0,
            )
