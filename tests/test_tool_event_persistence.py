"""P4: Regression tests — tool.success / tool.failed events persist to EventStore.

Locks the E2E finding that tool result events were reported missing. The server
maps ToolResult/ToolFailure LLMEvents to tool.success/tool.failed SSE dicts and
persists them (PERSIST_EVENT_TYPES). These tests freeze that behavior so it
cannot silently regress.
"""

from __future__ import annotations

from typing import Any

import pytest

from cscode.schema.events import ToolFailure, ToolResult
from cscode.schema.ids import ToolCallID
from cscode.server.app import PERSIST_EVENT_TYPES, _llm_event_to_dict
from cscode.storage.event_store import EventStore


@pytest.fixture
async def db(tmp_path):
    from cscode.storage.db import Database

    _db = Database(db_path=tmp_path / "tool_events.db")
    await _db.init()
    yield _db
    await _db.close()


@pytest.mark.asyncio
async def test_llm_event_to_dict_maps_tool_result_to_success() -> None:
    """ToolResult LLMEvent maps to a tool.success SSE dict."""
    evt = _llm_event_to_dict(
        ToolResult(
            tool_call_id=ToolCallID("c1"),
            result="done",
            tool_name="bash",
            tool_args={"cmd": "pwd"},
            metadata={"duration_ms": 12},
        )
    )
    assert evt["type"] == "tool.success"
    data = evt["data"]
    assert isinstance(data, dict)
    assert data["tool_call_id"] == "c1"
    assert data["result"] == "done"
    assert data["name"] == "bash"


@pytest.mark.asyncio
async def test_llm_event_to_dict_maps_tool_failure_to_failed() -> None:
    """ToolFailure LLMEvent maps to a tool.failed SSE dict."""
    evt = _llm_event_to_dict(
        ToolFailure(
            tool_call_id=ToolCallID("c2"),
            error="boom",
            tool_name="write",
            tool_args={"path": "a.py"},
        )
    )
    assert evt["type"] == "tool.failed"
    data = evt["data"]
    assert isinstance(data, dict)
    assert data["tool_call_id"] == "c2"
    assert data["error"] == "boom"
    assert data["name"] == "write"


def test_persist_event_types_include_tool_results() -> None:
    """PERSIST_EVENT_TYPES must include tool.success and tool.failed."""
    assert "tool.success" in PERSIST_EVENT_TYPES
    assert "tool.failed" in PERSIST_EVENT_TYPES


@pytest.mark.asyncio
async def test_tool_result_events_persist_to_event_store(db: Any) -> None:
    """Appending tool.success/tool.failed via the server helper writes to EventStore."""
    store = EventStore(db)
    sid = "p4-session"
    await store.append(
        sid,
        [
            {"type": "tool.called", "data": {"name": "bash", "args": {"cmd": "pwd"}}},
            {"type": "tool.success", "data": {"name": "bash", "result": "done"}},
            {"type": "tool.failed", "data": {"name": "write", "error": "boom"}},
        ],
    )
    events = await store.read(sid)
    types = [e.type for e in events]
    assert "tool.called" in types
    assert "tool.success" in types
    assert "tool.failed" in types