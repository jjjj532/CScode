from __future__ import annotations

import asyncio
import time

import pytest

from cscode.core.background_job import (
    BackgroundJobQueue,
    Job,
    JobStatus,
    JobStore,
)


class TestJob:
    def test_create_job(self) -> None:
        job = Job(job_type="test", params={"key": "value"})
        assert job.job_type == "test"
        assert job.params == {"key": "value"}
        assert job.status == JobStatus.PENDING
        assert job.id is not None
        assert len(job.id) == 12

    def test_duration_not_started(self) -> None:
        job = Job(job_type="test")
        assert job.duration is None

    def test_duration_running(self) -> None:
        job = Job(job_type="test", started_at=time.time() - 5)
        assert job.duration is not None
        assert job.duration >= 4.9

    def test_duration_completed(self) -> None:
        now = time.time()
        job = Job(
            job_type="test",
            started_at=now - 10,
            completed_at=now - 2,
        )
        assert job.duration is not None
        assert job.duration == pytest.approx(8.0, abs=0.1)

    def test_to_dict(self) -> None:
        job = Job(job_type="email", params={"to": "user@example.com"})
        d = job.to_dict()
        assert d["job_type"] == "email"
        assert d["status"] == "pending"
        assert d["params"] == {"to": "user@example.com"}
        assert d["error"] is None

    def test_to_dict_completed(self) -> None:
        job = Job(
            job_type="report",
            status=JobStatus.COMPLETED,
            result="OK",
            started_at=100.0,
            completed_at=105.0,
        )
        d = job.to_dict()
        assert d["status"] == "completed"
        assert d["result"] == "OK"
        assert d["duration"] == 5.0


class TestJobStore:
    @pytest.fixture
    def store(self) -> JobStore:
        return JobStore()

    async def test_add_and_get(self, store: JobStore) -> None:
        job = Job(job_type="test")
        await store.add(job)
        retrieved = await store.get(job.id)
        assert retrieved is not None
        assert retrieved.id == job.id
        assert retrieved.job_type == "test"

    async def test_get_not_found(self, store: JobStore) -> None:
        result = await store.get("nonexistent")
        assert result is None

    async def test_update(self, store: JobStore) -> None:
        job = Job(job_type="test")
        await store.add(job)
        job.status = JobStatus.RUNNING
        await store.update(job)
        retrieved = await store.get(job.id)
        assert retrieved is not None
        assert retrieved.status == JobStatus.RUNNING

    async def test_list(self, store: JobStore) -> None:
        for i in range(5):
            await store.add(Job(job_type="test", params={"i": i}))
        jobs = await store.list()
        assert len(jobs) == 5

    async def test_list_filter_status(self, store: JobStore) -> None:
        job1 = Job(job_type="test", status=JobStatus.COMPLETED)
        job2 = Job(job_type="test", status=JobStatus.FAILED)
        await store.add(job1)
        await store.add(job2)
        completed = await store.list(status=JobStatus.COMPLETED)
        failed = await store.list(status=JobStatus.FAILED)
        assert len(completed) == 1
        assert len(failed) == 1

    async def test_list_filter_job_type(self, store: JobStore) -> None:
        await store.add(Job(job_type="email"))
        await store.add(Job(job_type="report"))
        emails = await store.list(job_type="email")
        assert len(emails) == 1

    async def test_list_limit(self, store: JobStore) -> None:
        for i in range(10):
            await store.add(Job(job_type="test"))
        jobs = await store.list(limit=3)
        assert len(jobs) == 3

    async def test_remove(self, store: JobStore) -> None:
        job = Job(job_type="test")
        await store.add(job)
        result = await store.remove(job.id)
        assert result is True
        assert await store.get(job.id) is None

    async def test_remove_not_found(self, store: JobStore) -> None:
        result = await store.remove("nonexistent")
        assert result is False

    async def test_clear(self, store: JobStore) -> None:
        await store.add(Job(job_type="a"))
        await store.add(Job(job_type="b"))
        await store.clear()
        jobs = await store.list()
        assert len(jobs) == 0


class TestBackgroundJobQueue:
    @pytest.fixture
    def queue(self) -> BackgroundJobQueue:
        return BackgroundJobQueue()

    async def test_enqueue(self, queue: BackgroundJobQueue) -> None:
        job = await queue.enqueue("test", {"x": 1})
        assert job.job_type == "test"
        assert job.params == {"x": 1}
        assert job.status == JobStatus.PENDING

    async def test_get_job(self, queue: BackgroundJobQueue) -> None:
        job = await queue.enqueue("test")
        retrieved = await queue.get_job(job.id)
        assert retrieved is not None
        assert retrieved.id == job.id

    async def test_get_job_not_found(self, queue: BackgroundJobQueue) -> None:
        result = await queue.get_job("nonexistent")
        assert result is None

    async def test_list_jobs(self, queue: BackgroundJobQueue) -> None:
        await queue.enqueue("a")
        await queue.enqueue("b")
        jobs = await queue.list_jobs()
        assert len(jobs) == 2

    async def test_cancel_pending(self, queue: BackgroundJobQueue) -> None:
        job = await queue.enqueue("test")
        result = await queue.cancel_job(job.id)
        assert result is True
        cancelled = await queue.get_job(job.id)
        assert cancelled is not None
        assert cancelled.status == JobStatus.CANCELLED

    async def test_cancel_not_found(self, queue: BackgroundJobQueue) -> None:
        result = await queue.cancel_job("nonexistent")
        assert result is False

    async def test_execute_job(self, queue: BackgroundJobQueue) -> None:
        results: list[str] = []

        async def handler(job: Job) -> str:
            results.append("handled")
            return "done"

        queue.register_handler("test", handler)
        await queue.start()

        job = await queue.enqueue("test")
        # Wait for execution
        for _ in range(20):
            current = await queue.get_job(job.id)
            if current and current.status == JobStatus.COMPLETED:
                break
            await asyncio.sleep(0.05)

        await queue.stop()

        assert len(results) == 1
        finished = await queue.get_job(job.id)
        assert finished is not None
        assert finished.status == JobStatus.COMPLETED
        assert finished.result == "done"

    async def test_execute_job_no_handler(self, queue: BackgroundJobQueue) -> None:
        await queue.start()
        job = await queue.enqueue("unknown_type")

        for _ in range(20):
            current = await queue.get_job(job.id)
            if current and current.status != JobStatus.PENDING:
                break
            await asyncio.sleep(0.05)

        await queue.stop()

        finished = await queue.get_job(job.id)
        assert finished is not None
        assert finished.status == JobStatus.FAILED
        assert finished.error is not None
        assert "No handler registered" in finished.error

    async def test_execute_job_failure(self, queue: BackgroundJobQueue) -> None:
        async def handler(job: Job) -> str:
            raise ValueError("something broke")

        queue.register_handler("faulty", handler)
        await queue.start()

        job = await queue.enqueue("faulty")

        for _ in range(20):
            current = await queue.get_job(job.id)
            if current and current.status != JobStatus.PENDING:
                break
            await asyncio.sleep(0.05)

        await queue.stop()

        finished = await queue.get_job(job.id)
        assert finished is not None
        assert finished.status == JobStatus.FAILED
        assert finished.error is not None
        assert "ValueError" in finished.error

    async def test_start_stop(self, queue: BackgroundJobQueue) -> None:
        await queue.start()
        assert queue._running is True
        await queue.stop()
        assert queue._running is False

    async def test_double_start(self, queue: BackgroundJobQueue) -> None:
        await queue.start()
        await queue.start()  # Should be no-op
        assert queue._running is True
        await queue.stop()

    async def test_execute_job_cancelled(self, queue: BackgroundJobQueue) -> None:
        """_execute_job should handle CancelledError gracefully."""
        async def handler(job: Job) -> str:
            raise asyncio.CancelledError()

        queue.register_handler("cancel", handler)
        await queue.start()

        job = await queue.enqueue("cancel")

        for _ in range(20):
            current = await queue.get_job(job.id)
            if current and current.status != JobStatus.PENDING:
                break
            await asyncio.sleep(0.05)

        await queue.stop()

        finished = await queue.get_job(job.id)
        assert finished is not None
        assert finished.status == JobStatus.CANCELLED

    async def test_execute_job_handler_none_result(self, queue: BackgroundJobQueue) -> None:
        """_execute_job should store None result without error."""
        async def handler(job: Job) -> None:
            return None

        queue.register_handler("none", handler)
        await queue.start()

        job = await queue.enqueue("none")

        for _ in range(20):
            current = await queue.get_job(job.id)
            if current and current.status != JobStatus.PENDING:
                break
            await asyncio.sleep(0.05)

        await queue.stop()

        finished = await queue.get_job(job.id)
        assert finished is not None
        assert finished.status == JobStatus.COMPLETED
        assert finished.result is None

    async def test_concurrent_jobs(self, queue: BackgroundJobQueue) -> None:
        """Test that multiple jobs are processed sequentially."""
        execution_order: list[int] = []

        async def handler(job: Job) -> str:
            idx = job.params["idx"]
            await asyncio.sleep(0.05)
            execution_order.append(idx)
            return str(idx)

        queue.register_handler("seq", handler)
        await queue.start()

        for i in range(3):
            await queue.enqueue("seq", {"idx": i})

        await asyncio.sleep(0.5)

        await queue.stop()
        assert execution_order == [0, 1, 2]

    # ─── _worker_loop direct tests ──────────────────────────────────

    async def test_worker_loop_processes_job(self, queue: BackgroundJobQueue) -> None:
        """_worker_loop dequeues a pending job and runs _execute_job."""
        results: list[str] = []

        async def handler(job: Job) -> str:
            results.append("executed")
            return "ok"

        queue.register_handler("test_direct", handler)
        # Inject job directly into pending queue (bypass enqueue)
        job = Job(job_type="test_direct")
        queue._pending.put_nowait(job)
        queue._running = True

        # Run worker loop until it processes the job, then stop
        async def run_until_done() -> None:
            while queue._running:
                await asyncio.sleep(0.01)
                if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                    queue._running = False

        task = asyncio.create_task(run_until_done())
        await queue._worker_loop()
        await task

        assert results == ["executed"]
        assert job.status == JobStatus.COMPLETED

    async def test_worker_loop_timeout_continues(self, queue: BackgroundJobQueue) -> None:
        """_worker_loop handles TimeoutError and continues polling."""
        queue._running = True
        poll_count: list[int] = [0]

        orig_get = queue._pending.get
        async def tracking_get() -> Job:
            poll_count[0] += 1
            return await orig_get()

        queue._pending.get = tracking_get  # type: ignore[assignment]

        # Run loop for a short time, observe at least one timeout cycle
        async def stop_after_timeout() -> None:
            await asyncio.sleep(0.05)
            # The get() call should have been attempted at least once
            queue._running = False

        stop_task = asyncio.create_task(stop_after_timeout())
        await queue._worker_loop()
        await stop_task

        # get() was called (the wait_for wrapping it may have hit timeout)
        assert poll_count[0] >= 1

    async def test_worker_loop_exits_when_stopped(self, queue: BackgroundJobQueue) -> None:
        """_worker_loop exits when _running is set to False."""
        queue._running = False
        # Should return immediately without blocking
        await queue._worker_loop()
        assert queue._running is False
