from __future__ import annotations

import json
import os
import tempfile

import pytest

from cscode.core.tracker import TaskTracker
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
