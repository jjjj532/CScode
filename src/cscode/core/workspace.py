"""P2-3: Project/Workspace — multi-project management.

Provides a Workspace dataclass and WorkspaceStore backed by SQLite.
Each workspace represents a code project directory with optional
configuration overrides and session association.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List

from cscode.schema.ids import SessionID
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore
from cscode.utils.logging import get_logger

if TYPE_CHECKING:
    from cscode.core.session import SessionV2

logger = get_logger(__name__)


@dataclass
class Workspace:
    """A project workspace with path and optional config.

    Attributes:
        workspace_id: UUID string (auto-generated on create).
        name: Human-readable project name.
        path: Absolute filesystem path to the project.
        config: Optional config overrides (provider, model, etc.).
        last_used_at: Unix timestamp of last use (for recent ordering).
        created_at: Unix timestamp of creation.
        updated_at: Unix timestamp of last update.
    """

    workspace_id: str = ""
    name: str = ""
    path: str = ""
    config: dict[str, object] = field(default_factory=dict)
    last_used_at: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0


class WorkspaceStore:
    """SQLite-backed workspace store.

    All mutations are persisted immediately.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── Create ──────────────────────────────────────────────────────

    async def create(
        self,
        name: str,
        path: str,
        config: dict[str, object] | None = None,
    ) -> Workspace:
        """Create a new workspace.

        Args:
            name: Project name (must be non-empty).
            path: Absolute project path (must be non-empty).
            config: Optional config overrides.

        Returns:
            The created Workspace.

        Raises:
            ValueError: If name or path is empty.
        """
        if not name or not name.strip():
            raise ValueError("name must be non-empty")
        if not path or not path.strip():
            raise ValueError("path must be non-empty")

        workspace_id = str(uuid.uuid4())
        now = time.time()
        config_json = json.dumps(config or {})

        await self._db.execute(
            "INSERT INTO workspaces (id, name, path, config_json, last_used_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (workspace_id, name.strip(), path.strip(), config_json, now, now, now),
        )

        return Workspace(
            workspace_id=workspace_id,
            name=name.strip(),
            path=path.strip(),
            config=config or {},
            last_used_at=now,
            created_at=now,
            updated_at=now,
        )

    # ── Read ────────────────────────────────────────────────────────

    async def get(self, workspace_id: str) -> Workspace | None:
        """Get a workspace by id.

        Returns None if not found.
        """
        row = await self._db.fetchone(
            "SELECT * FROM workspaces WHERE id = ?",
            (workspace_id,),
        )
        if row is None:
            return None
        return self._row_to_workspace(row)

    async def list(self, limit: int = 50) -> List[Workspace]:
        """List all workspaces ordered by last_used_at descending.

        Args:
            limit: Maximum number of workspaces to return (default 50).
        """
        rows = await self._db.fetchall(
            "SELECT * FROM workspaces ORDER BY last_used_at DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_workspace(r) for r in rows]

    async def recent(self, limit: int = 10) -> List[Workspace]:
        """Return recently used workspaces.

        Alias for list() with a smaller default limit for the "recent"
        quick-access feature.
        """
        workspaces = await self.list(limit=limit)
        return workspaces

    async def list_sessions(
        self, event_store: EventStore, workspace_id: str
    ) -> List[SessionV2]:
        """List all sessions associated with the given workspace.

        Scans event store for session.workspace.associated/.moved events
        to determine which sessions belong to this workspace.

        Args:
            event_store: EventStore instance for scanning workspace events.
            workspace_id: The workspace ID to filter sessions by.

        Returns:
            List of SessionV2 instances currently in this workspace.
        """
        workspace_events = await event_store.scan_events_by_type(
            "session.workspace.associated",
            "session.workspace.moved",
        )

        session_workspace: dict[str, str] = {}
        for evt in workspace_events:
            if evt.type == "session.workspace.associated":
                session_workspace[evt.aggregate_id] = str(
                    evt.data.get("workspace_id", "")
                )
            elif evt.type == "session.workspace.moved":
                session_workspace[evt.aggregate_id] = str(
                    evt.data.get("to_workspace_id", "")
                )

        from cscode.core.session import SessionV2

        result: List[SessionV2] = []
        for sess_id, ws_id in session_workspace.items():
            if ws_id == workspace_id:
                try:
                    session = await SessionV2.load(
                        event_store, SessionID(sess_id)
                    )
                    result.append(session)
                except Exception:
                    logger.warning(
                        "Failed to load session %s for workspace %s",
                        sess_id, workspace_id,
                    )
        return result

    # ── Update ──────────────────────────────────────────────────────

    async def update(
        self,
        workspace_id: str,
        name: str | None = None,
        path: str | None = None,
        config: dict[str, object] | None = None,
    ) -> Workspace | None:
        """Update workspace fields.

        Only provided fields are updated. Returns None if not found.
        Raises ValueError if name is provided and empty.
        """
        existing = await self.get(workspace_id)
        if existing is None:
            return None

        new_name = name if name is not None else existing.name
        if new_name is not None and not new_name.strip():
            raise ValueError("name must be non-empty")

        new_path = path if path is not None else existing.path
        new_config = config if config is not None else existing.config
        now = time.time()
        config_json = json.dumps(new_config)

        await self._db.execute(
            "UPDATE workspaces SET name = ?, path = ?, config_json = ?, updated_at = ? WHERE id = ?",
            (new_name.strip(), new_path.strip(), config_json, now, workspace_id),
        )

        return Workspace(
            workspace_id=workspace_id,
            name=new_name.strip(),
            path=new_path.strip(),
            config=new_config,
            last_used_at=existing.last_used_at,
            created_at=existing.created_at,
            updated_at=now,
        )

    async def record_use(self, workspace_id: str) -> None:
        """Record that a workspace was used (updates last_used_at).

        Idempotent; does nothing if workspace does not exist.
        """
        now = time.time()
        await self._db.execute(
            "UPDATE workspaces SET last_used_at = ?, updated_at = ? WHERE id = ?",
            (now, now, workspace_id),
        )

    # ── Delete ──────────────────────────────────────────────────────

    async def delete(self, workspace_id: str) -> bool:
        """Delete a workspace.

        Returns True if deleted, False if not found.
        """
        existing = await self.get(workspace_id)
        if existing is None:
            return False
        await self._db.execute(
            "DELETE FROM workspaces WHERE id = ?",
            (workspace_id,),
        )
        logger.info("Deleted workspace: %s (%s)", workspace_id, existing.name)
        return True

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _row_to_workspace(row: Any) -> Workspace:
        """Convert a SQLite row to a Workspace."""
        config: dict[str, object] = {}
        raw_config = row["config_json"]
        if raw_config:
            try:
                parsed = json.loads(raw_config)
                if isinstance(parsed, dict):
                    config = parsed
            except (json.JSONDecodeError, TypeError):
                logger.warning("Invalid config_json for workspace %s: %s", row["id"], raw_config)

        return Workspace(
            workspace_id=row["id"],
            name=row["name"],
            path=row["path"],
            config=config,
            last_used_at=row["last_used_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
