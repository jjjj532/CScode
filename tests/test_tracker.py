from __future__ import annotations

import json
import os
import tempfile

import pytest

from cscode.core.tracker import TaskTracker
from cscode.schema.events import ToolFailure, ToolResult
from cscode.schema.ids import ToolCallID
from cscode.storage.db import Database


@pytest.fixture
async def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(db_path=path)
    await database.init()
    yield database
    await database.close()
    os.unlink(path)


@pytest.mark.asyncio
async def test_tracker_handles_tool_success_with_evidence(db):
    tracker = TaskTracker(db)
    event = {
        "type": "tool.success",
        "data": {
            "name": "browser",
            "result": "Screenshot saved",
            "args": {"task_id": "TC-001", "action": "screenshot"},
            "metadata": {
                "task_id": "TC-001",
                "evidence": json.dumps({"screenshot_path": "/tmp/ss.png", "html": True, "html_length": 100, "content_length": 500}),
                "verified": "True",
            },
        },
    }
    await tracker.handle_event("session-1", event)

    rows = await db.fetchall(
        "SELECT * FROM task_verifications WHERE session_id = ? AND task_id = ?",
        ("session-1", "TC-001"),
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "EXECUTED"
    assert rows[0]["verified"] == 1


@pytest.mark.asyncio
async def test_tracker_handles_tool_failed(db):
    tracker = TaskTracker(db)
    event = {
        "type": "tool.failed",
        "data": {
            "name": "browser",
            "error": "Timeout",
            "args": {"task_id": "TC-002"},
            "metadata": {"task_id": "TC-002"},
        },
    }
    await tracker.handle_event("session-1", event)

    rows = await db.fetchall(
        "SELECT * FROM task_verifications WHERE session_id = ? AND task_id = ?",
        ("session-1", "TC-002"),
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["verified"] == 0


@pytest.mark.asyncio
async def test_tracker_skips_events_without_task_id(db):
    tracker = TaskTracker(db)
    event = {
        "type": "tool.success",
        "data": {
            "name": "read",
            "result": "file content",
            "args": {"file_path": "/tmp/test.txt"},
            "metadata": {},
        },
    }
    await tracker.handle_event("session-1", event)

    rows = await db.fetchall("SELECT * FROM task_verifications")
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_tracker_unverified_when_no_evidence(db):
    tracker = TaskTracker(db)
    event = {
        "type": "tool.success",
        "data": {
            "name": "browser",
            "result": "",
            "args": {"task_id": "TC-003", "action": "get_text"},
            "metadata": {
                "task_id": "TC-003",
                "evidence": json.dumps({"screenshot_path": "", "html": False, "html_length": 0, "content_length": 0}),
                "verified": "False",
            },
        },
    }
    await tracker.handle_event("session-1", event)

    rows = await db.fetchall(
        "SELECT * FROM task_verifications WHERE session_id = ? AND task_id = ?",
        ("session-1", "TC-003"),
    )
    assert rows[0]["status"] == "UNVERIFIED"


# ─── LLMEvent conversion tests ────────────────────────────────────────


def test_tool_result_event_includes_name_args_metadata():
    """ToolResult schema event now carries tool_name, tool_args, metadata."""
    evt = ToolResult(
        tool_call_id=ToolCallID("call-1"),
        result="ok",
        tool_name="browser",
        tool_args={"task_id": "TC-001", "action": "screenshot"},
        metadata={"evidence": '{"html":true}', "verified": "True"},
    )
    assert evt.tool_name == "browser"
    assert evt.tool_args == {"task_id": "TC-001", "action": "screenshot"}
    assert evt.metadata == {"evidence": '{"html":true}', "verified": "True"}


def test_tool_failure_event_includes_name_args_metadata():
    """ToolFailure schema event now carries tool_name, tool_args, metadata."""
    evt = ToolFailure(
        tool_call_id=ToolCallID("call-2"),
        error="timeout",
        tool_name="browser",
        tool_args={"task_id": "TC-002"},
        metadata={"task_id": "TC-002"},
    )
    assert evt.tool_name == "browser"
    assert evt.tool_args == {"task_id": "TC-002"}
    assert evt.metadata == {"task_id": "TC-002"}


def test_llm_event_to_dict_enriched():
    """_llm_event_to_dict includes name/args/metadata for tool events."""
    from cscode.server.app import _llm_event_to_dict

    evt = ToolResult(
        tool_call_id=ToolCallID("call-1"),
        result="done",
        tool_name="bash",
        tool_args={"command": "ls", "task_id": "TC-001"},
        metadata={"evidence": '{"content_length":42}', "verified": "True"},
    )
    d = _llm_event_to_dict(evt)
    assert d["type"] == "tool.success"
    assert d["data"]["name"] == "bash"
    assert d["data"]["args"] == {"command": "ls", "task_id": "TC-001"}
    assert d["data"]["metadata"]["evidence"] == '{"content_length":42}'


@pytest.mark.asyncio
async def test_handle_event_from_llm_event(db):
    """Full flow: LLMEvent → _llm_event_to_dict → handle_event → task_verifications."""
    from cscode.server.app import _llm_event_to_dict

    # Simulate what happens in app.py on_event
    llm_evt = ToolResult(
        tool_call_id=ToolCallID("call-1"),
        result="test output",
        tool_name="bash",
        tool_args={"command": "echo hi", "task_id": "TC-005"},
        metadata={"evidence": json.dumps({"content_length": 6}), "verified": "True"},
    )
    sse_event = _llm_event_to_dict(llm_evt)
    assert sse_event["type"] == "tool.success"

    tracker = TaskTracker(db)
    await tracker.handle_event("session-1", sse_event)

    rows = await db.fetchall(
        "SELECT * FROM task_verifications WHERE session_id = ? AND task_id = ?",
        ("session-1", "TC-005"),
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "EXECUTED"
    assert rows[0]["verified"] == 1
    assert rows[0]["tool_name"] == "bash"


@pytest.mark.asyncio
async def test_get_execution_report_with_skipped(db):
    """get_execution_report computes SKIPPED from expected_tasks."""
    tracker = TaskTracker(db)

    # Insert expected tasks
    await db.execute(
        "INSERT INTO expected_tasks (session_id, task_id, description) VALUES (?, ?, ?)",
        ("session-1", "TC-001", "Login test"),
    )
    await db.execute(
        "INSERT INTO expected_tasks (session_id, task_id, description) VALUES (?, ?, ?)",
        ("session-1", "TC-002", "Signup test"),
    )
    await db.execute(
        "INSERT INTO expected_tasks (session_id, task_id, description) VALUES (?, ?, ?)",
        ("session-1", "TC-003", "Logout test"),
    )

    # Insert one executed, one failed
    await db.execute(
        "INSERT INTO task_verifications (session_id, task_id, tool_name, status, verified, evidence, result_summary) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("session-1", "TC-001", "browser", "EXECUTED", 1, '{"html":true}', "ok"),
    )
    await db.execute(
        "INSERT INTO task_verifications (session_id, task_id, tool_name, status, verified, evidence, result_summary) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("session-1", "TC-002", "browser", "FAILED", 0, '{}', "timeout"),
    )

    report = await tracker.get_execution_report("session-1")

    # Compute skipped from expected_tasks
    all_expected = await db.fetchall(
        "SELECT task_id FROM expected_tasks WHERE session_id = ?",
        ("session-1",),
    )
    expected_ids = {r["task_id"] for r in all_expected}
    recorded_ids = {d["task_id"] for d in report["details"]}
    skipped = expected_ids - recorded_ids

    assert report["summary"]["executed"] == 1
    assert report["summary"]["failed"] == 1
    assert len(skipped) == 1  # TC-003 skipped
    assert "TC-003" in skipped


@pytest.mark.asyncio
async def test_get_execution_report(db):
    tracker = TaskTracker(db)
    await db.execute(
        "INSERT INTO task_verifications (session_id, task_id, tool_name, status, verified, evidence, result_summary) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("session-1", "TC-001", "browser", "EXECUTED", 1, '{"html":true}', "ok"),
    )
    await db.execute(
        "INSERT INTO task_verifications (session_id, task_id, tool_name, status, verified, evidence, result_summary) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("session-1", "TC-002", "browser", "UNVERIFIED", 0, '{}', ""),
    )

    report = await tracker.get_execution_report("session-1")
    assert report["summary"]["executed"] == 1
    assert report["summary"]["unverified"] == 1
    assert len(report["details"]) == 2
