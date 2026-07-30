"""Tests for P0.2 Context Epoch (SPEC §2.2).

Tests validate the SessionContextEpoch class with three static methods:
- initialize(db, context, session_id) → tuple[str, int] | None
- prepare(db, events, context, session_id) → tuple[str, int]
- compact(db, events, context, session_id) → None

Integration with SystemContext algebra (P0.1) and context_epochs table.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from cscode.core.context_epoch import SessionContextEpoch
from cscode.core.system_context import (
    ContextKey,
    ContextSource,
    SystemContext,
    make,
)


@pytest.fixture
async def db(tmp_path: Any) -> Any:
    from cscode.storage.db import Database

    _db = Database(db_path=tmp_path / "test.db")
    await _db.init()
    yield _db
    await _db.close()


@pytest.fixture
def event_store(db: Any) -> Any:
    from cscode.storage.event_store import EventStore
    return EventStore(db)


@pytest.fixture
def date_context() -> SystemContext:
    """A SystemContext with a single date source."""
    async def load_date() -> str:
        return "2026-07-28"

    source = ContextSource(
        key=ContextKey("test/date"),
        load=load_date,
        baseline=lambda d: f"Today: {d}",
        update=lambda old, new: f"Date changed: {old} → {new}",
    )
    return make(source)


@pytest.fixture
def mutable_context() -> tuple[SystemContext, list[str]]:
    """A SystemContext where the date can be mutated."""
    values: list[str] = ["2026-01-01"]

    async def load_date() -> str:
        return values[0]

    source = ContextSource(
        key=ContextKey("test/date"),
        load=load_date,
        baseline=lambda d: f"Today: {d}",
        update=lambda old, new: f"Date changed: {old} → {new}",
    )
    ctx = make(source)
    return ctx, values


# ═══════════════════════════════════════════════════════════════════
# SessionContextEpoch.initialize()
# ═══════════════════════════════════════════════════════════════════

class TestInitialize:
    """SPEC §2.2.3: initialize(db, context, session_id) → tuple[str, int] | None"""

    @pytest.mark.asyncio
    async def test_creates_epoch_zero(self, db: Any, date_context: SystemContext) -> None:
        """Initialize creates epoch 0 with baseline text and baseline_seq=0."""
        result = await SessionContextEpoch.initialize(db, date_context, "s1")
        assert result is not None
        baseline_text, baseline_seq = result
        assert isinstance(baseline_text, str)
        assert "Today: 2026-07-28" in baseline_text
        assert baseline_seq == 0

        # Verify the epoch was persisted
        row = await db.fetchone(
            "SELECT epoch, baseline_seq, baseline FROM context_epochs WHERE session_id = ? ORDER BY epoch DESC LIMIT 1",
            ("s1",),
        )
        assert row is not None
        assert row["epoch"] == 0
        assert row["baseline_seq"] == 0
        assert "Today: 2026-07-28" in row["baseline"]

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_context(self, db: Any) -> None:
        """Empty SystemContext yields None (no context to render)."""
        empty_ctx = SystemContext()
        result = await SessionContextEpoch.initialize(db, empty_ctx, "s1")
        assert result is None

    @pytest.mark.asyncio
    async def test_stores_snapshot_for_reconcile(self, db: Any, date_context: SystemContext) -> None:
        """Snapshot column stores JSON that can be deserialized to SourceSnapshot."""
        await SessionContextEpoch.initialize(db, date_context, "s1")

        row = await db.fetchone(
            "SELECT snapshot FROM context_epochs WHERE session_id = ?",
            ("s1",),
        )
        assert row is not None
        raw = json.loads(row["snapshot"])
        assert "test/date" in raw
        entry = raw["test/date"]
        assert "value" in entry
        assert entry["value"] == "2026-07-28"
        assert "loaded_at" in entry

    @pytest.mark.asyncio
    async def test_increments_epoch_on_multiple_calls(self, db: Any, date_context: SystemContext) -> None:
        """Second initialize() call creates epoch 1."""
        await SessionContextEpoch.initialize(db, date_context, "s1")
        await SessionContextEpoch.initialize(db, date_context, "s1")

        row = await db.fetchone(
            "SELECT epoch FROM context_epochs WHERE session_id = ? ORDER BY epoch DESC LIMIT 1",
            ("s1",),
        )
        assert row is not None
        assert row["epoch"] == 1

    @pytest.mark.asyncio
    async def test_isolation_between_sessions(self, db: Any, date_context: SystemContext) -> None:
        """Different sessions get separate epochs."""
        await SessionContextEpoch.initialize(db, date_context, "s1")
        await SessionContextEpoch.initialize(db, date_context, "s2")

        rows = await db.fetchall(
            "SELECT session_id, epoch FROM context_epochs ORDER BY session_id, epoch",
        )
        assert len(rows) == 2


# ═══════════════════════════════════════════════════════════════════
# SessionContextEpoch.prepare()
# ═══════════════════════════════════════════════════════════════════

class TestPrepare:
    """SPEC §2.2.3: prepare(db, events, context, session_id) → tuple[str, int]"""

    @pytest.mark.asyncio
    async def test_auto_initializes_when_no_epoch_exists(
        self, db: Any, event_store: Any, date_context: SystemContext
    ) -> None:
        """If no epoch exists, prepare auto-initializes."""
        text, seq = await SessionContextEpoch.prepare(db, event_store, date_context, "s1")
        assert "Today: 2026-07-28" in text
        assert seq == 0

    @pytest.mark.asyncio
    async def test_returns_baseline_when_unchanged(
        self, db: Any, event_store: Any, date_context: SystemContext
    ) -> None:
        """When context hasn't changed, baseline text is returned."""
        await SessionContextEpoch.initialize(db, date_context, "s1")
        text, seq = await SessionContextEpoch.prepare(db, event_store, date_context, "s1")
        assert "Today: 2026-07-28" in text
        assert seq == 0

    @pytest.mark.asyncio
    async def test_returns_update_text_when_changed(
        self, db: Any, event_store: Any, mutable_context: tuple[SystemContext, list[str]]
    ) -> None:
        """When context changed, update text is returned."""
        ctx, values = mutable_context
        await SessionContextEpoch.initialize(db, ctx, "s1")

        # Mutate the value
        values[0] = "2026-07-28"

        text, seq = await SessionContextEpoch.prepare(db, event_store, ctx, "s1")
        assert "Date changed" in text
        assert "2026-01-01" in text
        assert "2026-07-28" in text
        assert seq == 0

    @pytest.mark.asyncio
    async def test_handles_replacement_blocked_gracefully(
        self, db: Any, event_store: Any
    ) -> None:
        """When context source fails, returns empty fallback."""
        async def failing_load() -> str:
            msg = "Source unavailable"
            raise RuntimeError(msg)

        source = ContextSource(
            key=ContextKey("test/failing"),
            load=failing_load,
            baseline=lambda v: f"Value: {v}",
            update=lambda old, new: "Changed",
        )
        ctx = make(source)

        # initialize should still work (source was available at init time)
        await SessionContextEpoch.initialize(db, ctx, "s1")

        # But prepare should fallback gracefully since reconcile fails
        text, seq = await SessionContextEpoch.prepare(db, event_store, ctx, "s1")
        assert isinstance(text, str)  # Falls back, no crash
        assert seq == 0

    @pytest.mark.asyncio
    async def test_preserves_baseline_seq_across_prepare_calls(
        self, db: Any, event_store: Any, date_context: SystemContext
    ) -> None:
        """Repeated prepare() calls return same baseline_seq."""
        await SessionContextEpoch.initialize(db, date_context, "s1")
        _, seq1 = await SessionContextEpoch.prepare(db, event_store, date_context, "s1")
        _, seq2 = await SessionContextEpoch.prepare(db, event_store, date_context, "s1")
        assert seq1 == seq2 == 0


# ═══════════════════════════════════════════════════════════════════
# SessionContextEpoch.compact()
# ═══════════════════════════════════════════════════════════════════

class TestCompact:
    """SPEC §2.2.3: compact(db, events, context, session_id) → None"""

    @pytest.mark.asyncio
    async def test_creates_new_epoch_in_db(
        self, db: Any, event_store: Any, date_context: SystemContext
    ) -> None:
        """Compact creates a new epoch row with incremented epoch index."""
        await event_store.append("s1", [
            {"type": "prompt.admitted", "data": {"content": "hello"}},
            {"type": "text.ended", "data": {"content": "hi"}},
        ])

        await SessionContextEpoch.compact(db, event_store, date_context, "s1")

        row = await db.fetchone(
            "SELECT epoch, baseline_seq, baseline FROM context_epochs WHERE session_id = ? ORDER BY epoch DESC LIMIT 1",
            ("s1",),
        )
        assert row is not None
        assert row["epoch"] >= 0
        assert row["baseline_seq"] > 0
        assert "Today: 2026-07-28" in row["baseline"]

    @pytest.mark.asyncio
    async def test_appends_compaction_event(
        self, db: Any, event_store: Any, date_context: SystemContext
    ) -> None:
        """Compact appends a 'compaction' event with baseline_seq."""
        await event_store.append("s1", [
            {"type": "prompt.admitted", "data": {"content": "hello"}},
            {"type": "text.ended", "data": {"content": "hi"}},
        ])

        await SessionContextEpoch.compact(db, event_store, date_context, "s1")

        events = await event_store.read("s1")
        compaction_events = [e for e in events if e.type == "compaction"]
        assert len(compaction_events) == 1
        assert "baseline_seq" in compaction_events[0].data

    @pytest.mark.asyncio
    async def test_empty_session_does_nothing(
        self, db: Any, event_store: Any, date_context: SystemContext
    ) -> None:
        """Compact on empty session does not create epochs or events."""
        await SessionContextEpoch.compact(db, event_store, date_context, "s1")

        events = await event_store.read("s1")
        compaction_events = [e for e in events if e.type == "compaction"]
        assert len(compaction_events) == 0

        row = await db.fetchone(
            "SELECT COUNT(*) as cnt FROM context_epochs WHERE session_id = ?",
            ("s1",),
        )
        assert row is not None
        assert row["cnt"] == 0

    @pytest.mark.asyncio
    async def test_increments_epoch_on_multiple_compactions(
        self, db: Any, event_store: Any, date_context: SystemContext
    ) -> None:
        """Two compactions produce epochs 0 and 1."""
        await event_store.append("s1", [
            {"type": "prompt.admitted", "data": {"content": "m1"}},
            {"type": "text.ended", "data": {"content": "r1"}},
        ])
        await SessionContextEpoch.compact(db, event_store, date_context, "s1")

        await event_store.append("s1", [
            {"type": "prompt.admitted", "data": {"content": "m2"}},
            {"type": "text.ended", "data": {"content": "r2"}},
        ])
        await SessionContextEpoch.compact(db, event_store, date_context, "s1")

        rows = await db.fetchall(
            "SELECT epoch FROM context_epochs WHERE session_id = ? ORDER BY epoch ASC",
            ("s1",),
        )
        epochs = [r["epoch"] for r in rows]
        assert epochs == [0, 1]

    @pytest.mark.asyncio
    async def test_compaction_event_has_message_count(
        self, db: Any, event_store: Any, date_context: SystemContext
    ) -> None:
        """Compaction event data includes message_count of compacted events."""
        await event_store.append("s1", [
            {"type": "prompt.admitted", "data": {"content": "q1"}},
            {"type": "text.ended", "data": {"content": "a1"}},
        ])

        await SessionContextEpoch.compact(db, event_store, date_context, "s1")

        events = await event_store.read("s1")
        ce = [e for e in events if e.type == "compaction"][0]
        assert "message_count" in ce.data
        assert ce.data["message_count"] >= 2
