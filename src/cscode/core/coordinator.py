"""SessionCoordinator — per-session state machine.

Manages the lifecycle of a single session's processing loop.
Implements the idle → draining → queued state machine to ensure
only one active processing chain per session.

Features:
    - Per-session serialization (IDLE → DRAINING → QUEUED)
    - Global concurrency limit (max_concurrent)
    - Interrupt support via cancel events
    - Status introspection (get_status)
    - Completion waiting (wait_for_completion)

Usage:
    coordinator = SessionCoordinator(max_concurrent=3)
    await coordinator.run(session_id, processor)
    status = coordinator.get_status()
    ok = await coordinator.wait_for_completion(session_id, timeout=5.0)
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

    When max_concurrent > 0, a global semaphore limits how many
    sessions can be in DRAINING simultaneously. Excess sessions
    are queued per-session (QUEUED state) and resume automatically
    when the current drain completes.
    """

    def __init__(self, max_concurrent: int = 0) -> None:
        """Initialize the coordinator.

        Args:
            max_concurrent: Maximum number of sessions that can be
                draining simultaneously. 0 means unlimited (default).
        """
        self._states: dict[str, SessionState] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_mutex = asyncio.Lock()
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._completion_events: dict[str, asyncio.Event] = {}
        self._max_concurrent = max_concurrent
        self._semaphore: asyncio.Semaphore | None = (
            asyncio.Semaphore(max_concurrent) if max_concurrent > 0 else None
        )

    async def _get_lock(self, session_id: str) -> asyncio.Lock:
        async with self._lock_mutex:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
                self._states[session_id] = SessionState.IDLE
                self._completion_events[session_id] = asyncio.Event()
                # Initially set so wait_for_completion on idle resolves
                self._completion_events[session_id].set()
            return self._locks[session_id]

    def get_state(self, session_id: str) -> SessionState:
        """Get the current state for a session."""
        return self._states.get(session_id, SessionState.IDLE)

    def get_status(self) -> dict[str, str]:
        """Return the state of all tracked sessions.

        Returns:
            Dict mapping session_id → lowercase state name
            (e.g. "idle", "draining", "queued").
        """
        return {
            sid: state.name.lower()
            for sid, state in self._states.items()
        }

    async def run(self, session_id: str, processor: Any) -> str:
        """Run the session processing loop.

        If the session is already draining, the caller is queued.
        Only one queue slot is available per session.

        If max_concurrent is set and the global limit is reached,
        the caller waits until a slot becomes available.

        Args:
            session_id: Unique session identifier.
            processor: Object with an async process(session_id) method.

        Returns:
            The result of the processor.
        """
        lock = await self._get_lock(session_id)

        # Acquire global concurrency slot if limited
        if self._semaphore is not None:
            await self._semaphore.acquire()

        prev = self._states[session_id]

        if prev == SessionState.DRAINING:
            self._states[session_id] = SessionState.QUEUED
            logger.info("Session %s queued (was DRAINING)", session_id)
            async with lock:
                pass
            if self._semaphore is not None:
                self._semaphore.release()
            return ""

        self._states[session_id] = SessionState.DRAINING
        # Clear completion event — session is now active
        self._completion_events[session_id].clear()
        logger.info(
            "Session %s state: %s -> DRAINING",
            session_id, prev.name if hasattr(prev, 'name') else prev,
        )

        try:
            async with lock:
                return await self._process_loop(session_id, processor)
        finally:
            if self._semaphore is not None:
                self._semaphore.release()
            if self._states.get(session_id) == SessionState.QUEUED:
                self._states[session_id] = SessionState.DRAINING
                self._completion_events[session_id].clear()
                logger.info("Session %s re-draining (was QUEUED)", session_id)
                async with lock:
                    await self._process_loop(session_id, processor)
            self._states[session_id] = SessionState.IDLE
            self._completion_events[session_id].set()
            logger.info("Session %s state: DRAINING -> IDLE", session_id)

    async def wait_for_completion(
        self,
        session_id: str,
        timeout: float | None = None,
    ) -> bool:
        """Wait for a session to complete its current execution.

        If the session is not tracked or already idle, returns
        immediately with True.

        Args:
            session_id: Session to wait for.
            timeout: Maximum seconds to wait. None = wait forever.

        Returns:
            True if the session completed (or was already idle),
            False if the timeout elapsed before completion.
        """
        completion_event = self._completion_events.get(session_id)
        if completion_event is None:
            return True  # session not tracked → already "done"

        try:
            await asyncio.wait_for(completion_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

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
            logger.debug(
                "Session %s wake no-op (state=%s)",
                session_id, state.name if state else "None",
            )

    async def interrupt(self, session_id: str) -> None:
        """Cancel current processing for a session."""
        cancel_event = self._cancel_events.get(session_id)
        if cancel_event is not None:
            logger.info("Interrupt requested for session %s", session_id)
            cancel_event.set()
        else:
            logger.debug(
                "Interrupt requested for session %s: no active cancel event",
                session_id,
            )

    async def _process_loop(self, session_id: str, processor: Any) -> str:
        """Inner processing loop. Calls processor.process() which should
        handle LLM calls, tool dispatch, and event emission.
        Returns the processor's result string.

        If the processor exposes a ``cancel_event`` attribute, it is
        set to the cancel event so the processor can check for
        interruption (e.g. via SessionExecution).
        """
        cancel_evt = asyncio.Event()
        self._cancel_events[session_id] = cancel_evt

        # Pass cancel_event to processor if it supports it
        if hasattr(processor, "cancel_event"):
            processor.cancel_event = cancel_evt

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
                    logger.error(
                        "Process loop error for session %s: %s",
                        session_id, exc,
                    )
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
