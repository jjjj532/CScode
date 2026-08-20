from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from cscode.core.compression import serialize_messages
from cscode.schema.events import PersistenceEvent
from cscode.schema.messages import Message
from cscode.server.projector import Projector
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

#: Serialize events into messages for the summarizer (kept loose: events → text lines).
#: When no summarizer is provided, the compacted snapshot stays the compatible text form.
Summarizer = Callable[[str], str]


class Compactor:
    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        projector: Projector,
        summarizer: Summarizer | None = None,
    ) -> None:
        self._db = db
        self._event_store = event_store
        self._projector = projector
        self._summarizer = summarizer

    async def compact(self, session_id: str, system_prompt: str | None = None) -> int:
        logger.info("Compactor.compact: session_id=%s has_system_prompt=%s", session_id, system_prompt is not None)
        events = await self._event_store.read(session_id)
        if not events:
            return 0

        # baseline_seq = last event seq: read(after_seq=baseline_seq) excludes all compacted events
        baseline_seq = events[-1].seq

        message_count = sum(1 for e in events if e.type in ("prompt.admitted", "text.ended", "tool.success", "tool.failed"))
        logger.debug("Compactor.compact: baseline_seq=%d message_count=%d", baseline_seq, message_count)

        snapshot = self._build_snapshot(events, message_count, system_prompt)

        await self._event_store.append(session_id, [
            {
                "type": "compaction",
                "data": {
                    "baseline_seq": baseline_seq,
                    "snapshot": snapshot,
                    "message_count": message_count,
                },
            }
        ])

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

        logger.info("Compactor.compact: done session_id=%s next_epoch=%d baseline_seq=%d", session_id, next_epoch, baseline_seq)
        return baseline_seq

    def _build_snapshot(
        self,
        events: Sequence[PersistenceEvent],
        message_count: int,
        system_prompt: str | None,
    ) -> str:
        """Build the compaction snapshot.

        With a summarizer, serialize the compacted events and run the
        summarizer over them; on summarizer failure, log and fall back to the
        compatible fixed text (never silently swallow — Ratchet rule).
        """
        if self._summarizer is not None:
            try:
                serialized = serialize_messages(self._events_to_messages(events))
                summary = self._summarizer(serialized)
                if summary:
                    return summary
                logger.warning("Compactor: summarizer returned empty summary, falling back to text")
            except Exception:
                logger.exception("Compactor: summarizer failed, falling back to text")

        if system_prompt:
            return f"{system_prompt}\n\n[Compacted {message_count} earlier messages]"
        return f"Previous context with {message_count} messages has been compacted."

    def _events_to_messages(self, events: Sequence[PersistenceEvent]) -> list[Message]:
        """Project raw events into text lines for the summarizer.

        Kept loose on purpose: events carry role/content when available;
        otherwise they degrade to ``[type]: data`` lines. The summarizer
        contract only needs readable text, not a full projection.
        """
        messages: list[Message] = []
        for e in events:
            data = getattr(e, "data", None) or {}
            content = data.get("content") if isinstance(data, dict) else None
            role = data.get("role") if isinstance(data, dict) else None
            if isinstance(content, str) and content:
                messages.append(Message.from_text(role or "user", content))
            else:
                messages.append(Message.user(f"[{getattr(e, 'type', 'event')}]: {str(data)[:200]}"))
        return messages
