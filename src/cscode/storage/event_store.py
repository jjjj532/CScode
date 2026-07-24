from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator

from cscode.schema.events import PersistenceEvent as Event  # noqa: F401 — type moved to schema
from cscode.storage.db import Database
from cscode.utils.logging import get_logger

__all__ = [
    "Event",
    "EventStore",
]

logger = get_logger(__name__)


class EventStore:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._listeners: dict[str, list[asyncio.Event]] = {}
        self._listener_lock = asyncio.Lock()
        self._append_locks: dict[str, asyncio.Lock] = {}
        self._append_lock_mutex = asyncio.Lock()

    async def append(self, aggregate_id: str, events: list[dict[str, Any]]) -> list[Event]:
        _start = time.monotonic()
        async with self._append_lock_mutex:
            if aggregate_id not in self._append_locks:
                self._append_locks[aggregate_id] = asyncio.Lock()

        async with self._append_locks[aggregate_id]:
            result = await self._append_impl(aggregate_id, events)
            logger.info("event_store.append aggregate=%s events=%d duration_ms=%.0f", aggregate_id, len(events), (time.monotonic() - _start) * 1000)
            return result

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
                await self._db.conn.execute(
                    "INSERT INTO events (aggregate_id, seq, type, data, created_at) VALUES (?, ?, ?, ?, ?)",
                    (aggregate_id, seq, evt["type"], json.dumps(evt.get("data", {})), now),
                )
                cursor = await self._db.conn.execute("SELECT last_insert_rowid()")
                row = await cursor.fetchone()
                event_id = int(row[0]) if row else 0
                event = Event(
                    id=event_id,
                    aggregate_id=aggregate_id,
                    seq=seq,
                    type=evt["type"],
                    data=evt.get("data", {}),
                    created_at=now,
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
        _start = time.monotonic()
        logger.debug("Reading events for %s after_seq=%d limit=%d", aggregate_id, after_seq, limit)
        cursor = await self._db.conn.execute(
            "SELECT * FROM events WHERE aggregate_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
            (aggregate_id, after_seq, limit),
        )
        rows = await cursor.fetchall()
        result = [
            Event(
                id=r["id"],
                aggregate_id=r["aggregate_id"],
                seq=r["seq"],
                type=r["type"],
                data=json.loads(r["data"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]
        logger.info("event_store.read aggregate=%s events=%d duration_ms=%.0f", aggregate_id, len(result), (time.monotonic() - _start) * 1000)
        return result

    async def scan_events_global(
        self, after_id: int = 0, limit: int = 100
    ) -> list[Event]:
        """Scan all events globally ordered by auto-increment id.

        This is the primary method for incremental sync — new events always
        get monotonically increasing ids via AUTOINCREMENT.

        Args:
            after_id: Only return events with id > after_id (0 = all).
            limit: Maximum number of events to return (default 100).

        Returns:
            List of events ordered by id ascending.
        """
        cursor = await self._db.conn.execute(
            "SELECT * FROM events WHERE id > ? ORDER BY id ASC LIMIT ?",
            (after_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            Event(
                id=r["id"],
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

    async def scan_events_by_type(self, *types: str) -> list[Event]:
        """Scan events across all aggregates by type(s).

        Args:
            *types: Event types to filter by.

        Returns:
            List of matching events ordered by aggregate_id, seq.
        """
        placeholders = ",".join("?" for _ in types)
        cursor = await self._db.conn.execute(
            f"SELECT * FROM events WHERE type IN ({placeholders}) ORDER BY aggregate_id, seq ASC",
            types,
        )
        rows = await cursor.fetchall()
        return [
            Event(
                id=r["id"],
                aggregate_id=r["aggregate_id"],
                seq=r["seq"],
                type=r["type"],
                data=json.loads(r["data"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def list_aggregate_ids(self) -> list[str]:
        """List all aggregate IDs that have events."""
        cursor = await self._db.conn.execute(
            "SELECT DISTINCT aggregate_id FROM events ORDER BY aggregate_id"
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def _notify(self, aggregate_id: str) -> None:
        async with self._listener_lock:
            listeners = self._listeners.get(aggregate_id, [])
            if listeners:
                logger.debug("Notifying %d listeners for %s", len(listeners), aggregate_id)
            for evt in listeners:
                evt.set()
