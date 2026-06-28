from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from cscode.storage.db import Database
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Event:
    aggregate_id: str
    seq: int
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


class EventStore:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._listeners: dict[str, list[asyncio.Event]] = {}
        self._listener_lock = asyncio.Lock()
        self._append_locks: dict[str, asyncio.Lock] = {}
        self._append_lock_mutex = asyncio.Lock()

    async def append(self, aggregate_id: str, events: list[dict[str, Any]]) -> list[Event]:
        async with self._append_lock_mutex:
            if aggregate_id not in self._append_locks:
                self._append_locks[aggregate_id] = asyncio.Lock()

        async with self._append_locks[aggregate_id]:
            return await self._append_impl(aggregate_id, events)

    async def _append_impl(self, aggregate_id: str, events: list[dict[str, Any]]) -> list[Event]:
        now = time.time()
        event_types = [e.get("type", "?") for e in events]
        logger.debug("Appending %d events to %s: %s", len(events), aggregate_id, event_types)

        try:
            cursor = await self._db.conn.execute(
                "UPDATE event_sequences SET seq = seq + ? WHERE aggregate_id = ?",
                (len(events), aggregate_id),
            )
            if cursor.rowcount == 0:
                await self._db.conn.execute(
                    "INSERT INTO event_sequences (aggregate_id, seq) VALUES (?, ?)",
                    (aggregate_id, len(events)),
                )

            cursor = await self._db.conn.execute(
                "SELECT seq FROM event_sequences WHERE aggregate_id = ?", (aggregate_id,)
            )
            row = await cursor.fetchone()
            base_seq = int(row[0]) - len(events) if row else 0

            result = []
            for i, evt in enumerate(events):
                seq = base_seq + i + 1
                event = Event(
                    aggregate_id=aggregate_id,
                    seq=seq,
                    type=evt["type"],
                    data=evt.get("data", {}),
                    created_at=now,
                )
                await self._db.conn.execute(
                    "INSERT INTO events (aggregate_id, seq, type, data, created_at) VALUES (?, ?, ?, ?, ?)",
                    (aggregate_id, seq, event.type, json.dumps(event.data), now),
                )
                result.append(event)

            await self._db.conn.commit()
            await self._notify(aggregate_id)
            logger.debug("Committed %d events for %s (seq: %d-%d)", len(result), aggregate_id, result[0].seq, result[-1].seq)
            return result
        except BaseException:
            logger.warning("Rollback after error in _append_impl for %s", aggregate_id)
            await self._db.conn.rollback()
            raise

    # Note: `limit` truncates results; callers should check has_more or paginate.
    async def read(
        self, aggregate_id: str, after_seq: int = 0, limit: int = 1000
    ) -> list[Event]:
        logger.debug("Reading events for %s after_seq=%d limit=%d", aggregate_id, after_seq, limit)
        cursor = await self._db.conn.execute(
            "SELECT * FROM events WHERE aggregate_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
            (aggregate_id, after_seq, limit),
        )
        rows = await cursor.fetchall()
        return [
            Event(
                aggregate_id=r["aggregate_id"],
                seq=r["seq"],
                type=r["type"],
                data=json.loads(r["data"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def subscribe(
        self, aggregate_id: str, after_seq: int = 0
    ) -> AsyncIterator[Event]:
        logger.debug("Subscribe started: %s after_seq=%d", aggregate_id, after_seq)
        while True:
            events = await self.read(aggregate_id, after_seq)
            for e in events:
                yield e
                after_seq = e.seq
            if not events:
                evt = asyncio.Event()
                async with self._listener_lock:
                    self._listeners.setdefault(aggregate_id, []).append(evt)
                try:
                    await asyncio.wait_for(evt.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                finally:
                    async with self._listener_lock:
                        if aggregate_id in self._listeners:
                            self._listeners[aggregate_id] = [
                                e for e in self._listeners[aggregate_id] if e is not evt
                            ]

    async def _notify(self, aggregate_id: str) -> None:
        async with self._listener_lock:
            listeners = self._listeners.get(aggregate_id, [])
            if listeners:
                logger.debug("Notifying %d listeners for %s", len(listeners), aggregate_id)
            for evt in listeners:
                evt.set()
