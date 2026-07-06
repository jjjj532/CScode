from __future__ import annotations

import time
from typing import Any

from cscode.core.messages import Message, MessageRole
from cscode.storage.db import Database
from cscode.storage.event_store import Event, EventStore
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class Projector:
    """Maintains a materialized messages projection table from events.

    The messages table is an append-only CQRS read-side projection.
    It is rebuilt from events by ``BatchProjector``.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def on_event(self, event: Event) -> None:
        """Append a single event to the messages projection table.

        Only user/assistant/tool messages are persisted.
        Transient events (delta, step) are silently ignored.
        """
        event_type = event.type
        if event_type in ("text.delta", "step.started", "step.ended", "compaction", "session.created"):
            return

        session_id = event.aggregate_id
        now = time.time()
        event_seq = event.seq

        if event_type == "prompt.admitted":
            content = event.data.get("content") or event.data.get("prompt", "")
            if not content:
                return
            await self._db.conn.execute(
                """INSERT INTO messages (session_id, role, content, event_seq, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, "user", content, event_seq, now),
            )
        elif event_type == "text.ended":
            content = event.data.get("content", "")
            if not content:
                return
            await self._db.conn.execute(
                """INSERT INTO messages (session_id, role, content, event_seq, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, "assistant", content, event_seq, now),
            )
        elif event_type == "tool.success":
            result = event.data.get("result", "")
            name = event.data.get("name", "")
            await self._db.conn.execute(
                """INSERT INTO messages (session_id, role, content, name, event_seq, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, "tool", result, name, event_seq, now),
            )
        elif event_type == "tool.failed":
            error = event.data.get("error", "Unknown error")
            name = event.data.get("name", "")
            await self._db.conn.execute(
                """INSERT INTO messages (session_id, role, content, name, event_seq, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, "tool", f"Error: {error}", name, event_seq, now),
            )

        await self._db.conn.commit()

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Read messages from the projection table ordered by event_seq."""
        cursor = await self._db.conn.execute(
            "SELECT role, content, name, event_seq FROM messages WHERE session_id = ? ORDER BY event_seq ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def _get_latest_epoch(self, session_id: str) -> dict[str, Any] | None:
        logger.debug("Projector._get_latest_epoch: session_id=%s", session_id)
        cursor = await self._db.conn.execute(
            "SELECT epoch, baseline_seq, snapshot FROM context_epochs WHERE session_id = ? ORDER BY epoch DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "epoch": row["epoch"],
            "baseline_seq": row["baseline_seq"],
            "snapshot": row["snapshot"],
        }

    async def build_context(
        self,
        session_id: str,
        event_store: EventStore,
        system_prompt: str | None = None,
    ) -> list[Message]:
        logger.info("Projector.build_context: session_id=%s has_system_prompt=%s", session_id, system_prompt is not None)
        epoch = await self._get_latest_epoch(session_id)

        msgs: list[Message] = []
        after_seq = 0

        if epoch:
            msgs.append(Message(role=MessageRole.SYSTEM, content=epoch["snapshot"]))
            after_seq = epoch["baseline_seq"]
        elif system_prompt:
            msgs.append(Message(role=MessageRole.SYSTEM, content=system_prompt))

        events = await event_store.read(session_id, after_seq=after_seq)
        logger.debug("Projector.build_context: events_count=%d", len(events))

        for evt in events:
            if evt.type == "compaction":
                continue
            match evt.type:
                case "prompt.admitted":
                    content = evt.data.get("content") or evt.data.get("prompt", "")
                    if content:
                        msgs.append(Message(role=MessageRole.USER, content=content))
                case "text.ended":
                    content = evt.data.get("content", "")
                    if not content:
                        continue
                    msgs.append(Message(role=MessageRole.ASSISTANT, content=content))
                case "tool.called":
                    pass
                case "tool.success":
                    msgs.append(Message(role=MessageRole.TOOL, content=evt.data.get("result", ""), name=evt.data.get("name")))
                case "tool.failed":
                    msgs.append(Message(role=MessageRole.TOOL, content=f"Error: {evt.data.get('error', '')}", name=evt.data.get("name")))
        return msgs


class BatchProjector:
    """Rebuilds the CQRS messages projection table from raw events.

    Useful for recovery, backfilling after schema changes, and
    initial projection population.
    """

    def __init__(self, db: Database, event_store: EventStore) -> None:
        self._db = db
        self._event_store = event_store

    async def rebuild(self, session_id: str) -> None:
        """Clear and rebuild the projection table for a single session."""
        await self._db.conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        events = await self._event_store.read(session_id)
        # Use a fresh Projector instance for projection
        projector = Projector(self._db)
        for event in events:
            await projector.on_event(event)

    async def rebuild_all(self) -> None:
        """Rebuild projection for every session that has events."""
        aggregate_ids = await self._event_store.list_aggregate_ids()
        for sid in aggregate_ids:
            await self.rebuild(sid)
