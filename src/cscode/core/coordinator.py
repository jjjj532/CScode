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

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


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

    async def run(self, session_id: str, processor: Any) -> str:
        """Run the session processing loop.

        If the session is already draining, the caller is queued.
        Only one queue slot is available.
        Returns the result of the processor.
        """
        lock = await self._get_lock(session_id)

        prev = self._states[session_id]

        if prev == SessionState.DRAINING:
            self._states[session_id] = SessionState.QUEUED
            logger.info("Session %s queued (was DRAINING)", session_id)
            async with lock:
                pass
            return ""

        self._states[session_id] = SessionState.DRAINING
        logger.info("Session %s state: %s -> DRAINING", session_id, prev.name if hasattr(prev, 'name') else prev)

        try:
            async with lock:
                return await self._process_loop(session_id, processor)
        finally:
            if self._states.get(session_id) == SessionState.QUEUED:
                self._states[session_id] = SessionState.DRAINING
                logger.info("Session %s re-draining (was QUEUED)", session_id)
                async with lock:
                    await self._process_loop(session_id, processor)
            self._states[session_id] = SessionState.IDLE
            logger.info("Session %s state: DRAINING -> IDLE", session_id)

    async def wake(self, session_id: str) -> None:
        """Coalesce demand — if the session is currently draining,
        mark it as queued so it runs again after finishing.
        If idle, this is a no-op.
        """
        state = self._states.get(session_id)
        if state == SessionState.DRAINING:
            self._states[session_id] = SessionState.QUEUED
            logger.info("Session %s woken: DRAINING -> QUEUED", session_id)
        else:
            logger.debug("Session %s wake no-op (state=%s)", session_id, state.name if state else "None")

    async def interrupt(self, session_id: str) -> None:
        """Cancel current processing for a session."""
        cancel_event = self._cancel_events.get(session_id)
        if cancel_event is not None:
            logger.info("Interrupt requested for session %s", session_id)
            cancel_event.set()
        else:
            logger.debug("Interrupt requested for session %s: no active cancel event", session_id)

    async def _process_loop(self, session_id: str, processor: Any) -> str:
        """Inner processing loop. Calls processor.process() which should
        handle LLM calls, tool dispatch, and event emission.
        Returns the processor's result string.
        """
        cancel_evt = asyncio.Event()
        self._cancel_events[session_id] = cancel_evt
        logger.debug("Process loop starting for session %s", session_id)

        try:
            process_task = asyncio.create_task(processor.process(session_id))
            interrupt_task = asyncio.create_task(self._wait_interrupt(cancel_evt))

            done, pending = await asyncio.wait(
                [process_task, interrupt_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            result: str = ""
            for task in done:
                exc = task.exception()
                if exc is not None:
                    logger.error("Process loop error for session %s: %s", session_id, exc)
                    raise exc
                try:
                    result = task.result() or ""
                except Exception:
                    pass
            return result
        finally:
            self._cancel_events.pop(session_id, None)
            logger.debug("Process loop ended for session %s", session_id)

    @staticmethod
    async def _wait_interrupt(cancel_evt: asyncio.Event) -> None:
        """Wait until interrupt is signalled."""
        await cancel_evt.wait()
