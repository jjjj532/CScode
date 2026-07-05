"""SyncEngine — multi-instance event synchronization.

P2-5: Sync allows multiple CScode instances to share events via:
1. Direct EventStore-to-EventStore sync (tests, in-process)
2. HTTP transport via REST API (/api/sync/events, /api/sync/push)

Sync protocol:
- Events are identified by (aggregate_id, seq) pair — idempotent dedup
- scan_events_global() uses rowid-based global ordering for incremental sync
- last_sync_seq tracks how far the local store has synced (inclusive max rowid seen)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from cscode.storage.event_store import EventStore

logger = logging.getLogger(__name__)


@dataclass
class SyncState:
    """Tracks sync progress for a pair of stores."""

    last_sync_seq: int = 0
    """Max global rowid seen during last sync."""


class SyncEngine:
    """Synchronize events between local and remote EventStores.

    Supports two modes:
    - Direct: push/pull with a local EventStore reference
      (used for tests and inter-process sync)
    - HTTP: push/pull via REST API calls
      (used for remote instances)

    Dedup: By (aggregate_id, seq) — the UNIQUE constraint on the events
    table means re-inserting the same (aggregate_id, seq) silently fails.
    """

    def __init__(
        self,
        local_store: EventStore,
        remote_url: str = "",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._local_store = local_store
        self._remote_url = remote_url.rstrip("/")
        self._http_client = http_client or httpx.AsyncClient()
        self._state = SyncState()

    @property
    def last_sync_seq(self) -> int:
        return self._state.last_sync_seq

    def set_sync_seq(self, seq: int) -> None:
        self._state.last_sync_seq = seq

    def reset_sync(self) -> None:
        """Reset sync state — next pull/push will re-sync from scratch."""
        self._state = SyncState()

    # ── Direct (EventStore-to-EventStore) ──────────────────────────

    async def pull(self, remote_store: EventStore | None = None) -> int:
        """Pull new events from remote and apply to local store.

        Args:
            remote_store: Direct EventStore reference (None = use HTTP).

        Returns:
            Number of new events applied locally.
        """
        if remote_store is not None:
            return await self._pull_direct(remote_store)
        return await self._pull_http()

    async def push(self, remote_store: EventStore | None = None) -> int:
        """Push local events to remote store.

        Args:
            remote_store: Direct EventStore reference (None = use HTTP).

        Returns:
            Number of events pushed.
        """
        if remote_store is not None:
            return await self._push_direct(remote_store)
        return await self._push_http()

    # ── Direct implementation ──────────────────────────────────────

    async def _pull_direct(self, remote_store: EventStore) -> int:
        """Pull events directly from another EventStore."""
        remote_events = await remote_store.scan_events_global(
            after_id=self._state.last_sync_seq
        )
        if not remote_events:
            return 0

        count = 0
        for event in remote_events:
            try:
                await self._local_store.append(
                    event.aggregate_id,
                    [{"type": event.type, "data": event.data}],
                )
                count += 1
            except Exception:
                # (aggregate_id, seq) duplicate — skip
                pass

        # Track the highest seq seen
        max_id = max(e.id for e in remote_events)
        self._state.last_sync_seq = max_id
        logger.info("Pulled %d events (max rowid: %d)", count, max_id)
        return count

    async def _push_direct(self, remote_store: EventStore) -> int:
        """Push events directly to another EventStore."""
        local_events = await self._local_store.scan_events_global(
            after_id=self._state.last_sync_seq
        )
        if not local_events:
            return 0

        count = 0
        for event in local_events:
            try:
                await remote_store.append(
                    event.aggregate_id,
                    [{"type": event.type, "data": event.data}],
                )
                count += 1
            except Exception:
                pass

        max_id = max(e.id for e in local_events)
        self._state.last_sync_seq = max_id
        logger.info("Pushed %d events (max rowid: %d)", count, max_id)
        return count

    # ── HTTP implementation ────────────────────────────────────────

    async def _pull_http(self) -> int:
        """Pull events via HTTP GET."""
        if not self._remote_url:
            raise RuntimeError("remote_url not configured for HTTP sync")

        resp = await self._http_client.get(
            f"{self._remote_url}/api/sync/events",
            params={"after_id": self._state.last_sync_seq},
        )
        resp.raise_for_status()
        raw_events: list[dict[str, Any]] = resp.json()
        if not raw_events:
            return 0

        count = 0
        for raw in raw_events:
            try:
                await self._local_store.append(
                    raw["aggregate_id"],
                    [{"type": raw["type"], "data": raw.get("data", {})}],
                )
                count += 1
            except Exception:
                pass

        max_id = max(e["id"] for e in raw_events)
        self._state.last_sync_seq = max_id
        logger.info("HTTP-pulled %d events (max rowid: %d)", count, max_id)
        return count

    async def _push_http(self) -> int:
        """Push events via HTTP POST."""
        if not self._remote_url:
            raise RuntimeError("remote_url not configured for HTTP sync")

        local_events = await self._local_store.scan_events_global(
            after_id=self._state.last_sync_seq
        )
        if not local_events:
            return 0

        payload = {
            "events": [
                {
                    "id": e.id,
                    "aggregate_id": e.aggregate_id,
                    "seq": e.seq,
                    "type": e.type,
                    "data": e.data,
                    "created_at": e.created_at,
                }
                for e in local_events
            ]
        }

        resp = await self._http_client.post(
            f"{self._remote_url}/api/sync/push",
            json=payload,
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()

        max_id = max(e.id for e in local_events)
        self._state.last_sync_seq = max_id
        pushed: int = result.get("pushed", 0)
        logger.info("HTTP-pushed %d events", pushed)
        return pushed
