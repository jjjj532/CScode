"""SessionCoordinator — per-session state machine.

Manages the lifecycle of a single session's processing loop.
Implements the idle → draining → queued state machine to ensure
only one active processing chain per session.

States:
    IDLE      — No processing in progress
    DRAINING  — Actively processing (LLM calls, tool dispatch)
    QUEUED    — A request is queued (only one slot)

Usage:
    coordinator = SessionCoordinator()
    await coordinator.run(session_id)  # starts processing
    await coordinator.wake(session_id) # coalesces demand
    await coordinator.interrupt(session_id)  # cancels processing
"""

from __future__ import annotations

import asyncio
from enum import Enum, auto
from typing import Any


class SessionState(Enum):
    IDLE = auto()
    DRAINING = auto()
    QUEUED = auto()


class SessionCoordinator:
    """Per-session state machine ensuring ordered processing.

    Thread-safe via per-session lock. Each session has at most
    one active processing chain and one queued request.
    """

    def __init__(self) -> None:
        self._states: dict[str, SessionState] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_mutex = asyncio.Lock()
        self._cancel_events: dict[str, asyncio.Event] = {}

    async def _get_lock(self, session_id: str) -> asyncio.Lock:
        async with self._lock_mutex:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
                self._states[session_id] = SessionState.IDLE
            return self._locks[session_id]

    def get_state(self, session_id: str) -> SessionState:
        """Get the current state for a session."""
        return self._states.get(session_id, SessionState.IDLE)

    async def run(self, session_id: str, processor: Any) -> None:
        """Run the session processing loop.

        If the session is already draining, the caller is queued.
        Only one queue slot is available.
        """
        lock = await self._get_lock(session_id)

        if self._states[session_id] == SessionState.DRAINING:
            self._states[session_id] = SessionState.QUEUED
            # Wait for current drain to finish
            async with lock:
                pass
            return

        self._states[session_id] = SessionState.DRAINING

        try:
            async with lock:
                await self._process_loop(session_id, processor)
        finally:
            if self._states.get(session_id) == SessionState.QUEUED:
                self._states[session_id] = SessionState.DRAINING
                async with lock:
                    await self._process_loop(session_id, processor)
            self._states[session_id] = SessionState.IDLE

    async def wake(self, session_id: str) -> None:
        """Coalesce demand — if the session is currently draining,
        mark it as queued so it runs again after finishing.
        If idle, this is a no-op.
        """
        if self._states.get(session_id) == SessionState.DRAINING:
            self._states[session_id] = SessionState.QUEUED
        # If idle, there's nothing to interrupt — next run() will work.

    async def interrupt(self, session_id: str) -> None:
        """Cancel current processing for a session."""
        cancel_event = self._cancel_events.get(session_id)
        if cancel_event is not None:
            cancel_event.set()

    async def _process_loop(self, session_id: str, processor: Any) -> None:
        """Inner processing loop. Calls processor.process() which should
        handle LLM calls, tool dispatch, and event emission.
        """
        cancel_evt = asyncio.Event()
        self._cancel_events[session_id] = cancel_evt

        try:
            process_task = asyncio.create_task(processor.process(session_id))
            interrupt_task = asyncio.create_task(self._wait_interrupt(cancel_evt))

            done, pending = await asyncio.wait(
                [process_task, interrupt_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            for task in done:
                exc = task.exception()
                if exc is not None:
                    raise exc
        finally:
            self._cancel_events.pop(session_id, None)

    @staticmethod
    async def _wait_interrupt(cancel_evt: asyncio.Event) -> None:
        """Wait until interrupt is signalled."""
        await cancel_evt.wait()
