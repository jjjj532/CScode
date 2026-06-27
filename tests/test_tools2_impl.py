"""Unit tests for tools2 implementations."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cscode.tools2 import ReadTool, WriteTool, EditTool, ToolRegistry
from cscode.tools2.read import ReadInput, ReadOutput
from cscode.tools2.write import WriteInput, WriteOutput
from cscode.tools2.edit import EditInput, EditOutput


# ---------------------------------------------------------------------------
# ReadTool
# ---------------------------------------------------------------------------

class TestReadTool:
    tool = ReadTool()

    async def test_read_existing_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            path = f.name
        try:
            result = await self.tool.execute(ReadInput(path=path))
            assert result.success
            assert result.data is not None
            assert result.data.content == "hello world"
            assert result.data.size == 11
            assert result.data.path == path
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_read_nonexistent_file(self) -> None:
        result = await self.tool.execute(ReadInput(path="/tmp/nonexistent_abc123.txt"))
        assert not result.success
        assert result.error is not None
        assert "not found" in result.error.lower()

    async def test_read_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await self.tool.execute(ReadInput(path=tmpdir))
            assert not result.success
            assert result.error is not None
            assert "not a file" in result.error.lower()


# ---------------------------------------------------------------------------
# WriteTool
# ---------------------------------------------------------------------------

class TestWriteTool:
    tool = WriteTool()

    async def test_write_new_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "new.txt"
            result = await self.tool.execute(WriteInput(path=str(path), content="hello"))
            assert result.success
            assert result.data is not None
            assert result.data.size == 5
            assert path.read_text() == "hello"

    async def test_write_overwrite_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "existing.txt"
            path.write_text("old content")
            result = await self.tool.execute(WriteInput(path=str(path), content="new content"))
            assert result.success
            assert path.read_text() == "new content"

    async def test_write_creates_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "a" / "b" / "deep.txt"
            result = await self.tool.execute(WriteInput(path=str(path), content="deep"))
            assert result.success
            assert path.read_text() == "deep"


# ---------------------------------------------------------------------------
# EditTool
# ---------------------------------------------------------------------------

class TestEditTool:
    tool = EditTool()

    async def test_edit_replace(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            path = f.name
        try:
            result = await self.tool.execute(EditInput(
                path=path,
                old_string="world",
                new_string="there",
            ))
            assert result.success
            assert result.data is not None
            assert result.data.replacement_count == 1
            assert Path(path).read_text() == "hello there"
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_edit_nonexistent_file(self) -> None:
        result = await self.tool.execute(EditInput(
            path="/tmp/nonexistent_abc123.txt",
            old_string="foo",
            new_string="bar",
        ))
        assert not result.success

    async def test_edit_old_string_not_found(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            path = f.name
        try:
            result = await self.tool.execute(EditInput(
                path=path,
                old_string="zzz",
                new_string="aaa",
            ))
            assert not result.success
            assert "not found" in result.error.lower() if result.error else True
        finally:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class TestTools2Registry:
    def test_register_all(self) -> None:
        reg = ToolRegistry()
        reg.register(ReadTool())
        reg.register(WriteTool())
        reg.register(EditTool())
        assert set(reg.list_tools()) == {"read", "write", "edit"}

    async def test_materialize_settle(self) -> None:
        reg = ToolRegistry()
        reg.register(ReadTool())

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test data")
            path = f.name

        try:
            _, settle = reg.materialize()
            result = await settle("read", {"path": path})
            assert result.success
            assert result.data is not None
            assert result.data.content == "test data"
        finally:
            Path(path).unlink(missing_ok=True)

    async def test_settle_unknown_tool(self) -> None:
        reg = ToolRegistry()
        reg.register(ReadTool())
        _, settle = reg.materialize()
        result = await settle("unknown_tool", {})
        assert not result.success
        assert result.error is not None
        assert "unknown" in result.error.lower()

    async def test_settle_invalid_args(self) -> None:
        reg = ToolRegistry()
        reg.register(ReadTool())
        _, settle = reg.materialize()
        result = await settle("read", {"bad_arg": "value"})
        assert not result.success
