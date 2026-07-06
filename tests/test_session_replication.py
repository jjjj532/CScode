"""Tests for Session Replication — per-session concurrency locks.

Tests cover:
1. EventLock basic acquire/release
2. EventLock try_acquire returns False when locked
3. EventLock waiters wake after release
4. SessionLockManager per-session locking
5. SessionLockManager different sessions don't interfere
6. SessionLockManager unlock without lock (safe)
"""
from __future__ import annotations

import asyncio

import pytest

from cscode.core.session import EventLock, SessionLockManager


class TestEventLock:
    """EventLock — a per-session lock with try_acquire()."""

    async def test_acquire_release(self) -> None:
        lock = EventLock()
        assert await lock.acquire() is True
        lock.release()

    async def test_try_acquire_returns_true_when_free(self) -> None:
        lock = EventLock()
        assert lock.try_acquire() is True
        lock.release()

    async def test_try_acquire_returns_false_when_locked(self) -> None:
        lock = EventLock()
        lock.try_acquire()
        assert lock.try_acquire() is False
        lock.release()
        assert lock.try_acquire() is True
        lock.release()

    async def test_waiter_wakes_after_release(self) -> None:
        lock = EventLock()
        lock.try_acquire()
        results: list[int] = []

        async def waiter() -> None:
            await lock.acquire()
            results.append(1)
            lock.release()

        task = asyncio.create_task(waiter())
        await asyncio.sleep(0.01)
        assert len(results) == 0
        lock.release()
        await asyncio.wait_for(task, timeout=1)
        assert results == [1]

    async def test_double_release_is_safe(self) -> None:
        lock = EventLock()
        lock.release()
        lock.release()
        assert lock.try_acquire() is True

    async def test_concurrent_acquires_are_serialized(self) -> None:
        lock = EventLock()
        acquired: list[int] = []

        async def worker(i: int) -> None:
            await lock.acquire()
            acquired.append(i)
            await asyncio.sleep(0.01)
            lock.release()

        tasks = [asyncio.create_task(worker(i)) for i in range(5)]
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
        assert acquired == list(range(5))


class TestSessionLockManager:
    """SessionLockManager — per-session locking orchestration."""

    async def test_try_lock_returns_true_first_time(self) -> None:
        assert await SessionLockManager.try_lock("sess-1") is True
        SessionLockManager.unlock("sess-1")

    async def test_try_lock_returns_false_second_time(self) -> None:
        assert await SessionLockManager.try_lock("sess-2") is True
        assert await SessionLockManager.try_lock("sess-2") is False
        SessionLockManager.unlock("sess-2")

    async def test_different_sessions_dont_interfere(self) -> None:
        assert await SessionLockManager.try_lock("sess-a") is True
        assert await SessionLockManager.try_lock("sess-b") is True
        SessionLockManager.unlock("sess-a")
        SessionLockManager.unlock("sess-b")

    async def test_lock_available_after_unlock(self) -> None:
        assert await SessionLockManager.try_lock("sess-3") is True
        SessionLockManager.unlock("sess-3")
        assert await SessionLockManager.try_lock("sess-3") is True
        SessionLockManager.unlock("sess-3")

    async def test_unlock_without_lock_is_safe(self) -> None:
        SessionLockManager.unlock("nonexistent")

    async def test_cleanup_removes_idle_lock(self) -> None:
        await SessionLockManager.try_lock("sess-clean")
        assert "sess-clean" in SessionLockManager._locks
        SessionLockManager.unlock("sess-clean")
        SessionLockManager.cleanup("sess-clean")
        assert "sess-clean" not in SessionLockManager._locks
