"""Tests for new Slice 0.4 tools: Plan, Task, Truncate, OutputStore."""

from __future__ import annotations

import pytest

from cscode.tools2.output_store import OutputStoreInput, OutputStoreTool, ToolOutputStore
from cscode.tools2.plan import PlanInput, PlanTool
from cscode.tools2.task import TaskInput, TaskTool
from cscode.tools2.truncate import TruncateInput, TruncateTool

# ---------------------------------------------------------------------------
# PlanTool (0.4.1)
# ---------------------------------------------------------------------------

class TestPlanTool:
    tool = PlanTool()

    async def test_plan_creates_steps(self) -> None:
        result = await self.tool.execute(PlanInput(
            goal="Implement login feature",
            context="We use JWT auth",
        ))
        assert result.success
        assert result.data is not None
        assert result.data.plan_id
        assert len(result.data.steps) > 0
        assert all(s.description for s in result.data.steps)
        assert all(s.status == "pending" for s in result.data.steps)

    async def test_plan_requires_goal(self) -> None:
        result = await self.tool.execute(PlanInput(goal=""))
        assert not result.success
        assert result.error is not None

    async def test_plan_default_context(self) -> None:
        result = await self.tool.execute(PlanInput(goal="Refactor config"))
        assert result.success
        assert result.data is not None
        assert len(result.data.steps) >= 1


# ---------------------------------------------------------------------------
# TaskTool (0.4.2)
# ---------------------------------------------------------------------------

class TestTaskTool:
    tool = TaskTool()

    async def test_task_create(self) -> None:
        result = await self.tool.execute(TaskInput(
            action="create",
            description="Set up CI pipeline",
        ))
        assert result.success
        assert result.data is not None
        assert result.data.task_id
        assert result.data.status == "pending"

    async def test_task_list(self) -> None:
        result = await self.tool.execute(TaskInput(action="list"))
        assert result.success
        assert result.data is not None
        assert len(result.data.tasks) >= 0

    async def test_task_update_status(self) -> None:
        # Create first
        created = await self.tool.execute(TaskInput(action="create", description="Test task"))
        assert created.success and created.data
        task_id = created.data.task_id
        # Update
        result = await self.tool.execute(TaskInput(
            action="update",
            task_id=task_id,
            status="in_progress",
        ))
        assert result.success
        assert result.data is not None
        assert result.data.status == "in_progress"

    async def test_task_unknown_action(self) -> None:
        # Pydantic Literal validation catches invalid actions at construction
        with pytest.raises(ValueError, match="Input should be"):
            TaskInput(action="unknown")


# ---------------------------------------------------------------------------
# TruncateTool (0.4.3)
# ---------------------------------------------------------------------------

class TestTruncateTool:
    tool = TruncateTool()

    async def test_truncate_keep_recent(self) -> None:
        result = await self.tool.execute(TruncateInput(
            strategy="keep_recent",
            max_tokens=1000,
        ))
        assert result.success
        assert result.data is not None
        assert result.data.truncated
        assert result.data.tokens_freed >= 0

    async def test_truncate_drop_oldest(self) -> None:
        result = await self.tool.execute(TruncateInput(
            strategy="drop_oldest",
            max_tokens=500,
        ))
        assert result.success
        assert result.data is not None
        assert result.data.truncated

    async def test_truncate_unknown_strategy(self) -> None:
        # Pydantic Literal validation catches invalid strategies at construction
        with pytest.raises(ValueError, match="Input should be"):
            TruncateInput(strategy="unknown")

    async def test_truncate_requires_max_tokens(self) -> None:
        result = await self.tool.execute(TruncateInput(
            strategy="drop_oldest",
            max_tokens=0,
        ))
        assert not result.success
        assert result.error is not None


# ---------------------------------------------------------------------------
# OutputStore (0.4.4)
# ---------------------------------------------------------------------------

class TestOutputStore:
    """Tests for ToolOutputStore (the data backend) and OutputStoreTool (the LLM-facing tool)."""
    store = ToolOutputStore()
    tool = OutputStoreTool()

    async def test_store_save_and_get(self) -> None:
        result = await self.tool.execute(OutputStoreInput(
            action="save",
            key="test-key",
            data={"result": "hello"},
        ))
        assert result.success
        assert result.data is not None
        assert result.data.status == "saved"

        # Retrieve
        got = await self.tool.execute(OutputStoreInput(
            action="get",
            key="test-key",
        ))
        assert got.success
        assert got.data is not None
        assert got.data.data["result"] == "hello"

    async def test_store_list(self) -> None:
        # Save a couple entries
        await self.tool.execute(OutputStoreInput(action="save", key="k1", data={"v": 1}))
        await self.tool.execute(OutputStoreInput(action="save", key="k2", data={"v": 2}))
        result = await self.tool.execute(OutputStoreInput(action="list"))
        assert result.success
        assert result.data is not None
        assert len(result.data.keys) >= 2

    async def test_store_get_nonexistent(self) -> None:
        result = await self.tool.execute(OutputStoreInput(
            action="get",
            key="nonexistent-key-xyz",
        ))
        assert not result.success
        assert "not found" in (result.error or "").lower()

    async def test_store_unknown_action(self) -> None:
        # Pydantic Literal validation catches invalid actions at construction
        with pytest.raises(ValueError, match="Input should be"):
            OutputStoreInput(action="unknown")


class TestToolOutputStoreBounded:
    """Tests for BoundedOutput and bounded storage features."""

    @pytest.fixture(autouse=True)
    def reset_store(self) -> None:
        ToolOutputStore().clear()

    def test_bounded_output_small(self) -> None:
        """Output under threshold returns preview without truncation."""
        store = ToolOutputStore()
        text = "Hello, world!"
        result = store.save("test-key", text)
        assert result.preview == text
        assert not result.truncated
        assert result.managed_path is None

    def test_bounded_output_large_lines(self) -> None:
        """Output exceeding MAX_LINES is truncated and stored to disk."""
        store = ToolOutputStore(data_dir="/tmp/test-output-store")
        lines = [f"line {i}" for i in range(600)]
        text = "\n".join(lines)
        result = store.save("large-key", text)
        assert result.truncated
        assert result.managed_path is not None
        # Preview should have first 500 lines
        preview_lines = result.preview.split("\n")
        assert len(preview_lines) == 500

    def test_bounded_output_large_bytes(self) -> None:
        """Output exceeding MAX_BYTES is truncated."""
        store = ToolOutputStore()
        # Create a string larger than 512KB
        large = "x" * (600 * 1024)
        result = store.save("big-key", large)
        assert result.truncated
        assert len(result.preview.encode("utf-8")) <= 512 * 1024

    def test_bounded_output_no_file_backed_in_memory(self) -> None:
        """Without data_dir, large output is still bounded in memory."""
        store = ToolOutputStore()
        lines = [f"line {i}" for i in range(600)]
        text = "\n".join(lines)
        result = store.save("mem-key", text)
        assert result.truncated
        # Without data_dir, managed_path may be None (in-memory only)
        assert result.managed_path is None

    def test_cleanup_removes_session_entries(self) -> None:
        """Cleanup removes entries for a specific session."""
        store = ToolOutputStore()
        store.save("s1-key1", "data1", session_id="session-1")
        store.save("s1-key2", "data2", session_id="session-1")
        store.save("s2-key1", "data3", session_id="session-2")
        store.cleanup("session-1")
        assert store.get("s1-key1", session_id="session-1") is None
        assert store.get("s1-key2", session_id="session-1") is None
        # Other session should remain
        assert store.get("s2-key1", session_id="session-2") is not None

    def test_get_returns_bounded_data(self) -> None:
        """get() returns the stored metadata including saved_at."""
        store = ToolOutputStore()
        store.save("test-key", "test data")
        entry = store.get("test-key")
        assert entry is not None
        assert entry["data"] == "test data"
        assert "saved_at" in entry


# ---------------------------------------------------------------------------
# TruncateTool — G-2 真实会话存储接入（spec §4.2）
# ---------------------------------------------------------------------------

class TestTruncateToolRealStore:
    """注入真实 Compactor + EventStore 时，truncate 落地到会话存储。"""

    @pytest.fixture
    async def db(self, tmp_path):
        from cscode.storage.db import Database

        db = Database(db_path=tmp_path / "truncate.db")
        await db.init()
        yield db
        await db.close()

    async def test_truncate_with_real_store_creates_epoch(self, db) -> None:
        from cscode.server.compactor import Compactor
        from cscode.server.projector import Projector
        from cscode.storage.event_store import EventStore
        from cscode.tools2.truncate import TruncateTool

        store = EventStore(db)
        projector = Projector(db)
        compactor = Compactor(db, store, projector)
        tool = TruncateTool(compactor=compactor, event_store=store)

        await store.append("s1", [
            {"type": "prompt.admitted", "data": {"content": "hello"}},
            {"type": "text.ended", "data": {"content": "hi"}},
        ])

        result = await tool.execute(TruncateInput(
            strategy="keep_recent",
            max_tokens=1000,
            session_id="s1",
        ))
        assert result.success
        assert result.data is not None
        assert result.data.truncated

        # 真实 epoch 落库
        epoch = await projector._get_latest_epoch("s1")
        assert epoch is not None
        assert epoch["epoch"] == 1
        # 返回真实 token 差值（非输入值原样返回）
        assert result.data.tokens_freed >= 0
        assert result.data.remaining_tokens >= 0

    async def test_truncate_freed_tokens_exact_delta(self, db) -> None:
        """tokens_freed 是精确的真实差值（报告 §5.2 缺口 #3）。

        事件内容已知："hello"（5 ASCII → 1 token）+ "hi"（2 ASCII → 0 token）。
        compact 的 baseline_seq 覆盖全部事件 → remaining=0 → freed=total_before。
        """
        from cscode.core.token_estimate import estimate_tokens
        from cscode.server.compactor import Compactor
        from cscode.server.projector import Projector
        from cscode.storage.event_store import EventStore
        from cscode.tools2.truncate import TruncateTool

        store = EventStore(db)
        projector = Projector(db)
        compactor = Compactor(db, store, projector)
        tool = TruncateTool(compactor=compactor, event_store=store)

        await store.append("s2", [
            {"type": "prompt.admitted", "data": {"content": "hello"}},
            {"type": "text.ended", "data": {"content": "hi"}},
        ])

        result = await tool.execute(TruncateInput(
            strategy="keep_recent",
            max_tokens=1000,
            session_id="s2",
        ))
        assert result.success
        assert result.data is not None
        expected_total = estimate_tokens("hello") + estimate_tokens("hi")
        assert result.data.tokens_freed == expected_total
        assert result.data.remaining_tokens == 0

    async def test_truncate_without_session_id_fails(self, db) -> None:
        from cscode.server.compactor import Compactor
        from cscode.server.projector import Projector
        from cscode.storage.event_store import EventStore
        from cscode.tools2.truncate import TruncateTool

        store = EventStore(db)
        projector = Projector(db)
        compactor = Compactor(db, store, projector)
        tool = TruncateTool(compactor=compactor, event_store=store)

        result = await tool.execute(TruncateInput(
            strategy="keep_recent",
            max_tokens=1000,
        ))
        assert not result.success
        assert "session" in (result.error or "").lower()

    async def test_truncate_empty_session(self, db) -> None:
        from cscode.server.compactor import Compactor
        from cscode.server.projector import Projector
        from cscode.storage.event_store import EventStore
        from cscode.tools2.truncate import TruncateTool

        store = EventStore(db)
        projector = Projector(db)
        compactor = Compactor(db, store, projector)
        tool = TruncateTool(compactor=compactor, event_store=store)

        result = await tool.execute(TruncateInput(
            strategy="keep_recent",
            max_tokens=1000,
            session_id="empty-session",
        ))
        assert not result.success
        assert result.error is not None

    async def test_truncate_stub_without_deps_keeps_compat(self) -> None:
        """无依赖注入 → 保持 stub 行为（向后兼容）。"""
        from cscode.tools2.truncate import TruncateTool

        tool = TruncateTool()
        result = await tool.execute(TruncateInput(
            strategy="keep_recent",
            max_tokens=1000,
        ))
        assert result.success
        assert result.data is not None
        assert result.data.truncated
