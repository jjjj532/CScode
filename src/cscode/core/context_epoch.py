"""P0.2 — Context Epoch (SPEC §2.2).

Manages session context epoch lifecycle using System Context algebra (P0.1)
for baseline creation, change detection (reconcile), and compaction.

Each epoch is a snapshot of the SystemContext at a point in time,
stored in the context_epochs table for cross-session persistence.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, cast

from cscode.core.system_context import (
    SourceSnapshot,
    SystemContext,
)
from cscode.core.system_context import (
    initialize as sc_initialize,
)
from cscode.core.system_context import (
    reconcile as sc_reconcile,
)
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

# ─── Serialization helpers for SourceSnapshot ─────────────────────

SNAPSHOT_VERSION_KEY = "__v__"
SNAPSHOT_VERSION = 1


def _snapshot_to_dict(snapshot: dict[str, SourceSnapshot]) -> str:
    """Serialize SourceSnapshot dict to JSON string for DB storage."""
    raw: dict[str, dict[str, Any]] = {}
    for key, snap in snapshot.items():
        value = snap.value
        loaded_at = snap.loaded_at.isoformat()
        raw[key] = {"value": value, "loaded_at": loaded_at}
    raw[SNAPSHOT_VERSION_KEY] = {"value": SNAPSHOT_VERSION, "loaded_at": datetime.now().isoformat()}
    return json.dumps(raw, default=str)


def _snapshot_from_dict(raw: str) -> dict[str, SourceSnapshot]:
    """Deserialize JSON string back to SourceSnapshot dict."""
    data: dict[str, dict[str, Any]] = json.loads(raw)
    result: dict[str, SourceSnapshot] = {}
    for key, entry in data.items():
        if key == SNAPSHOT_VERSION_KEY:
            continue
        loaded_at: datetime
        if isinstance(entry["loaded_at"], str):
            loaded_at = datetime.fromisoformat(entry["loaded_at"])
        else:
            loaded_at = datetime.now()
        result[key] = SourceSnapshot(value=entry["value"], loaded_at=loaded_at)
    return result


# ─── Epoch helpers ────────────────────────────────────────────────


async def _get_next_epoch(db: Database, session_id: str) -> int:
    """Get the next epoch index for a session."""
    row = await db.fetchone(
        "SELECT COALESCE(MAX(epoch), -1) AS max_epoch FROM context_epochs WHERE session_id = ?",
        (session_id,),
    )
    max_epoch = row["max_epoch"] if row else -1
    return cast(int, max_epoch) + 1


_PERSISTED_EVENT_TYPES = frozenset({
    "prompt.admitted", "text.ended", "tool.success", "tool.failed",
})


async def _count_message_events(store: EventStore, session_id: str) -> int:
    """Count message-like events in a session (for compaction metadata)."""
    events = await store.read(session_id)
    return sum(1 for e in events if e.type in _PERSISTED_EVENT_TYPES)


# ═══════════════════════════════════════════════════════════════════
# SessionContextEpoch (SPEC §2.2.3)
# ═══════════════════════════════════════════════════════════════════


class SessionContextEpoch:
    """Manages session context epoch lifecycle.

    Each session has a sequence of epochs. An epoch captures the
    SystemContext state at a point in time, storing:
      - ``baseline``: rendered baseline text (LLM system message)
      - ``snapshot``: JSON-serialized ``SourceSnapshot`` dict (for reconcile)
      - ``baseline_seq``: last event seq covered by this epoch (for compaction)

    Usage::

        result = await SessionContextEpoch.initialize(db, context, "session_1")
        if result:
            baseline_text, baseline_seq = result
    """

    @staticmethod
    async def initialize(
        db: Database,
        context: SystemContext,
        session_id: str,
    ) -> tuple[str, int] | None:
        """Create the first (or a new) epoch for a session.

        Args:
            db: Database with ``context_epochs`` table.
            context: SystemContext to baseline from.
            session_id: Target session.

        Returns:
            ``(baseline, baseline_seq)`` where ``baseline_seq`` is always
            0 for a fresh epoch (no events compacted yet), or ``None`` if
            the SystemContext produced no renderable text.
        """
        # Initialize SystemContext to get baseline + snapshot
        generation = await sc_initialize(context)
        baseline_text = generation.baseline.strip()

        if not baseline_text:
            logger.debug("SessionContextEpoch.initialize: empty baseline, skipping")
            return None

        # Determine epoch index
        epoch_index = await _get_next_epoch(db, session_id)

        # Serialize snapshot
        snapshot_json = _snapshot_to_dict(generation.snapshot)

        # Persist to context_epochs table
        await db.execute(
            "INSERT INTO context_epochs "
            "(session_id, epoch, baseline_seq, snapshot, baseline, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, epoch_index, 0, snapshot_json, baseline_text, time.time()),
        )

        logger.debug(
            "SessionContextEpoch.initialize: session=%s epoch=%d baseline_len=%d",
            session_id, epoch_index, len(baseline_text),
        )

        return (baseline_text, 0)

    @staticmethod
    async def prepare(
        db: Database,
        events: EventStore,
        context: SystemContext,
        session_id: str,
    ) -> tuple[str, int]:
        """Prepare context text for a provider turn.

        If no epoch exists, auto-initializes one. Otherwise, reconciles
        the current SystemContext against the latest epoch's snapshot.

        Args:
            db: Database with ``context_epochs`` table.
            events: EventStore (reserved for future use, e.g. checking
                    for events beyond baseline).
            context: SystemContext to reconcile.
            session_id: Target session.

        Returns:
            ``(text, baseline_seq)`` where ``text`` is either the baseline
            text (unchanged) or an update description (when reconciled).
        """
        _ = events  # Reserved for future use

        # Get the latest epoch
        row = await db.fetchone(
            "SELECT epoch, baseline_seq, snapshot, baseline "
            "FROM context_epochs "
            "WHERE session_id = ? ORDER BY epoch DESC LIMIT 1",
            (session_id,),
        )

        if row is None:
            # No epoch — auto-initialize
            logger.debug("SessionContextEpoch.prepare: no epoch found, auto-initializing")
            result = await SessionContextEpoch.initialize(db, context, session_id)
            if result is not None:
                return result
            return ("", 0)

        baseline_seq: int = row["baseline_seq"]
        baseline_text: str = row["baseline"]
        snapshot_raw: str = row["snapshot"]

        # Deserialize snapshot and reconcile
        try:
            previous_snapshot = _snapshot_from_dict(snapshot_raw)
        except (json.JSONDecodeError, KeyError, ValueError):
            logger.warning(
                "SessionContextEpoch.prepare: corrupt snapshot for session=%s, using baseline",
                session_id,
            )
            return (baseline_text, baseline_seq)

        reconcile_result = await sc_reconcile(context, previous_snapshot)

        match reconcile_result:
            case _ if hasattr(reconcile_result, "text") and reconcile_result.text:  # type: ignore[union-attr]
                # Updated — return update description
                logger.debug("SessionContextEpoch.prepare: context changed for session=%s", session_id)
                return (reconcile_result.text, baseline_seq)  # type: ignore[union-attr]
            case _:
                # Unchanged or blocked — return baseline
                return (baseline_text, baseline_seq)

    @staticmethod
    async def compact(
        db: Database,
        events: EventStore,
        context: SystemContext,
        session_id: str,
    ) -> None:
        """Compact the session: create a new epoch with a fresh baseline.

        Appends a ``compaction`` event to the EventStore and inserts a
        new row in ``context_epochs``.

        Args:
            db: Database with ``context_epochs`` table.
            events: EventStore for reading session events and appending
                    the compaction event.
            context: SystemContext for the fresh baseline.
            session_id: Target session.
        """
        # Read all session events to determine baseline_seq
        all_events = await events.read(session_id)
        if not all_events:
            logger.debug("SessionContextEpoch.compact: no events, skipping")
            return

        baseline_seq = all_events[-1].seq

        # Create fresh baseline
        generation = await sc_initialize(context)
        baseline_text = generation.baseline.strip()
        if not baseline_text:
            logger.debug("SessionContextEpoch.compact: empty baseline, skipping")
            return

        # Determine epoch index
        epoch_index = await _get_next_epoch(db, session_id)

        # Serialize snapshot
        snapshot_json = _snapshot_to_dict(generation.snapshot)

        await db.execute(
            "INSERT INTO context_epochs "
            "(session_id, epoch, baseline_seq, snapshot, baseline, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, epoch_index, baseline_seq, snapshot_json, baseline_text, time.time()),
        )

        # Count message events for metadata
        message_count = sum(
            1 for e in all_events if e.type in _PERSISTED_EVENT_TYPES
        )

        # Append compaction event to EventStore
        await events.append(session_id, [
            {
                "type": "compaction",
                "data": {
                    "baseline_seq": baseline_seq,
                    "snapshot": baseline_text,
                    "message_count": message_count,
                },
            }
        ])

        logger.info(
            "SessionContextEpoch.compact: session=%s epoch=%d baseline_seq=%d messages=%d",
            session_id, epoch_index, baseline_seq, message_count,
        )
