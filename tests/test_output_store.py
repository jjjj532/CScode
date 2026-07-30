from __future__ import annotations

import pathlib

import pytest
from pydantic import ValidationError

from cscode.tools2.output_store import (
    BoundedOutput,
    OutputStoreInput,
    OutputStoreTool,
    ToolOutputStore,
    _truncate_content,
)


class TestTruncateContent:
    """_truncate_content: line/byte boundary enforcement."""

    def test_short_content_not_truncated(self) -> None:
        preview, truncated = _truncate_content("hello world")
        assert preview == "hello world"
        assert not truncated

    def test_excessive_lines_truncated(self) -> None:
        content = "\n".join(f"line{i}" for i in range(600))
        preview, truncated = _truncate_content(content)
        assert truncated
        assert len(preview.split("\n")) == 500

    def test_excessive_bytes_truncated(self) -> None:
        content = "x" * (600 * 1024)
        preview, truncated = _truncate_content(content)
        assert truncated
        assert len(preview.encode("utf-8")) <= 512 * 1024

    def test_exact_line_boundary_not_truncated(self) -> None:
        content = "\n".join(f"line{i}" for i in range(500))
        preview, truncated = _truncate_content(content)
        assert not truncated
        assert preview == content

    def test_exact_byte_boundary_not_truncated(self) -> None:
        content = "x" * (512 * 1024)
        preview, truncated = _truncate_content(content)
        assert not truncated

    def test_empty_string(self) -> None:
        preview, truncated = _truncate_content("")
        assert preview == ""
        assert not truncated


class TestToolOutputStore:
    """ToolOutputStore backend: save / get / list / cleanup."""

    @pytest.fixture(autouse=True)
    def _reset_store(self) -> None:
        ToolOutputStore().clear()

    async def test_save_and_get(self) -> None:
        store = ToolOutputStore()
        result = store.save("mykey", "hello world")
        assert result.preview == "hello world"
        assert not result.truncated
        assert result.managed_path is None

        entry = store.get("mykey")
        assert entry is not None
        assert entry["data"] == "hello world"

    async def test_save_with_session_scoping(self) -> None:
        store = ToolOutputStore()
        store.save("key", "session-data", session_id="sess_1")
        store.save("key", "global-data")

        global_entry = store.get("key")
        assert global_entry is not None
        assert global_entry["data"] == "global-data"

        session_entry = store.get("key", session_id="sess_1")
        assert session_entry is not None
        assert session_entry["data"] == "session-data"

    async def test_get_fallback_to_global(self) -> None:
        store = ToolOutputStore()
        store.save("key", "global")
        entry = store.get("key", session_id="sess_unknown")
        assert entry is not None
        assert entry["data"] == "global"

    async def test_get_not_found(self) -> None:
        store = ToolOutputStore()
        result = store.get("nonexistent")
        assert result is None

    async def test_list_keys(self) -> None:
        store = ToolOutputStore()
        store.save("a", 1)
        store.save("b", 2)
        store.save("c", 3)
        keys = store.list_keys()
        assert sorted(keys) == ["a", "b", "c"]

    async def test_list_keys_filter_by_session(self) -> None:
        store = ToolOutputStore()
        store.save("k1", "x", session_id="sess_a")
        store.save("k2", "y", session_id="sess_a")
        store.save("k3", "z", session_id="sess_b")
        assert sorted(store.list_keys(session_id="sess_a")) == ["k1", "k2"]
        assert sorted(store.list_keys(session_id="sess_b")) == ["k3"]

    async def test_cleanup_removes_session_data(self) -> None:
        store = ToolOutputStore()
        store.save("k1", "x", session_id="sess_1")
        store.save("k2", "y", session_id="sess_1")
        store.save("k3", "z")  # global, should survive
        store.cleanup("sess_1")
        assert store.get("k1", session_id="sess_1") is None
        assert store.get("k2", session_id="sess_1") is None
        assert store.get("k3") is not None

    async def test_clear_removes_all(self) -> None:
        store = ToolOutputStore()
        store.save("a", 1)
        store.save("b", 2)
        store.clear()
        assert store.list_keys() == []

    async def test_save_non_string_data(self) -> None:
        store = ToolOutputStore()
        store.save("dict", {"nested": True})
        entry = store.get("dict")
        assert entry is not None
        assert entry["data"] == {"nested": True}

    async def test_save_with_disk_overflow(self, tmp_path: pathlib.Path) -> None:
        store = ToolOutputStore(data_dir=str(tmp_path))
        content = "\n".join(f"line{i}" for i in range(600))
        result = store.save("big", content)
        assert result.truncated
        assert result.managed_path is not None
        assert pathlib.Path(result.managed_path).exists()

        disk_content = pathlib.Path(result.managed_path).read_text(encoding="utf-8")
        assert disk_content == content

    async def test_cleanup_removes_disk_files(self, tmp_path: pathlib.Path) -> None:
        store = ToolOutputStore(data_dir=str(tmp_path))
        content = "\n".join(f"line{i}" for i in range(600))
        r1 = store.save("big1", content, session_id="sess_1")
        r2 = store.save("big2", content, session_id="sess_1")
        assert r1.managed_path is not None
        assert r2.managed_path is not None
        assert pathlib.Path(r1.managed_path).exists()
        assert pathlib.Path(r2.managed_path).exists()

        store.cleanup("sess_1")
        assert not pathlib.Path(r1.managed_path).exists()
        assert not pathlib.Path(r2.managed_path).exists()

    async def test_cleanup_no_data_dir(self) -> None:
        store = ToolOutputStore()
        store.save("k", "v", session_id="sess_1")
        store.cleanup("sess_1")


class TestOutputStoreTool:
    """OutputStoreTool: execute() dispatch."""

    @pytest.fixture(autouse=True)
    def _reset_store(self) -> None:
        ToolOutputStore().clear()

    async def test_tool_save(self) -> None:
        tool = OutputStoreTool()
        result = await tool.execute(OutputStoreInput(action="save", key="k", data="v"))
        assert result.success is True

    async def test_tool_save_missing_key(self) -> None:
        tool = OutputStoreTool()
        result = await tool.execute(OutputStoreInput(action="save", data="v"))
        assert result.success is False
        assert "key" in (result.error or "")

    async def test_tool_get(self) -> None:
        tool = OutputStoreTool()
        await tool.execute(OutputStoreInput(action="save", key="k", data="hello"))
        result = await tool.execute(OutputStoreInput(action="get", key="k"))
        assert result.success is True
        assert result.data is not None
        assert result.data.data == "hello"

    async def test_tool_get_not_found(self) -> None:
        tool = OutputStoreTool()
        result = await tool.execute(OutputStoreInput(action="get", key="nonexistent"))
        assert result.success is False
        assert "not found" in (result.error or "")

    async def test_tool_list(self) -> None:
        tool = OutputStoreTool()
        await tool.execute(OutputStoreInput(action="save", key="a", data=1))
        await tool.execute(OutputStoreInput(action="save", key="b", data=2))
        result = await tool.execute(OutputStoreInput(action="list"))
        assert result.success is True
        assert result.data is not None
        assert sorted(result.data.keys) == ["a", "b"]

    async def test_tool_unknown_action_rejected(self) -> None:
        """Pydantic rejects invalid action literals."""
        with pytest.raises(ValidationError):
            OutputStoreInput(action="unknown")  # type: ignore[arg-type]

    async def test_tool_get_missing_key(self) -> None:
        tool = OutputStoreTool()
        result = await tool.execute(OutputStoreInput(action="get"))
        assert result.success is False
        assert "key" in (result.error or "")
