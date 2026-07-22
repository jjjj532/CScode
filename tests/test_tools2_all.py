"""Unit tests for all tools2 implementations (Batch 2-4)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from cscode.storage.db import Database
from cscode.tools2 import (
    BashTool, GrepTool, GlobTool, LsTool,
    WebFetchTool, WebSearchTool,
    TodoWriteTool, QuestionTool, SkillTool, ApplyPatchTool,
    ToolRegistry,
)
from cscode.tools2.bash import BashInput, BashOutput
from cscode.tools2.grep import GrepInput, GrepOutput
from cscode.tools2.glob import GlobInput, GlobOutput
from cscode.tools2.ls import LsInput, LsOutput
from cscode.tools2.webfetch import WebFetchInput
from cscode.tools2.websearch import WebSearchInput
from cscode.tools2.todowrite import TodoWriteInput
from cscode.tools2.question import QuestionInput
from cscode.tools2.skill import SkillInput
from cscode.tools2.apply_patch import ApplyPatchInput


# ---------------------------------------------------------------------------
# BashTool
# ---------------------------------------------------------------------------

class TestBashTool:
    tool = BashTool()

    async def test_echo(self) -> None:
        result = await self.tool.execute(BashInput(command="echo hello"))
        assert result.success
        assert result.data is not None
        assert "hello" in result.data.output
        assert result.data.exit_code == 0

    async def test_failing_command(self) -> None:
        result = await self.tool.execute(BashInput(command="exit 42"))
        assert not result.success
        assert result.data is None
        assert "42" in (result.error or "")

    async def test_non_existent_command(self) -> None:
        result = await self.tool.execute(BashInput(command="nonexistent_cmd_xyz"))
        assert not result.success

    async def test_timeout(self) -> None:
        result = await self.tool.execute(BashInput(command="sleep 10", timeout=100))
        assert not result.success
        assert "timed out" in (result.error or "").lower()

    async def test_metadata_includes_evidence_with_content_length(self) -> None:
        """BashTool metadata includes evidence dict with content_length > 0 on success."""
        result = await self.tool.execute(BashInput(command="echo hello world", task_id="TC-001"))
        assert result.metadata is not None
        assert "evidence" in result.metadata
        import json
        evidence = json.loads(result.metadata["evidence"]) if isinstance(result.metadata["evidence"], str) else result.metadata["evidence"]
        assert evidence["content_length"] > 0
        assert evidence["exit_code"] == 0
        assert "timestamp" in evidence

    async def test_metadata_includes_task_id_when_provided(self) -> None:
        """BashTool metadata includes task_id when set in input."""
        result = await self.tool.execute(BashInput(command="echo hi", task_id="TC-002"))
        assert result.metadata is not None
        assert result.metadata.get("task_id") == "TC-002"

    async def test_metadata_evidence_with_nonzero_exit(self) -> None:
        """BashTool evidence includes content_length even when exit_code != 0."""
        result = await self.tool.execute(BashInput(command="echo stderr_output >&2; exit 1", task_id="TC-003"))
        assert result.metadata is not None
        assert "evidence" in result.metadata
        import json
        evidence = json.loads(result.metadata["evidence"]) if isinstance(result.metadata["evidence"], str) else result.metadata["evidence"]
        assert evidence["content_length"] > 0  # stderr has content
        assert evidence["exit_code"] == 1
        assert "timestamp" in evidence


# ---------------------------------------------------------------------------
# GrepTool
# ---------------------------------------------------------------------------

class TestGrepTool:
    tool = GrepTool()

    async def test_grep_basic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.txt"
            f.write_text("hello world\nfoo bar\nhello again")
            result = await self.tool.execute(GrepInput(pattern="hello", path=tmpdir))
            assert result.success
            assert result.data is not None
            assert result.data.matches >= 2
            assert result.data.files_scanned >= 1

    async def test_grep_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.txt"
            f.write_text("hello world")
            result = await self.tool.execute(GrepInput(pattern="zzz", path=tmpdir))
            assert result.success
            assert result.data is not None
            assert result.data.matches == 0

    async def test_grep_nonexistent_path(self) -> None:
        result = await self.tool.execute(GrepInput(pattern="foo", path="/tmp/nonexistent_xyz"))
        assert not result.success

    async def test_grep_single_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("python code here\n")
            path = f.name
        try:
            result = await self.tool.execute(GrepInput(pattern="python", path=path))
            assert result.success
            assert result.data is not None
            assert result.data.matches >= 1
        finally:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# GlobTool
# ---------------------------------------------------------------------------

class TestGlobTool:
    tool = GlobTool()

    async def test_glob_find_py(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "a.py").write_text("")
            Path(tmpdir, "b.py").write_text("")
            Path(tmpdir, "c.txt").write_text("")
            result = await self.tool.execute(GlobInput(pattern="*.py", path=tmpdir))
            assert result.success
            assert result.data is not None
            assert result.data.count == 2
            assert any("a.py" in m for m in result.data.matches)

    async def test_glob_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await self.tool.execute(GlobInput(pattern="*.xyz", path=tmpdir))
            assert result.success
            assert result.data is not None
            assert result.data.count == 0

    async def test_glob_nonexistent_path(self) -> None:
        result = await self.tool.execute(GlobInput(pattern="*.py", path="/tmp/nonexistent_xyz"))
        assert not result.success


# ---------------------------------------------------------------------------
# LsTool
# ---------------------------------------------------------------------------

class TestLsTool:
    tool = LsTool()

    async def test_ls_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "a.txt").write_text("")
            Path(tmpdir, "b.txt").write_text("")
            sub = Path(tmpdir, "sub")
            sub.mkdir()
            result = await self.tool.execute(LsInput(path=tmpdir))
            assert result.success
            assert result.data is not None
            assert result.data.count >= 2
            # sub/ should have trailing slash
            assert any("sub/" in e for e in result.data.entries)

    async def test_ls_nonexistent(self) -> None:
        result = await self.tool.execute(LsInput(path="/tmp/nonexistent_xyz"))
        assert not result.success

    async def test_ls_not_a_directory(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name
        try:
            result = await self.tool.execute(LsInput(path=path))
            assert not result.success
        finally:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# TodoWriteTool
# ---------------------------------------------------------------------------

class TestTodoWriteTool:
    tool = TodoWriteTool()

    async def test_todo_basic(self) -> None:
        result = await self.tool.execute(TodoWriteInput(todos=[
            {"content": "Task 1", "status": "pending", "priority": "high"},
        ]))
        assert result.success
        assert result.data is not None
        assert "HIGH" in result.data.formatted
        assert result.data.count == 1

    async def test_todo_multiple(self) -> None:
        result = await self.tool.execute(TodoWriteInput(todos=[
            {"content": "Task A", "status": "in_progress", "priority": "high"},
            {"content": "Task B", "status": "completed", "priority": "low"},
        ]))
        assert result.success
        assert result.data is not None
        assert result.data.count == 2

    @pytest.mark.asyncio
    async def test_todowrite_writes_expected_tasks_with_db(self) -> None:
        """TodoWriteTool should write to expected_tasks table when db and session_id provided."""
        # Create temp database
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = Database(db_path=path)
        await db.init()
        try:
            tool = TodoWriteTool()
            # Execute with context containing db and session_id
            context = {"session_id": "test-session-001", "db": db}
            result = await tool.execute(
                TodoWriteInput(todos=[
                    {"content": "TC-001 Login test", "status": "pending", "priority": "high"},
                ]),
                context=context,
            )
            assert result.success

            # Verify expected_tasks was written
            rows = await db.fetchall(
                "SELECT * FROM expected_tasks WHERE session_id = ?",
                ("test-session-001",),
            )
            assert len(rows) == 1
            assert rows[0]["task_id"] == "TC-001"
            assert rows[0]["description"] == "TC-001 Login test"
        finally:
            await db.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_todowrite_extracts_tc_id_from_content(self) -> None:
        """TodoWriteTool should extract TC-XXX from task content."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = Database(db_path=path)
        await db.init()
        try:
            tool = TodoWriteTool()
            context = {"session_id": "test-session-002", "db": db}
            result = await tool.execute(
                TodoWriteInput(todos=[
                    {"content": "Test case TC-005 verify login", "status": "pending", "priority": "medium"},
                ]),
                context=context,
            )
            assert result.success

            rows = await db.fetchall(
                "SELECT task_id FROM expected_tasks WHERE session_id = ?",
                ("test-session-002",),
            )
            assert len(rows) == 1
            assert rows[0]["task_id"] == "TC-005"
        finally:
            await db.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_todowrite_on_event_from_context(self) -> None:
        """on_event callback from context should be called with task_created event."""
        tool = TodoWriteTool()
        events: list[dict[str, object]] = []

        async def capture_event(event: dict[str, object]) -> None:
            events.append(event)

        context = {"session_id": "test-ctx-001", "on_event": capture_event}
        result = await tool.execute(
            TodoWriteInput(todos=[
                {"content": "TC-010 Context event", "status": "pending", "priority": "high"},
            ]),
            context=context,
        )
        assert result.success
        assert len(events) == 1
        assert events[0]["type"] == "task_created"
        assert events[0]["session_id"] == "test-ctx-001"
        data = events[0]["data"]
        assert isinstance(data, dict)
        assert data["task_id"] == "TC-010"
        assert data["description"] == "TC-010 Context event"
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_todowrite_on_event_from_init(self) -> None:
        """on_event callback from __init__ should be called with task_created event."""
        events: list[dict[str, object]] = []

        async def capture_event(event: dict[str, object]) -> None:
            events.append(event)

        tool = TodoWriteTool(on_event=capture_event)
        result = await tool.execute(
            TodoWriteInput(todos=[
                {"content": "TC-011 Init event", "status": "in_progress", "priority": "medium"},
            ]),
        )
        assert result.success
        assert len(events) == 1
        assert events[0]["type"] == "task_created"
        data = events[0]["data"]
        assert isinstance(data, dict)
        assert data["task_id"] == "TC-011"

    @pytest.mark.asyncio
    async def test_todowrite_context_on_event_overrides_init(self) -> None:
        """context on_event overrides __init__ on_event when both provided."""
        init_events: list[dict[str, object]] = []
        ctx_events: list[dict[str, object]] = []

        async def init_cb(event: dict[str, object]) -> None:
            init_events.append(event)

        async def ctx_cb(event: dict[str, object]) -> None:
            ctx_events.append(event)

        tool = TodoWriteTool(on_event=init_cb)
        result = await tool.execute(
            TodoWriteInput(todos=[
                {"content": "TC-012 Override test", "status": "completed", "priority": "low"},
            ]),
            context={"session_id": "test-override", "on_event": ctx_cb},
        )
        assert result.success
        # Only context callback should fire
        assert len(ctx_events) == 1
        assert len(init_events) == 0

    @pytest.mark.asyncio
    async def test_todowrite_no_tc_id_fallback_to_content(self) -> None:
        """When no TC-XXX pattern matches, task_id should fallback to first 50 chars of content."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = Database(db_path=path)
        await db.init()
        try:
            tool = TodoWriteTool()
            long_content = "A" * 100
            context = {"session_id": "test-noid-001", "db": db}
            result = await tool.execute(
                TodoWriteInput(todos=[
                    {"content": long_content, "status": "pending", "priority": "high"},
                ]),
                context=context,
            )
            assert result.success

            rows = await db.fetchall(
                "SELECT task_id FROM expected_tasks WHERE session_id = ?",
                ("test-noid-001",),
            )
            assert len(rows) == 1
            assert rows[0]["task_id"] == "A" * 50
        finally:
            await db.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_todowrite_context_none(self) -> None:
        """context=None should not raise and should produce valid output."""
        tool = TodoWriteTool()
        result = await tool.execute(
            TodoWriteInput(todos=[
                {"content": "TC-020 No context", "status": "pending", "priority": "high"},
            ]),
            context=None,
        )
        assert result.success
        assert result.data is not None
        assert "TC-020" in result.data.formatted

    @pytest.mark.asyncio
    async def test_todowrite_context_empty_db_no_session_id(self) -> None:
        """db present but session_id empty should skip DB write without error."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = Database(db_path=path)
        await db.init()
        try:
            tool = TodoWriteTool()
            context = {"session_id": "", "db": db}
            result = await tool.execute(
                TodoWriteInput(todos=[
                    {"content": "TC-030 No session", "status": "pending", "priority": "medium"},
                ]),
                context=context,
            )
            assert result.success

            rows = await db.fetchall(
                "SELECT * FROM expected_tasks",
            )
            assert len(rows) == 0
        finally:
            await db.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_todowrite_duplicate_tc_id_idempotent(self) -> None:
        """INSERT OR IGNORE should handle duplicate TC-ID without error."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = Database(db_path=path)
        await db.init()
        try:
            tool = TodoWriteTool()
            context = {"session_id": "test-dedup-001", "db": db}
            # Insert same TC-XXX twice
            for _ in range(2):
                result = await tool.execute(
                    TodoWriteInput(todos=[
                        {"content": "TC-040 Duplicate test", "status": "pending", "priority": "high"},
                    ]),
                    context=context,
                )
                assert result.success

            # Should only have one row
            rows = await db.fetchall(
                "SELECT * FROM expected_tasks WHERE session_id = ?",
                ("test-dedup-001",),
            )
            assert len(rows) == 1
        finally:
            await db.close()
            os.unlink(path)


# ---------------------------------------------------------------------------
# QuestionTool
# ---------------------------------------------------------------------------

class TestQuestionTool:
    tool = QuestionTool()

    async def test_question_basic(self) -> None:
        result = await self.tool.execute(QuestionInput(question="What is your name?"))
        assert result.success
        assert result.data is not None
        assert "What is your name?" in result.data.formatted

    async def test_question_with_options(self) -> None:
        result = await self.tool.execute(QuestionInput(
            question="Choose one", options=["A", "B", "C"]
        ))
        assert result.success
        assert "A" in result.data.formatted


# ---------------------------------------------------------------------------
# SkillTool
# ---------------------------------------------------------------------------

class TestSkillTool:
    tool = SkillTool()

    async def test_skill_basic(self) -> None:
        result = await self.tool.execute(SkillInput(name="test-skill"))
        assert result.success
        assert result.data is not None
        assert "test-skill" in result.data.message


# ---------------------------------------------------------------------------
# WebSearchTool (stub)
# ---------------------------------------------------------------------------

class TestWebSearchTool:
    tool = WebSearchTool()

    async def test_websearch_basic(self) -> None:
        result = await self.tool.execute(WebSearchInput(query="test query", num_results=5))
        assert result.success
        assert result.data is not None
        assert "test query" in result.data.results


# ---------------------------------------------------------------------------
# WebFetchTool (requires network, test basic validation only)
# ---------------------------------------------------------------------------

class TestWebFetchTool:
    tool = WebFetchTool()

    async def test_webfetch_invalid_url(self) -> None:
        result = await self.tool.execute(WebFetchInput(url="not-a-url"))
        assert not result.success
        assert "invalid" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# ApplyPatchTool (test input validation)
# ---------------------------------------------------------------------------

class TestApplyPatchTool:
    tool = ApplyPatchTool()

    async def test_apply_patch_nonexistent_file(self) -> None:
        result = await self.tool.execute(ApplyPatchInput(
            path="/tmp/nonexistent_xyz.txt",
            patch_content="--- a\n+++ b\n@@ -0,0 +1 @@\n+hello",
        ))
        assert not result.success
        assert "not found" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# Full registry integration test
# ---------------------------------------------------------------------------

class TestFullRegistry:
    def test_register_all_14_tools(self) -> None:
        reg = ToolRegistry()
        from cscode.tools2 import (
            ReadTool, WriteTool, EditTool, BashTool, GrepTool,
            GlobTool, LsTool, WebFetchTool, WebSearchTool,
            TodoWriteTool, QuestionTool, SkillTool, ApplyPatchTool, BrowserTool,
        )
        for t in [ReadTool(), WriteTool(), EditTool(), BashTool(), GrepTool(),
                  GlobTool(), LsTool(), WebFetchTool(), WebSearchTool(),
                  TodoWriteTool(), QuestionTool(), SkillTool(), ApplyPatchTool(), BrowserTool()]:
            reg.register(t)
        assert len(reg.list_tools()) == 14

    def test_definitions_all(self) -> None:
        reg = ToolRegistry()
        from cscode.tools2 import ReadTool, WriteTool, EditTool
        reg.register(ReadTool())
        reg.register(WriteTool())
        reg.register(EditTool())
        defs = reg.to_definitions()
        assert len(defs) == 3
        for d in defs:
            assert d.name
            assert d.description
            assert "type" in d.input_schema
