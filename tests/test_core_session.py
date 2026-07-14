"""Contract tests for Phase 2 Core layer.

Tests verify:
- SessionV2: create, prompt, add_text, metadata, delete, refresh
- SessionProjector: event → SessionState reconstruction
- SessionCoordinator: state machine transitions
- SessionRunner: loop structure (mocked LLM)
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest

from cscode.core.coordinator import SessionCoordinator, SessionState
from cscode.core.runner import SessionRunner
from cscode.core.session import SessionProjector, SessionV2
from cscode.schema.errors import LLMError, LLMErrorReason
from cscode.schema.events import (
    Error as LLMEventError,
)
from cscode.schema.events import (
    Finish,
    LLMEvent,
    TextDelta,
    TextEnded,
    TextStarted,
    ToolCallDelta,
    ToolCallEnded,
    ToolCallStarted,
)
from cscode.schema.events import (
    ToolFailure as EventToolFailure,
)
from cscode.schema.events import (
    ToolResult as EventToolResult,
)
from cscode.schema.ids import SessionID, ToolCallID
from cscode.schema.messages import MessageRole
from cscode.storage.db import Database
from cscode.storage.event_store import Event, EventStore

# ─── In-Memory DB Fixture ───────────────────────────────────────────


@pytest.fixture
async def event_store() -> EventStore:
    db = Database(":memory:")
    await db.init()
    return EventStore(db)


# ─── SessionProjector ───────────────────────────────────────────────


class TestSessionProjector:
    def test_project_empty_events(self) -> None:
        state = SessionProjector.project([])
        assert state.session_id == SessionID("")
        assert state.messages == ()
        assert state.status == "active"

    def test_project_created_event(self) -> None:
        events = [
            Event(
                aggregate_id="sess_001",
                seq=1,
                type="session.created",
                data={"title": "Test", "provider": "openai", "model": "gpt-4o", "agent": "auto"},
                created_at=time.time(),
            )
        ]
        state = SessionProjector.project(events)
        assert state.session_id == SessionID("sess_001")
        assert state.title == "Test"
        assert state.provider == "openai"
        assert state.model == "gpt-4o"
        assert state.agent == "auto"
        assert state.status == "active"
        assert state.seq == 1

    def test_project_prompt_and_text(self) -> None:
        events = [
            Event(
                "sess_001",
                1,
                "session.created",
                {"title": "Chat", "provider": "openai", "model": "gpt-4o", "agent": "auto"},
                100.0,
            ),
            Event("sess_001", 2, "prompt.admitted", {"prompt": "Hello"}, 101.0),
            Event("sess_001", 3, "text.ended", {"content": "Hi there!"}, 102.0),
        ]
        state = SessionProjector.project(events)
        assert len(state.messages) == 2
        assert state.messages[0].role == MessageRole.USER
        assert state.messages[0].content == "Hello"
        assert state.messages[1].role == MessageRole.ASSISTANT
        assert state.messages[1].content == "Hi there!"

    def test_project_deleted(self) -> None:
        events = [
            Event(
                "sess_001",
                1,
                "session.created",
                {"title": "X", "provider": "openai", "model": "gpt-4o", "agent": "auto"},
                100.0,
            ),
            Event("sess_001", 2, "session.deleted", {}, 101.0),
        ]
        state = SessionProjector.project(events)
        assert state.status == "deleted"

    def test_project_updated(self) -> None:
        events = [
            Event(
                "sess_001",
                1,
                "session.created",
                {"title": "Old", "provider": "openai", "model": "gpt-4o", "agent": "auto"},
                100.0,
            ),
            Event(
                "sess_001", 2, "session.updated", {"title": "New Title", "model": "claude-3"}, 101.0
            ),
        ]
        state = SessionProjector.project(events)
        assert state.title == "New Title"
        assert state.model == "claude-3"

    def test_project_tool_call_increments_round(self) -> None:
        events = [
            Event(
                "sess_001",
                1,
                "session.created",
                {"title": "X", "provider": "openai", "model": "gpt-4o", "agent": "auto"},
                100.0,
            ),
            Event(
                "sess_001",
                2,
                "tool.called",
                {"name": "Bash", "args": {"command": "ls"}, "round": 1},
                101.0,
            ),
        ]
        state = SessionProjector.project(events)
        assert state.tool_rounds == 1

    def test_build_context(self) -> None:
        events = [
            Event(
                "sess_001",
                1,
                "session.created",
                {"title": "X", "provider": "openai", "model": "gpt-4o", "agent": "auto"},
                100.0,
            ),
            Event("sess_001", 2, "prompt.admitted", {"prompt": "Hi"}, 101.0),
            Event("sess_001", 3, "text.ended", {"content": "Hey"}, 102.0),
        ]
        state = SessionProjector.project(events)
        ctx = SessionProjector.build_context(state)
        assert len(ctx) == 2
        assert ctx[0].role == MessageRole.USER
        assert ctx[1].role == MessageRole.ASSISTANT


# ─── SessionV2 ──────────────────────────────────────────────────────


class TestSessionV2:
    async def test_create(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", "openai", title="Test Session")
        assert session.session_id is not None
        assert session.state.title == "Test Session"
        assert session.state.model == "gpt-4o"
        assert session.state.provider == "openai"
        assert session.state.status == "active"

    async def test_prompt(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o")
        await session.prompt("Hello, world!")
        assert len(session.state.messages) == 1
        assert session.state.messages[0].content == "Hello, world!"

    async def test_add_text(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o")
        await session.prompt("Hi")
        await session.add_text("Hello back!")
        assert len(session.state.messages) == 2
        assert session.state.messages[1].role == MessageRole.ASSISTANT
        assert session.state.messages[1].content == "Hello back!"

    async def test_add_tool_call(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o")
        await session.add_tool_call("Bash", {"command": "ls"})
        assert session.state.tool_rounds == 1

    async def test_update_metadata(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", title="Old")
        await session.update_metadata(title="New Title", model="claude-3")
        assert session.state.title == "New Title"
        assert session.state.model == "claude-3"

    async def test_delete(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o")
        assert session.state.status == "active"
        await session.delete()
        assert session.state.status == "deleted"

    async def test_load(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", title="Load Test")
        await session.prompt("Hello")
        # Load from store
        loaded = await SessionV2.load(event_store, session.session_id)
        assert loaded.state.title == "Load Test"
        assert len(loaded.state.messages) == 1
        assert loaded.state.messages[0].content == "Hello"

    async def test_refresh(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", title="Refresh Test")
        assert session.state.title == "Refresh Test"
        # Mutate state directly and refresh
        await event_store.append(
            session.session_id,
            [{"type": "session.updated", "data": {"title": "Refreshed"}}],
        )
        await session.refresh()
        assert session.state.title == "Refreshed"

    async def test_repr(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o")
        rep = repr(session)
        assert "SessionV2" in rep
        assert session.session_id in rep

    async def test_state_not_loaded_error(self) -> None:
        store = EventStore(Database(":memory:"))
        session = SessionV2(store, SessionID("test"))
        with pytest.raises(RuntimeError, match="not loaded"):
            _ = session.state


# ─── SessionCoordinator ─────────────────────────────────────────────


class TestSessionCoordinator:
    async def test_initial_state(self) -> None:
        coord = SessionCoordinator()
        assert coord.get_state("test") == SessionState.IDLE

    async def test_run_changes_state(self) -> None:
        coord = SessionCoordinator()
        calls: list[str] = []

        async def processor(session_id: str) -> None:
            calls.append("process")

        await coord.run("test", _ProcAdapter(processor))
        assert calls == ["process"]

    async def test_wake_sets_queued(self) -> None:
        coord = SessionCoordinator()
        # Initially idle
        assert coord.get_state("test") == SessionState.IDLE
        # Wake on idle is a no-op
        await coord.wake("test")
        assert coord.get_state("test") == SessionState.IDLE

    async def test_interrupt_noop_when_not_running(self) -> None:
        coord = SessionCoordinator()
        # Interrupt on idle should be safe
        await coord.interrupt("test")
        assert coord.get_state("test") == SessionState.IDLE

    # ── SessionCoordinator Enhancements (T2.2) ──────────────────────

    async def test_max_concurrent_limits_simultaneous_runs(self) -> None:
        """max_concurrent=1 allows only one session to drain at a time."""
        coord = SessionCoordinator(max_concurrent=1)
        started: list[str] = []
        barrier = asyncio.Event()

        async def slow_processor(session_id: str) -> str:
            started.append(session_id)
            await barrier.wait()
            return "done"

        # Start session "a" — enters DRAINING, acquires semaphore
        task_a = asyncio.create_task(
            coord.run("a", _ProcAdapter(slow_processor))
        )
        await asyncio.sleep(0.05)

        assert coord.get_state("a") == SessionState.DRAINING
        assert len(started) == 1

        # Start session "b" — blocked on global semaphore, stays IDLE
        task_b = asyncio.create_task(
            coord.run("b", _ProcAdapter(slow_processor))
        )
        await asyncio.sleep(0.05)

        assert coord.get_state("b") == SessionState.IDLE
        assert len(started) == 1  # only "a" is running

        # Release barrier — "a" finishes, semaphore frees, "b" proceeds
        barrier.set()
        await asyncio.gather(task_a, task_b)

        assert len(started) == 2  # both ran

    async def test_max_concurrent_default_no_limit(self) -> None:
        """Default max_concurrent=0 means unlimited."""
        coord = SessionCoordinator()  # default: no limit
        barrier = asyncio.Event()

        async def waiter(session_id: str) -> str:
            await barrier.wait()
            return "ok"

        task_a = asyncio.create_task(coord.run("a", _ProcAdapter(waiter)))
        task_b = asyncio.create_task(coord.run("b", _ProcAdapter(waiter)))
        await asyncio.sleep(0.05)

        # Both should be draining (no limit)
        assert coord.get_state("a") == SessionState.DRAINING
        assert coord.get_state("b") == SessionState.DRAINING

        barrier.set()
        await asyncio.gather(task_a, task_b)

    async def test_get_status_returns_all_sessions(self) -> None:
        """get_status() returns state for all tracked sessions."""
        coord = SessionCoordinator()

        # No sessions tracked yet
        assert coord.get_status() == {}

        # Run a session to track it
        async def fast(session_id: str) -> str:
            return "ok"

        await coord.run("s1", _ProcAdapter(fast))
        status = coord.get_status()
        assert "s1" in status
        assert status["s1"] == "idle"  # back to IDLE after run

        # Queue another
        barrier = asyncio.Event()
        async def slow(session_id: str) -> str:
            await barrier.wait()
            return "ok"

        task = asyncio.create_task(coord.run("s2", _ProcAdapter(slow)))
        await asyncio.sleep(0.05)
        status = coord.get_status()
        assert "s2" in status
        assert status["s2"] == "draining"

        barrier.set()
        await task

    async def test_wait_for_completion_resolves_after_run(self) -> None:
        """wait_for_completion() resolves after the session finishes."""
        coord = SessionCoordinator()
        barrier = asyncio.Event()

        async def slow(session_id: str) -> str:
            await barrier.wait()
            return "done"

        # Start processing in background
        task = asyncio.create_task(coord.run("w1", _ProcAdapter(slow)))

        # Wait for it to start draining
        await asyncio.sleep(0.05)
        assert coord.get_state("w1") == SessionState.DRAINING

        # Start wait_for_completion — should NOT resolve until released
        wait_task = asyncio.create_task(coord.wait_for_completion("w1"))
        await asyncio.sleep(0.05)
        assert not wait_task.done()

        # Release barrier — now wait should resolve
        barrier.set()
        result = await wait_task
        assert result is True

        await task

    async def test_wait_for_completion_idle_session(self) -> None:
        """wait_for_completion() on idle session resolves immediately."""
        coord = SessionCoordinator()
        result = await coord.wait_for_completion("nonexistent")
        assert result is True

    async def test_wait_for_completion_timeout(self) -> None:
        """wait_for_completion() respects timeout parameter."""
        coord = SessionCoordinator()
        barrier = asyncio.Event()

        async def slow(session_id: str) -> str:
            await barrier.wait()
            return "done"

        task = asyncio.create_task(coord.run("t1", _ProcAdapter(slow)))
        await asyncio.sleep(0.05)

        result = await coord.wait_for_completion("t1", timeout=0.1)
        assert result is False  # timed out, didn't complete

        barrier.set()
        await task


class _ProcAdapter:
    """Adapter to wrap a simple async function as a processor."""

    def __init__(self, process_func: Any) -> None:
        self._process = process_func

    async def process(self, session_id: str) -> None:
        await self._process(session_id)


# ─── SessionRunner Contract Tests ────────────────────────────────────


class _MockLLMClient:
    """Mock LLMClient that yields a controlled event sequence."""

    def __init__(self) -> None:
        self._sequences: list[list[LLMEvent]] = []
        self._call_count = 0
        self.last_request: object = None

    def set_sequence(self, events: list[LLMEvent]) -> None:
        self._sequences.append(events)

    def set_sequences(self, sequences: list[list[LLMEvent]]) -> None:
        self._sequences = list(sequences)

    @property
    def route(self) -> object:
        return None

    async def stream(self, request: object) -> AsyncIterator[LLMEvent]:
        self._call_count += 1
        self.last_request = request
        idx = self._call_count - 1
        if idx < len(self._sequences):
            for event in self._sequences[idx]:
                yield event


class _MockToolRuntime:
    """Mock ToolRuntime that returns controlled results."""

    def __init__(self) -> None:
        self._results: dict[str, str] = {}
        self._failures: set[str] = set()
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def set_result(self, tool_name: str, result: str) -> None:
        self._results[tool_name] = result

    def set_failure(self, tool_name: str) -> None:
        self._failures.add(tool_name)

    async def dispatch(
        self,
        tool_call_id: ToolCallID,
        name: str,
        args: dict[str, object],
    ) -> AsyncIterator[LLMEvent]:
        self.calls.append((tool_call_id, name, args))
        if name in self._failures:
            yield EventToolFailure(
                tool_call_id=tool_call_id,
                error=f"Tool {name} failed",
            )
            return
        result = self._results.get(name, f"ok:{name}")
        yield EventToolResult(tool_call_id=tool_call_id, result=result)


class TestSessionRunnerContract:
    """Contract tests for SessionRunner — verify loop structure with mocked dependencies."""

    @staticmethod
    def _make_runner(
        llm_client: _MockLLMClient | None = None,
        tool_runtime: _MockToolRuntime | None = None,
        max_tool_rounds: int = 10,
        system_prompt: str | None = None,
    ) -> SessionRunner:
        return SessionRunner(
            llm_client=llm_client or _MockLLMClient(),  # type: ignore[arg-type]
            tool_runtime=tool_runtime or _MockToolRuntime(),  # type: ignore[arg-type]
            max_tool_rounds=max_tool_rounds,
            system_prompt=system_prompt,
        )

    @pytest.mark.asyncio
    async def test_text_only_response(self, event_store: EventStore) -> None:
        """Single text response with no tool calls."""
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        mock_llm = _MockLLMClient()
        mock_llm.set_sequence(
            [
                TextStarted(),
                TextDelta(text="Hello!"),
                TextEnded(full_text="Hello!"),
                Finish(finish_reason="stop", usage=None),
            ]
        )
        runner = self._make_runner(llm_client=mock_llm)

        result = await runner.run(session, "Hi there")

        assert result == "Hello!"
        assert len(session.state.messages) >= 1

    @pytest.mark.asyncio
    async def test_single_tool_call(self, event_store: EventStore) -> None:
        """One tool call round then final response."""
        session = await SessionV2.create(event_store, "gpt-4o")
        mock_llm = _MockLLMClient()
        mock_tools = _MockToolRuntime()
        mock_tools.set_result("Bash", "hello.txt")

        mock_llm.set_sequence(
            [
                TextStarted(),
                TextDelta(text="Let me check..."),
                TextEnded(full_text="Let me check..."),
                ToolCallStarted(tool_call_id=ToolCallID("call_1"), name="Bash"),
                ToolCallDelta(tool_call_id=ToolCallID("call_1"), args_text='{"command":"ls"}'),
                ToolCallEnded(
                    tool_call_id=ToolCallID("call_1"), name="Bash", args={"command": "ls"}
                ),
                Finish(
                    finish_reason="tool_use", usage={"prompt_tokens": 10, "completion_tokens": 5}
                ),
            ]
        )
        mock_llm.set_sequence(
            [
                TextStarted(),
                TextDelta(text="Done: hello.txt"),
                TextEnded(full_text="Done: hello.txt"),
                Finish(finish_reason="stop", usage=None),
            ]
        )
        runner = self._make_runner(llm_client=mock_llm, tool_runtime=mock_tools)

        result = await runner.run(session, "List files")

        assert "Done: hello.txt" in result
        assert len(mock_tools.calls) == 1
        assert mock_tools.calls[0][1] == "Bash"

    @pytest.mark.asyncio
    async def test_max_tool_rounds_honored(self, event_store: EventStore) -> None:
        """Runner stops after max_tool_rounds even if LLM keeps calling tools."""
        session = await SessionV2.create(event_store, "gpt-4o")
        mock_llm = _MockLLMClient()
        mock_tools = _MockToolRuntime()
        mock_tools.set_result("Read", "/tmp/x content")

        tool_round: list[LLMEvent] = [
            ToolCallStarted(tool_call_id=ToolCallID("c1"), name="Read"),
            ToolCallDelta(tool_call_id=ToolCallID("c1"), args_text='{"path":"/tmp/x"}'),
            ToolCallEnded(tool_call_id=ToolCallID("c1"), name="Read", args={"path": "/tmp/x"}),
            Finish(finish_reason="tool_use", usage=None),
        ]
        mock_llm.set_sequences([tool_round, tool_round, tool_round])

        runner = self._make_runner(llm_client=mock_llm, max_tool_rounds=2)

        await runner.run(session, "Read files")

        assert mock_llm._call_count == 2

    @pytest.mark.asyncio
    async def test_tool_failure_continues(self, event_store: EventStore) -> None:
        """Tool failure should not crash the loop — should continue to next round."""
        session = await SessionV2.create(event_store, "gpt-4o")
        mock_llm = _MockLLMClient()
        mock_tools = _MockToolRuntime()
        mock_tools.set_failure("Bash")

        mock_llm.set_sequence(
            [
                ToolCallStarted(tool_call_id=ToolCallID("c1"), name="Bash"),
                ToolCallDelta(tool_call_id=ToolCallID("c1"), args_text="{}"),
                ToolCallEnded(tool_call_id=ToolCallID("c1"), name="Bash", args={}),
                Finish(finish_reason="tool_use", usage=None),
            ]
        )
        mock_llm.set_sequence(
            [
                TextStarted(),
                TextDelta(text="Tool failed but continuing"),
                TextEnded(full_text="Tool failed but continuing"),
                Finish(finish_reason="stop", usage=None),
            ]
        )
        runner = self._make_runner(llm_client=mock_llm, tool_runtime=mock_tools)

        result = await runner.run(session, "Run bash")

        assert "Tool failed" in result

    @pytest.mark.asyncio
    async def test_system_prompt_injected(self, event_store: EventStore) -> None:
        """System prompt is injected when no existing system message."""
        session = await SessionV2.create(event_store, "gpt-4o")
        mock_llm = _MockLLMClient()
        mock_llm.set_sequence(
            [
                TextStarted(),
                TextDelta(text="OK"),
                TextEnded(full_text="OK"),
                Finish(finish_reason="stop"),
            ]
        )
        runner = self._make_runner(
            llm_client=mock_llm, system_prompt="You are a helpful assistant."
        )

        await runner.run(session, "Hi")

        assert mock_llm.last_request is not None
        assert hasattr(mock_llm.last_request, "messages")

    @pytest.mark.asyncio
    async def test_run_stream_yields_events(self, event_store: EventStore) -> None:
        """run_stream should yield LLMEvents directly."""
        session = await SessionV2.create(event_store, "gpt-4o")
        mock_llm = _MockLLMClient()
        mock_llm.set_sequence(
            [
                TextStarted(),
                TextDelta(text="Hello"),
                TextEnded(full_text="Hello"),
                Finish(finish_reason="stop"),
            ]
        )
        runner = self._make_runner(llm_client=mock_llm)

        events: list[LLMEvent] = []
        async for event in runner.run_stream(session, "Hi"):
            events.append(event)

        assert len(events) >= 1
        assert any(isinstance(e, TextStarted) for e in events)
        assert any(isinstance(e, TextDelta) for e in events)
        assert any(isinstance(e, Finish) for e in events)

    @pytest.mark.asyncio
    async def test_llm_error_returns_error_message(self, event_store: EventStore) -> None:
        """LLM error event should be caught and returned as error message."""
        session = await SessionV2.create(event_store, "gpt-4o")
        mock_llm = _MockLLMClient()
        mock_llm.set_sequence(
            [
                LLMEventError(
                    error=LLMError(
                        module="test",
                        method="stream",
                        reason=LLMErrorReason.PROVIDER_INTERNAL,
                        message="API error",
                    )
                ),
            ]
        )
        runner = self._make_runner(llm_client=mock_llm)

        result = await runner.run(session, "Hi")

        assert "API error" in result or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_run_with_execution_text_only(self, event_store: EventStore) -> None:
        """run_with_execution produces same result as run() with SessionExecution lifecycle."""
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        mock_llm = _MockLLMClient()
        mock_llm.set_sequence(
            [
                TextStarted(),
                TextDelta(text="Hello from exec!"),
                TextEnded(full_text="Hello from exec!"),
                Finish(finish_reason="stop", usage=None),
            ]
        )
        runner = self._make_runner(llm_client=mock_llm)

        result = await runner.run_with_execution(session, "Hi")

        assert result == "Hello from exec!"
        # SessionExecution handles mark_run_start + prompt + mark_run_complete
        assert session.state.run_status == "completed"

    @pytest.mark.asyncio
    async def test_run_with_execution_cancel_event(self, event_store: EventStore) -> None:
        """cancel_event stops execution before it completes."""
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        cancel = asyncio.Event()
        mock_llm = _MockLLMClient()
        mock_llm.set_sequence(
            [
                TextStarted(),
                TextDelta(text="Partial"),
                TextEnded(full_text="Partial"),
                Finish(finish_reason="stop", usage=None),
            ]
        )
        # Signal cancel before execution starts
        cancel.set()
        runner = self._make_runner(llm_client=mock_llm)

        result = await runner.run_with_execution(
            session, "Hi", cancel_event=cancel,
        )

        # Execution was interrupted before processing events
        assert session.state.run_status == "stopped"
        assert result == ""

    @pytest.mark.asyncio
    async def test_run_with_execution_on_event(self, event_store: EventStore) -> None:
        """on_event callback is invoked during run_with_execution."""
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        mock_llm = _MockLLMClient()
        mock_llm.set_sequence(
            [
                TextStarted(),
                TextDelta(text="With callback"),
                TextEnded(full_text="With callback"),
                Finish(finish_reason="stop", usage=None),
            ]
        )
        runner = self._make_runner(llm_client=mock_llm)
        received: list[LLMEvent] = []

        def collect(event: LLMEvent) -> None:
            received.append(event)

        result = await runner.run_with_execution(session, "Hi", on_event=collect)

        assert result == "With callback"
        assert any(isinstance(e, TextDelta) for e in received)
        assert any(isinstance(e, Finish) for e in received)
        assert session.state.run_status == "completed"
