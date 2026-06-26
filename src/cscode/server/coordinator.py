from __future__ import annotations

import asyncio
from typing import Any, Callable

Handler = Callable[[], Any]

class _Entry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._pending: tuple[Handler, asyncio.Future[None] | None] | None = None

    @property
    def locked(self) -> bool:
        return self._lock.locked()

class SessionCoordinator:
    """Per-session: 1 active + 1 queued. run() waits, wake() coalesces."""

    _entries: dict[str, _Entry] = {}
    _dict_lock = asyncio.Lock()

    async def _entry(self, sid: str) -> _Entry:
        async with self._dict_lock:
            if sid not in self._entries:
                self._entries[sid] = _Entry()
            return self._entries[sid]

    async def _drain(self, sid: str, entry: _Entry, handler: Handler) -> None:
        await entry._lock.acquire()
        try:
            await handler()
            while entry._pending:
                h, future = entry._pending
                entry._pending = None
                await h()
                if future is not None:
                    future.set_result(None)
        finally:
            entry._lock.release()
            async with self._dict_lock:
                if entry._pending is None and sid in self._entries:
                    del self._entries[sid]

    async def run(self, sid: str, handler: Handler) -> None:
        """Explicit run: caller waits until handler completes."""
        entry = await self._entry(sid)
        if entry.locked:
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            entry._pending = (handler, future)
            await future
        else:
            await self._drain(sid, entry, handler)

    async def wake(self, sid: str, handler: Handler) -> None:
        """Advisory notification: coalesces if already draining, no wait."""
        entry = await self._entry(sid)
        if entry.locked:
            entry._pending = (handler, None)
        else:
            await self._drain(sid, entry, handler)
