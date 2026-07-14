"""Tests for SessionExecution — standardized execution pipeline.

Tests verify:
1. execute() completes successfully with proper run_status transitions
2. execute() handles errors with run_error state
3. execute() handles interrupt via cancel_event
4. execute() accumulates content from streamed events
5. SessionExecution works with empty user input
6. is_interrupted property reflects cancel_event state
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from cscode.core.session import SessionV2
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore
from cscode.schema.events import (
    Finish,
    LLMEvent,
    TextDelta,
    TextEnded,
    TextStarted,
)
from cscode.schema.ids import SessionID


pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
async def event_store() -> EventStore:
    db = Database(":memory:")
    await db.init()
    return EventStore(db)


@pytest.fixture
async def session(event_store: EventStore) -> SessionV2:
    return await SessionV2.create(event_store, "gpt-4o", title="Exec Test")


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


async def _event_stream(
    texts: list[str] | None = None,
    raise_error: bool = False,
) -> AsyncIterator[LLMEvent]:
    """Produce a simple stream of TextStarted → TextDelta* → TextEnded → Finish."""
    content = texts or ["Hello, world!"]
    for text in content:
        yield TextStarted()
        yield TextDelta(text=text)
        yield TextEnded(full_text=text)
    if raise_error:
        msg = "Simulated execution error"
        raise RuntimeError(msg)
    yield Finish(finish_reason="stop")


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════


class TestSessionExecution:
    """Tests for SessionExecution lifecycle."""

    async def test_execute_completes_successfully(self, session: SessionV2) -> None:
        """SessionExecution.execute() marks run_start, admits prompt, runs agent, marks complete."""
        from cscode.core.execution import SessionExecution

        execution = SessionExecution()
        content = "Hello, world!"

        async def runner() -> AsyncIterator[LLMEvent]:
            yield TextStarted()
            yield TextDelta(text=content)
            yield TextEnded(full_text=content)
            yield Finish(finish_reason="stop")

        result = await execution.execute(session, "test prompt", runner)

        assert result == content
        assert session.state.run_status == "completed"
        assert session.state.run_error == ""

    async def test_execute_accumulates_multiple_texts(self, session: SessionV2) -> None:
        """Execute accumulates content across multiple TextEnded events."""
        from cscode.core.execution import SessionExecution

        execution = SessionExecution()

        async def runner() -> AsyncIterator[LLMEvent]:
            yield TextStarted()
            yield TextDelta(text="Part A")
            yield TextEnded(full_text="Part A")
            yield TextStarted()
            yield TextDelta(text="Part B")
            yield TextEnded(full_text="Part B")
            yield Finish(finish_reason="stop")

        result = await execution.execute(session, "multi", runner)

        assert "Part A" in result
        assert "Part B" in result

    async def test_execute_handles_error(self, session: SessionV2) -> None:
        """When agent_runner raises, execution marks run_error and re-raises."""
        from cscode.core.execution import SessionExecution

        execution = SessionExecution()

        async def runner() -> AsyncIterator[LLMEvent]:
            yield TextStarted()
            yield TextDelta(text="partial")
            yield TextEnded(full_text="partial")
            msg = "LLM API failure"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="LLM API failure"):
            await execution.execute(session, "error test", runner)

        assert session.state.run_status == "errored"
        assert "LLM API failure" in session.state.run_error

    async def test_execute_interrupted(self, session: SessionV2) -> None:
        """When cancel_event is set mid-stream, execution stops and marks run_stopped."""
        from cscode.core.execution import SessionExecution

        cancel_event = asyncio.Event()

        execution = SessionExecution(cancel_event=cancel_event)

        # Set cancel_event after first event
        event_count = 0

        async def runner() -> AsyncIterator[LLMEvent]:
            nonlocal event_count
            event_count += 1
            yield TextStarted()
            yield TextDelta(text="first")
            yield TextEnded(full_text="first")
            # Now signal interrupt
            cancel_event.set()
            yield TextStarted()
            yield TextDelta(text="should not appear")
            yield TextEnded(full_text="should not appear")
            yield Finish(finish_reason="stop")

        result = await execution.execute(session, "interrupt test", runner)

        # Should have stopped after the interrupt check
        assert session.state.run_status == "stopped"
        assert "first" in result
        assert "should not appear" not in result

    async def test_execute_empty_input(self, session: SessionV2) -> None:
        """Empty user input still executes the pipeline."""
        from cscode.core.execution import SessionExecution

        execution = SessionExecution()

        async def runner() -> AsyncIterator[LLMEvent]:
            yield TextStarted()
            yield TextEnded(full_text="")
            yield Finish(finish_reason="stop")

        result = await execution.execute(session, "", runner)

        assert result == ""
        assert session.state.run_status == "completed"

    async def test_execute_prompt_admitted_durably(self, session: SessionV2, event_store: EventStore) -> None:
        """The prompt is admitted as an event before the runner executes."""
        from cscode.core.execution import SessionExecution

        execution = SessionExecution()

        async def runner() -> AsyncIterator[LLMEvent]:
            # At this point, the prompt should already be persisted
            yield TextStarted()
            yield TextDelta(text="response")
            yield TextEnded(full_text="response")
            yield Finish(finish_reason="stop")

        await execution.execute(session, "durable prompt test", runner)

        # Reload session from store to verify durability
        loaded = await SessionV2.load(event_store, session.session_id)
        assert len(loaded.state.messages) > 0
        assert "durable prompt test" in loaded.state.messages[0].parts[0].text  # type: ignore[union-attr]

    async def test_execute_is_interrupted_property(self, session: SessionV2) -> None:
        """is_interrupted reflects the cancel_event state."""
        from cscode.core.execution import SessionExecution

        cancel_event = asyncio.Event()
        execution = SessionExecution(cancel_event=cancel_event)

        assert not execution.is_interrupted

        cancel_event.set()
        assert execution.is_interrupted

    async def test_execute_is_interrupted_no_event(self, session: SessionV2) -> None:
        """is_interrupted is False when no cancel_event is provided."""
        from cscode.core.execution import SessionExecution

        execution = SessionExecution()
        assert not execution.is_interrupted

    async def test_execute_multiple_calls(self, session: SessionV2) -> None:
        """SessionExecution can be called multiple times on the same session."""
        from cscode.core.execution import SessionExecution

        execution = SessionExecution()

        async def runner_a() -> AsyncIterator[LLMEvent]:
            yield TextStarted()
            yield TextDelta(text="first call")
            yield TextEnded(full_text="first call")
            yield Finish(finish_reason="stop")

        async def runner_b() -> AsyncIterator[LLMEvent]:
            yield TextStarted()
            yield TextDelta(text="second call")
            yield TextEnded(full_text="second call")
            yield Finish(finish_reason="stop")

        result_a = await execution.execute(session, "prompt 1", runner_a)
        result_b = await execution.execute(session, "prompt 2", runner_b)

        assert result_a == "first call"
        assert result_b == "second call"

    async def test_execute_cancelled_error(self, session: SessionV2) -> None:
        """asyncio.CancelledError during execution is handled gracefully."""
        from cscode.core.execution import SessionExecution

        execution = SessionExecution()

        async def runner() -> AsyncIterator[LLMEvent]:
            yield TextStarted()
            yield TextDelta(text="before cancel")
            yield TextEnded(full_text="before cancel")
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await execution.execute(session, "cancel test", runner)

        assert session.state.run_status == "stopped"

    async def test_execute_with_coordinator_cancel_event(self, event_store: EventStore) -> None:
        """SessionExecution receives cancel_event from coordinator via processor."""
        from cscode.core.execution import SessionExecution
        from cscode.core.coordinator import SessionCoordinator

        coord = SessionCoordinator()
        session = await SessionV2.create(event_store, "gpt-4o", title="Coord Exec Test")
        sid = str(session.session_id)
        received_cancel: list[asyncio.Event | None] = [None]

        class CancelAwareProcessor:
            def __init__(self) -> None:
                self.cancel_event: asyncio.Event | None = None

            async def process(self, session_id: str) -> str:
                # cancel_event should be set by _process_loop before calling process()
                received_cancel[0] = self.cancel_event
                return "ok"

        processor = CancelAwareProcessor()
        await coord.run(sid, processor)

        # Verify cancel_event was propagated
        assert received_cancel[0] is not None
        assert isinstance(received_cancel[0], asyncio.Event)
        # The event starts unset
        assert not received_cancel[0].is_set()

    async def test_execute_on_event_callback(self, session: SessionV2) -> None:
        """on_event callback is invoked for each event."""
        from cscode.core.execution import SessionExecution

        execution = SessionExecution()
        received: list[LLMEvent] = []

        async def runner() -> AsyncIterator[LLMEvent]:
            yield TextStarted()
            yield TextDelta(text="cb test")
            yield TextEnded(full_text="cb test")
            yield Finish(finish_reason="stop")

        # Use on_event as an iterator-based callback (sync)
        def event_collector(event: LLMEvent) -> None:
            received.append(event)

        result = await execution.execute(session, "callback", runner, on_event=event_collector)

        assert result == "cb test"
        assert len(received) > 0
        assert any(isinstance(e, TextStarted) for e in received)
        assert any(isinstance(e, TextEnded) for e in received)
        assert any(isinstance(e, Finish) for e in received)
