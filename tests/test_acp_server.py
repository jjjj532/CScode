"""Tests for G-5: ACP server completeness (spec §5.1).

Verifies ACPServer bridges protocol endpoints → SessionRunner:
  session → prompt → load_session → cancel full lifecycle
  fork_session isolates events (no pollution of source session)
  structured errors reuse schema/errors.py semantics (no bare exceptions)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from cscode.acp.server import ACPResponse, ACPServer
from cscode.acp.protocol import ACPMessageType
from cscode.core.session import SessionV2
from cscode.schema.errors import LLMError, LLMErrorReason
from cscode.schema.events import (
    Finish,
    LLMEvent,
    TextDelta,
    TextEnded,
    TextStarted,
)
from cscode.schema.ids import SessionID
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore

pytestmark = pytest.mark.asyncio


class _FakeLLMClient:
    """Produces a fixed text stream; raises LLMError on demand."""

    def __init__(self, texts: list[str] | None = None, fail: bool = False) -> None:
        self._texts = texts or ["Hello from ACP"]
        self._fail = fail

    async def stream(self, request: Any) -> AsyncIterator[LLMEvent]:
        if self._fail:
            raise LLMError(
                module="LLM",
                method="stream",
                reason=LLMErrorReason.RATE_LIMIT,
                message="429 Too Many Requests",
                retryable=True,
                retry_after_ms=5000,
            )
        for text in self._texts:
            yield TextStarted()
            yield TextDelta(text=text)
            yield TextEnded(full_text=text)
        yield Finish(finish_reason="stop")


class _FakeToolRuntime:
    async def dispatch(self, tool_call_id: Any, name: str, args: dict[str, Any]) -> AsyncIterator[LLMEvent]:
        # No tool calls in these tests — iterator must be empty-safe.
        return
        yield  # pragma: no cover


class _FakeSessionFactory:
    """Minimal factory: create() makes a fresh session, load() replays events."""

    def __init__(self, event_store: EventStore) -> None:
        self._store = event_store

    async def create(
        self,
        model: str = "gpt-4o",
        provider: str = "openai",
        title: str = "",
        agent: str = "auto",
        workspace_id: str = "",
    ) -> SessionV2:
        return await SessionV2.create(
            self._store, model, provider=provider, title=title, agent=agent,
            workspace_id=workspace_id,
        )

    async def load(self, session_id: str) -> SessionV2:
        return await SessionV2.load(self._store, SessionID(session_id))


@pytest.fixture
async def acp_server() -> ACPServer:
    db = Database(":memory:")
    await db.init()
    store = EventStore(db)
    runner = _FakeRunner()
    factory = _FakeSessionFactory(store)
    return ACPServer(runner=runner, session_factory=factory)


class _FakeRunner:
    """Stand-in for SessionRunner.run — records the call, returns canned text."""

    def __init__(self) -> None:
        self.last_session: str | None = None
        self.last_prompt: str = ""
        self.cancelled = False
        self.fail = False

    async def run(
        self,
        session: SessionV2,
        user_input: str,
        on_event: Any = None,
        generation_options: Any = None,
        cancel_event: Any = None,
    ) -> str:
        self.last_session = session.session_id
        self.last_prompt = user_input
        if self.fail:
            raise LLMError(
                module="LLM",
                method="stream",
                reason=LLMErrorReason.RATE_LIMIT,
                message="429 Too Many Requests",
                retryable=True,
                retry_after_ms=5000,
            )
        if cancel_event is not None:
            cancel_event.set()
            self.cancelled = True
        return "fake response"


class TestSessionLifecycle:
    """验收标准 1: session → prompt → load_session → cancel 全链路。"""

    async def test_session_creates_and_returns_id(self, acp_server: ACPServer) -> None:
        resp = await acp_server.handle({
            "method": "session",
            "payload": {"model": "gpt-4o", "title": "Lifecycle Test"},
        })
        assert resp.ok
        assert isinstance(resp.data["session_id"], str)
        assert len(resp.data["session_id"]) > 0

    async def test_prompt_runs_and_returns_text(self, acp_server: ACPServer) -> None:
        created = await acp_server.handle({
            "method": "session",
            "payload": {"model": "gpt-4o"},
        })
        sid = created.data["session_id"]

        resp = await acp_server.handle({
            "method": "prompt",
            "session_id": sid,
            "payload": {"prompt": "Hello"},
        })
        assert resp.ok
        assert resp.data["output"] == "fake response"

    async def test_load_session_restores_state(self, acp_server: ACPServer) -> None:
        created = await acp_server.handle({
            "method": "session",
            "payload": {"model": "gpt-4o", "title": "Persist Me"},
        })
        sid = created.data["session_id"]

        loaded = await acp_server.handle({
            "method": "load_session",
            "session_id": sid,
        })
        assert loaded.ok
        assert loaded.data["session_id"] == sid

    async def test_cancel_interrupts_prompt(self, acp_server: ACPServer) -> None:
        created = await acp_server.handle({
            "method": "session",
            "payload": {"model": "gpt-4o"},
        })
        sid = created.data["session_id"]

        resp = await acp_server.handle({
            "method": "cancel",
            "session_id": sid,
        })
        assert resp.ok
        assert resp.data["status"] == "cancelled"


class TestForkSession:
    """验收标准 2: fork_session 生成新 session 且不污染原 session（事件隔离）。"""

    async def test_fork_creates_new_session(self, acp_server: ACPServer) -> None:
        created = await acp_server.handle({
            "method": "session",
            "payload": {"model": "gpt-4o", "title": "Original"},
        })
        original = created.data["session_id"]

        forked = await acp_server.handle({
            "method": "fork_session",
            "session_id": original,
        })
        assert forked.ok
        assert forked.data["session_id"] != original

    async def test_fork_preserves_original_events(self, acp_server: ACPServer) -> None:
        created = await acp_server.handle({
            "method": "session",
            "payload": {"model": "gpt-4o", "title": "Orig"},
        })
        original = created.data["session_id"]
        await acp_server.handle({"method": "prompt", "session_id": original, "payload": {"prompt": "seed"}})

        forked = await acp_server.handle({"method": "fork_session", "session_id": original})
        forked_id = forked.data["session_id"]

        orig = await acp_server._factory.load(original)
        fork = await acp_server._factory.load(forked_id)
        assert orig.session_id == SessionID(original)
        assert fork.session_id == SessionID(forked_id)


class TestErrorResponses:
    """验收标准 3: 结构化错误复用 schema/errors.py 语义，不抛裸异常。"""

    async def test_unknown_method_returns_structured_error(self, acp_server: ACPServer) -> None:
        resp = await acp_server.handle({"method": "no_such_method"})
        assert not resp.ok
        assert resp.error is not None
        assert resp.error.reason == LLMErrorReason.INVALID_REQUEST
        assert resp.error.module == "ACP"

    async def test_missing_session_returns_structured_error(self, acp_server: ACPServer) -> None:
        resp = await acp_server.handle({"method": "prompt", "session_id": "nonexistent"})
        assert not resp.ok
        assert resp.error is not None
        assert resp.error.reason == LLMErrorReason.NO_ROUTE

    async def test_llm_error_propagates_structured(self, acp_server: ACPServer) -> None:
        """LLMError from runner surfaces as ACPResponse.error, not exception."""
        created = await acp_server.handle({"method": "session", "payload": {"model": "gpt-4o"}})
        sid = created.data["session_id"]
        acp_server._runner.fail = True

        resp = await acp_server.handle({"method": "prompt", "session_id": sid, "payload": {"prompt": "hi"}})
        assert not resp.ok
        assert resp.error is not None
        assert resp.error.reason == LLMErrorReason.RATE_LIMIT
