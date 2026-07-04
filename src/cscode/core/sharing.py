from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cscode.storage.db import Database


@dataclass
class SharedSession:
    """A persisted share record for a session."""

    session_id: str
    id: str = ""
    title: str = ""
    created_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


class ShareStore:
    """SQLite-backed CRUD for session shares."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        session_id: str,
        title: str = "",
        expires_at: datetime | None = None,
    ) -> SharedSession:
        share = SharedSession(
            session_id=session_id,
            title=title,
            expires_at=expires_at,
        )
        await self._db.execute(
            """INSERT INTO shares (id, session_id, title, created_at, expires_at, is_active)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                share.id,
                share.session_id,
                share.title,
                share.created_at.isoformat() if share.created_at else None,
                share.expires_at.isoformat() if share.expires_at else None,
                1 if share.is_active else 0,
            ),
        )
        return share

    async def get(self, share_id: str) -> SharedSession | None:
        row = await self._db.fetchone(
            "SELECT * FROM shares WHERE id = ?", (share_id,)
        )
        if row is None:
            return None
        return self._row_to_share(row)

    async def list(self) -> list[SharedSession]:
        rows = await self._db.fetchall(
            "SELECT * FROM shares WHERE is_active = 1 "
            "AND (expires_at IS NULL OR expires_at > datetime('now')) "
            "ORDER BY created_at DESC"
        )
        return [self._row_to_share(r) for r in rows]

    async def list_by_session(self, session_id: str) -> list[SharedSession]:
        rows = await self._db.fetchall(
            "SELECT * FROM shares WHERE session_id = ? AND is_active = 1 "
            "ORDER BY created_at DESC",
            (session_id,),
        )
        return [self._row_to_share(r) for r in rows]

    async def deactivate(self, share_id: str) -> bool:
        row = await self._db.fetchone(
            "UPDATE shares SET is_active = 0 WHERE id = ? RETURNING id",
            (share_id,),
        )
        return row is not None

    async def delete(self, share_id: str) -> bool:
        row = await self._db.fetchone(
            "DELETE FROM shares WHERE id = ? RETURNING id",
            (share_id,),
        )
        return row is not None

    async def _insert_raw(self, share: SharedSession) -> None:
        """Insert a share directly (for test setup with specific values)."""
        await self._db.execute(
            """INSERT INTO shares (id, session_id, title, created_at, expires_at, is_active)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                share.id,
                share.session_id,
                share.title,
                share.created_at.isoformat() if share.created_at else None,
                share.expires_at.isoformat() if share.expires_at else None,
                1 if share.is_active else 0,
            ),
        )

    @staticmethod
    def _row_to_share(row) -> SharedSession:
        created = row["created_at"]
        if isinstance(created, str):
            created_dt = datetime.fromisoformat(created)
        else:
            created_dt = None

        expires = row["expires_at"]
        expires_dt: datetime | None = None
        if expires:
            if isinstance(expires, str):
                expires_dt = datetime.fromisoformat(expires)
            else:
                expires_dt = None

        return SharedSession(
            id=row["id"],
            session_id=row["session_id"],
            title=row["title"],
            created_at=created_dt,
            expires_at=expires_dt,
            is_active=bool(row["is_active"]),
        )
