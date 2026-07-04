"""Tests for P2-3: Project/Workspace — multi-project management.

Tests cover:
1. Workspace dataclass
2. WorkspaceStore CRUD (create/get/update/delete/list)
3. Recent workspaces ordering
4. Session listing by workspace
5. Migration 008 workspaces table
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from cscode.core.workspace import Workspace, WorkspaceStore
from cscode.storage.db import Database


@pytest.fixture
async def db() -> AsyncGenerator[Database, None]:  # type: ignore[misc]
    """Fixture: in-memory SQLite database with all migrations applied."""
    tmp = Path(tempfile.mktemp(suffix=".db"))
    database = Database(str(tmp))
    await database.init()
    yield database
    await database.close()
    if tmp.exists():
        tmp.unlink()


@pytest.fixture
async def store(db: Database) -> WorkspaceStore:
    """Fixture: WorkspaceStore backed by the test DB."""
    return WorkspaceStore(db)


class TestWorkspace:
    """Test the Workspace dataclass."""

    def test_create_workspace(self) -> None:
        """Workspace can be created with required fields."""
        now = time.time()
        ws = Workspace(
            workspace_id="ws_001",
            name="My Project",
            path="/home/user/my-project",
            config={},
            last_used_at=now,
            created_at=now,
            updated_at=now,
        )
        assert ws.workspace_id == "ws_001"
        assert ws.name == "My Project"
        assert ws.path == "/home/user/my-project"

    def test_workspace_repr(self) -> None:
        """Workspace repr is readable."""
        ws = Workspace(
            workspace_id="ws_001",
            name="Test",
            path="/tmp/test",
        )
        r = repr(ws)
        assert "workspace_id=" in r
        assert "Test" in r


class TestWorkspaceStore:
    """Test WorkspaceStore CRUD operations."""

    async def test_create_workspace(self, store: WorkspaceStore) -> None:
        """create() inserts a workspace and returns it with generated id."""
        ws = await store.create(
            name="My Project",
            path="/home/user/my-project",
        )
        assert ws.workspace_id is not None
        assert ws.name == "My Project"
        assert ws.path == "/home/user/my-project"
        assert ws.last_used_at > 0
        assert ws.created_at > 0

    async def test_get_workspace(self, store: WorkspaceStore) -> None:
        """get() returns a workspace by id."""
        created = await store.create(name="Test", path="/tmp/test")
        fetched = await store.get(created.workspace_id)
        assert fetched is not None
        assert fetched.workspace_id == created.workspace_id
        assert fetched.name == "Test"

    async def test_get_nonexistent(self, store: WorkspaceStore) -> None:
        """get() returns None for unknown id."""
        ws = await store.get("nonexistent")
        assert ws is None

    async def test_list_workspaces(self, store: WorkspaceStore) -> None:
        """list() returns all workspaces ordered by last_used_at desc."""
        ws1 = await store.create(name="Alpha", path="/tmp/alpha")
        ws2 = await store.create(name="Beta", path="/tmp/beta")

        await store.record_use(ws2.workspace_id)  # ws2 used more recently
        await store.record_use(ws1.workspace_id)
        await store.record_use(ws2.workspace_id)  # ws2 now most recent

        all_ws = await store.list()
        assert len(all_ws) == 2
        assert all_ws[0].workspace_id == ws2.workspace_id  # most recent first
        assert all_ws[1].workspace_id == ws1.workspace_id

    async def test_update_workspace(self, store: WorkspaceStore) -> None:
        """update() modifies workspace fields."""
        ws = await store.create(name="Old Name", path="/tmp/old")
        updated = await store.update(
            ws.workspace_id,
            name="New Name",
            path="/tmp/new",
        )
        assert updated is not None
        assert updated.name == "New Name"
        assert updated.path == "/tmp/new"

    async def test_update_nonexistent(self, store: WorkspaceStore) -> None:
        """update() returns None for unknown id."""
        result = await store.update("nonexistent", name="Nope")
        assert result is None

    async def test_delete_workspace(self, store: WorkspaceStore) -> None:
        """delete() removes a workspace."""
        ws = await store.create(name="To Delete", path="/tmp/delete")
        success = await store.delete(ws.workspace_id)
        assert success is True
        fetched = await store.get(ws.workspace_id)
        assert fetched is None

    async def test_delete_nonexistent(self, store: WorkspaceStore) -> None:
        """delete() returns False for unknown id."""
        result = await store.delete("nonexistent")
        assert result is False

    async def test_create_with_config(self, store: WorkspaceStore) -> None:
        """create() supports config_json."""
        config: dict[str, object] = {"provider": "anthropic", "model": "claude-3"}
        ws = await store.create(
            name="Config Test",
            path="/tmp/config",
            config=config,
        )
        fetched = await store.get(ws.workspace_id)
        assert fetched is not None
        assert fetched.config == config

    async def test_update_config(self, store: WorkspaceStore) -> None:
        """update() modifies config."""
        ws = await store.create(name="Cfg", path="/tmp/cfg")
        new_config: dict[str, object] = {"provider": "openai", "model": "gpt-4"}
        updated = await store.update(ws.workspace_id, config=new_config)
        assert updated is not None
        assert updated.config == new_config

    async def test_list_empty(self, store: WorkspaceStore) -> None:
        """list() returns empty list when no workspaces exist."""
        workspaces = await store.list()
        assert workspaces == []

    async def test_list_limit(self, store: WorkspaceStore) -> None:
        """list() respects the limit parameter."""
        for i in range(5):
            await store.create(name=f"WS {i}", path=f"/tmp/ws{i}")

        workspaces = await store.list(limit=3)
        assert len(workspaces) == 3

    async def test_persistence(self, store: WorkspaceStore) -> None:
        """Workspace survives across store instances (same DB)."""
        ws = await store.create(name="Persist", path="/tmp/persist")

        # New store, same db connection
        store2 = WorkspaceStore(store._db)
        fetched = await store2.get(ws.workspace_id)
        assert fetched is not None
        assert fetched.name == "Persist"


class TestWorkspaceValidation:
    """Test WorkspaceStore input validation."""

    async def test_create_empty_name(self, store: WorkspaceStore) -> None:
        """create() with empty name raises ValueError."""
        with pytest.raises(ValueError, match="name"):
            await store.create(name="", path="/tmp/test")

    async def test_create_empty_path(self, store: WorkspaceStore) -> None:
        """create() with empty path raises ValueError."""
        with pytest.raises(ValueError, match="path"):
            await store.create(name="Test", path="")

    async def test_update_empty_name(self, store: WorkspaceStore) -> None:
        """update() with empty name raises ValueError."""
        ws = await store.create(name="Valid", path="/tmp/valid")
        with pytest.raises(ValueError, match="name"):
            await store.update(ws.workspace_id, name="")


class TestRecentWorkspaces:
    """Test recent workspace listing."""

    async def test_recent_returns_most_recent_first(self, store: WorkspaceStore) -> None:
        """recent() orders by last_used_at descending."""
        ws1 = await store.create(name="First", path="/tmp/first")
        ws2 = await store.create(name="Second", path="/tmp/second")
        ws3 = await store.create(name="Third", path="/tmp/third")

        await store.record_use(ws3.workspace_id)
        await store.record_use(ws1.workspace_id)
        await store.record_use(ws2.workspace_id)

        recent = await store.recent(limit=3)
        assert recent[0].workspace_id == ws2.workspace_id
        assert recent[1].workspace_id == ws1.workspace_id
        assert recent[2].workspace_id == ws3.workspace_id

    async def test_recent_limits(self, store: WorkspaceStore) -> None:
        """recent() respects limit parameter."""
        for i in range(5):
            ws = await store.create(name=f"WS {i}", path=f"/tmp/ws{i}")
            await store.record_use(ws.workspace_id)

        recent = await store.recent(limit=2)
        assert len(recent) == 2
