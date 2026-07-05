"""Tests for P2-4: Control-Plane — workspace routing, session move, worktree.

Tests cover:
1. SessionProjector: workspace_id reconstruction from events
2. SessionV2.associate_workspace(): associate session with workspace
3. SessionV2.move_workspace(): move session to another workspace
4. WorkspaceStore.list_sessions(): list sessions by workspace
5. WorktreeManager: git worktree list/add/remove
"""

from __future__ import annotations

import time

import pytest

from cscode.core.session import SessionProjector, SessionV2
from cscode.core.workspace import WorkspaceStore
from cscode.storage.db import Database
from cscode.storage.event_store import Event, EventStore

# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
async def event_store() -> EventStore:
    db = Database(":memory:")
    await db.init()
    return EventStore(db)


@pytest.fixture
async def db() -> Database:
    db = Database(":memory:")
    await db.init()
    return db


@pytest.fixture
async def workspace_store(db: Database) -> WorkspaceStore:
    return WorkspaceStore(db)


# ═══════════════════════════════════════════════════════════════════
# SessionProjector: workspace_id reconstruction
# ═══════════════════════════════════════════════════════════════════


class TestSessionProjectorWorkspace:
    def test_project_no_workspace_events(self) -> None:
        """Default workspace_id is empty string."""
        events = [
            Event(
                aggregate_id="sess_001",
                seq=1,
                type="session.created",
                data={"title": "Test"},
                created_at=time.time(),
            )
        ]
        state = SessionProjector.project(events)
        assert state.workspace_id == ""

    def test_project_associate_event(self) -> None:
        """session.workspace.associated sets workspace_id."""
        events = [
            Event(
                aggregate_id="sess_001",
                seq=1,
                type="session.created",
                data={"title": "Test"},
                created_at=time.time(),
            ),
            Event(
                aggregate_id="sess_001",
                seq=2,
                type="session.workspace.associated",
                data={"workspace_id": "ws_abc"},
                created_at=time.time(),
            ),
        ]
        state = SessionProjector.project(events)
        assert state.workspace_id == "ws_abc"

    def test_project_move_event(self) -> None:
        """session.workspace.moved updates workspace_id."""
        events = [
            Event(
                aggregate_id="sess_001",
                seq=1,
                type="session.created",
                data={"title": "Test"},
                created_at=time.time(),
            ),
            Event(
                aggregate_id="sess_001",
                seq=2,
                type="session.workspace.associated",
                data={"workspace_id": "ws_old"},
                created_at=time.time(),
            ),
            Event(
                aggregate_id="sess_001",
                seq=3,
                type="session.workspace.moved",
                data={
                    "from_workspace_id": "ws_old",
                    "to_workspace_id": "ws_new",
                },
                created_at=time.time(),
            ),
        ]
        state = SessionProjector.project(events)
        assert state.workspace_id == "ws_new"


# ═══════════════════════════════════════════════════════════════════
# SessionV2: associate/move workspace
# ═══════════════════════════════════════════════════════════════════


class TestSessionV2Workspace:
    async def test_associate_workspace(self, event_store: EventStore) -> None:
        """associate_workspace() adds workspace_id and returns updated state."""
        session = await SessionV2.create(event_store, "gpt-4o")
        assert session.state.workspace_id == ""

        updated = await session.associate_workspace("ws_abc")
        assert updated.workspace_id == "ws_abc"

        # Re-load to verify persistence via events
        reloaded = await SessionV2.load(event_store, session.session_id)
        assert reloaded.state.workspace_id == "ws_abc"

    async def test_move_workspace(self, event_store: EventStore) -> None:
        """move_workspace() changes workspace_id."""
        session = await SessionV2.create(event_store, "gpt-4o")
        await session.associate_workspace("ws_old")
        await session.move_workspace("ws_new")

        reloaded = await SessionV2.load(event_store, session.session_id)
        assert reloaded.state.workspace_id == "ws_new"

    async def test_associate_invalid_workspace_raises(
        self, event_store: EventStore
    ) -> None:
        """Empty workspace_id raises ValueError."""
        session = await SessionV2.create(event_store, "gpt-4o")
        with pytest.raises(ValueError, match="workspace_id"):
            await session.associate_workspace("")

    async def test_create_with_workspace(self, event_store: EventStore) -> None:
        """SessionV2.create() accepts optional workspace_id."""
        session = await SessionV2.create(
            event_store, "gpt-4o", workspace_id="ws_abc"
        )
        assert session.state.workspace_id == "ws_abc"

        reloaded = await SessionV2.load(event_store, session.session_id)
        assert reloaded.state.workspace_id == "ws_abc"

    async def test_list_sessions_in_workspace(
        self, event_store: EventStore, workspace_store: WorkspaceStore
    ) -> None:
        """WorkspaceStore.list_sessions returns session ids by workspace."""
        ws = await workspace_store.create("Project A", "/tmp/a")
        ws2 = await workspace_store.create("Project B", "/tmp/b")

        s1 = await SessionV2.create(event_store, "gpt-4o")
        s2 = await SessionV2.create(event_store, "gpt-4o")
        s3 = await SessionV2.create(event_store, "gpt-4o")

        await s1.associate_workspace(ws.workspace_id)
        await s2.associate_workspace(ws.workspace_id)
        await s3.associate_workspace(ws2.workspace_id)

        sessions = await workspace_store.list_sessions(event_store, ws.workspace_id)
        assert len(sessions) == 2
        got_ids = {str(s.session_id) for s in sessions}
        expected = {str(s1.session_id), str(s2.session_id)}
        assert got_ids == expected


# ═══════════════════════════════════════════════════════════════════
# WorktreeManager (git worktree operations)
# ═══════════════════════════════════════════════════════════════════


class TestWorktreeManager:
    def test_list_worktrees_returns_list(self) -> None:
        """list_worktrees returns a list (may be empty in non-git dir)."""
        from cscode.core.control_plane import WorktreeManager

        wts = WorktreeManager.list_worktrees()
        assert isinstance(wts, list)

    def test_list_worktrees_in_git_repo(self) -> None:
        """In a git repo, list includes the main worktree."""
        from cscode.core.control_plane import WorktreeManager

        wts = WorktreeManager.list_worktrees()
        # Current repo should have at least the main worktree
        main = [w for w in wts if not w.bare]
        assert len(main) >= 1

    def test_parse_worktree_line(self) -> None:
        """_parse_line correctly parses git worktree list output."""
        from cscode.core.control_plane import WorktreeManager

        line = "/Users/user/project  abc1234 [main]"
        info = WorktreeManager._parse_line(line)
        assert info is not None
        assert info.path == "/Users/user/project"
        assert info.hash == "abc1234"
        assert info.branch == "main"
        assert not info.detached

    def test_parse_worktree_line_detached(self) -> None:
        """Detached HEAD is parsed correctly."""
        from cscode.core.control_plane import WorktreeManager

        line = "/Users/user/project  def5678 (detached HEAD)"
        info = WorktreeManager._parse_line(line)
        assert info is not None
        assert info.hash == "def5678"
        assert info.detached
        assert info.branch == ""

    def test_parse_worktree_line_bare(self) -> None:
        """Bare repo parsed correctly."""
        from cscode.core.control_plane import WorktreeManager

        line = "/Users/user/bare-repo  (bare)"
        info = WorktreeManager._parse_line(line)
        assert info is not None
        assert info.bare
        assert info.hash == ""
