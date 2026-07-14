"""SessionExecution — standardized execution pipeline for session processing.

Manages the lifecycle of processing a user prompt through an agent:

    1. ADMIT — persist prompt to event store (durable prompt admission)
    2. RUN — delegate to agent runner, stream events
    3. COMPLETE — mark success, or handle error/interrupt gracefully

Run state transitions:
    idle → running (mark_run_start)
         ↓
    running → completed (mark_run_complete) — success
    running → errored  (mark_run_error)    — exception
    running → stopped  (mark_run_stop)     — interruption / CancelledError
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from cscode.core.session import SessionV2
from cscode.schema.events import (
    LLMEvent,
    TextDelta,
)
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class SessionExecution:
    """Standardized execution pipeline for processing a user prompt.

    Wraps the full lifecycle of a single prompt execution:
    durable admit → run → complete/error/stop.

    Usage:
        execution = SessionExecution(cancel_event=some_event)
        result = await execution.execute(session, user_input, agent_runner)

    The agent_runner is an async generator that yields LLMEvents.
    The execution handles run_status transitions and interrupt checking.
    """

    def __init__(self, cancel_event: asyncio.Event | None = None) -> None:
        """Initialize SessionExecution.

        Args:
            cancel_event: Optional event that signals interruption.
                          When set mid-execution, the pipeline stops
                          gracefully and marks the run as stopped.
        """
        self._cancel_event = cancel_event

    @property
    def is_interrupted(self) -> bool:
        """Whether an interrupt has been signalled."""
        return self._cancel_event is not None and self._cancel_event.is_set()

    async def execute(
        self,
        session: SessionV2,
        user_input: str,
        agent_runner: Callable[[], AsyncIterator[LLMEvent]],
        on_event: Callable[[LLMEvent], Any] | None = None,
    ) -> str:
        """Execute the full lifecycle for a user prompt.

        Pipeline:
            1. ADMIT — mark_run_start() + prompt() (durable admission)
            2. RUN — iterate agent_runner, forward events, check interrupt
            3. COMPLETE — mark_run_complete() on success
            4. ERROR/STOP — mark_run_error() / mark_run_stop() on failure

        Args:
            session: The session to execute within.
            user_input: The user's prompt text. Persisted to event store
                        before any agent processing begins.
            agent_runner: Async generator that produces LLMEvents.
                          Receives no arguments — close over session and
                          user_input in the closure/lambda as needed.
            on_event: Optional callback invoked for each LLMEvent.
                      Called after interrupt checking, before accumulation.
                      Can be sync or async.

        Returns:
            The accumulated assistant response text.

        Raises:
            Exception: Re-raises any exception from agent_runner after
                       setting run_state to 'errored'.
            asyncio.CancelledError: Re-raises after setting run_state to
                                    'stopped'.
        """
        # ── Phase 1: ADMIT ──────────────────────────────────────────
        logger.debug(
            "Execution admit: session=%s input_len=%d",
            session.session_id, len(user_input),
        )
        await session.mark_run_start()
        await session.prompt(user_input)

        full_content = ""

        # ── Phase 2: RUN ────────────────────────────────────────────
        try:
            async for event in agent_runner():
                # Check for interrupt before processing the event
                if self.is_interrupted:
                    logger.info(
                        "Execution interrupted: session=%s", session.session_id,
                    )
                    await session.mark_run_stop()
                    return full_content

                # Forward event to caller
                if on_event is not None:
                    if hasattr(on_event, "__await__"):
                        await on_event(event)
                    else:
                        on_event(event)

                # Accumulate text content from TextDelta events.
                # TextEnded marks completion but the full text is already
                # accumulated via TextDelta — ignore it to avoid overwriting
                # multi-round content.
                match event:
                    case TextDelta(text=t):
                        full_content += t
                    case _:
                        pass

            # ── Phase 3: COMPLETE ───────────────────────────────────
            logger.debug(
                "Execution complete: session=%s result_len=%d",
                session.session_id, len(full_content),
            )
            await session.mark_run_complete()
            return full_content

        except asyncio.CancelledError:
            logger.info(
                "Execution cancelled: session=%s", session.session_id,
            )
            await session.mark_run_stop()
            raise

        except Exception as e:
            logger.error(
                "Execution error: session=%s error=%s",
                session.session_id, str(e)[:200],
            )
            await session.mark_run_error(str(e))
            raise
