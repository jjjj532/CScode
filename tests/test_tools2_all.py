"""Unit tests for all tools2 implementations (Batch 2-4)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

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
