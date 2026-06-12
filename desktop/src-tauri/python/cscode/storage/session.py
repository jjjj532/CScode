from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from cscode.core.messages import Message, MessageRole, Session
from cscode.storage.db import Database


class SessionStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        title: str = "",
        provider: str = "openai",
        model: str = "gpt-4o",
        session_id: str | None = None,
    ) -> Session:
        now = datetime.now(timezone.utc)
        session_id = session_id or str(uuid.uuid4())
        await self._db.conn.execute(
            """INSERT INTO sessions (id, title, provider, model, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, title, provider, model, now.isoformat(), now.isoformat()),
        )
        await self._db.conn.commit()
        return Session(
            id=session_id,
            title=title,
            provider=provider,
            model=model,
            created_at=now,
            updated_at=now,
        )

    async def get(self, session_id: str) -> Session | None:
        cursor = await self._db.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return Session(
            id=row["id"],
            title=row["title"],
            provider=row["provider"],
            model=row["model"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    async def list(self) -> list[Session]:
        cursor = await self._db.conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC")
        rows = await cursor.fetchall()
        return [
            Session(
                id=row["id"],
                title=row["title"],
                provider=row["provider"],
                model=row["model"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    async def delete(self, session_id: str) -> None:
        await self._db.conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        await self._db.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await self._db.conn.commit()

    async def save_messages(self, session_id: str, messages: list[Message]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for msg in messages:
            await self._db.conn.execute(
                """INSERT INTO messages
                   (session_id, role, content, tool_calls, tool_call_id, name, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    msg.role.value,
                    msg.content,
                    json.dumps(msg.tool_calls) if msg.tool_calls else None,
                    msg.tool_call_id,
                    msg.name,
                    now,
                ),
            )
        await self._db.conn.commit()

    async def get_messages(self, session_id: str) -> list[Message]:
        cursor = await self._db.conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [
            Message(
                role=MessageRole(row["role"]),
                content=row["content"],
                tool_calls=json.loads(row["tool_calls"]) if row["tool_calls"] else None,
                tool_call_id=row["tool_call_id"],
                name=row["name"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    async def update_title(self, session_id: str, title: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, session_id),
        )
        await self._db.conn.commit()
