from __future__ import annotations

import time

from cscode.server.projector import Projector
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore


class Compactor:
    def __init__(self, db: Database, event_store: EventStore, projector: Projector) -> None:
        self._db = db
        self._event_store = event_store
        self._projector = projector

    async def compact(self, session_id: str, system_prompt: str | None = None) -> int:
        events = await self._event_store.read(session_id)
        if not events:
            return 0

        baseline_seq = events[-1].seq
        message_count = sum(1 for e in events if e.type in ("prompt.admitted", "text.ended", "tool.success", "tool.failed"))

        snapshot = f"Previous context with {message_count} messages has been compacted."
        if system_prompt:
            snapshot = f"{system_prompt}\n\n[Compacted {message_count} earlier messages]"

        appended = await self._event_store.append(session_id, [
            {
                "type": "compaction",
                "data": {
                    "baseline_seq": baseline_seq,
                    "snapshot": snapshot,
                    "message_count": message_count,
                },
            }
        ])
        compaction_seq = appended[0].seq

        now = time.time()
        cursor = await self._db.conn.execute(
            "SELECT COALESCE(MAX(epoch), 0) FROM context_epochs WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        next_epoch = (row[0] if row and row[0] else 0) + 1

        await self._db.conn.execute(
            "INSERT INTO context_epochs (session_id, epoch, baseline_seq, snapshot, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, next_epoch, baseline_seq, snapshot, now),
        )
        await self._db.conn.commit()

        return baseline_seq
