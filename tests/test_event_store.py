from __future__ import annotations

import asyncio
import logging
from unittest.mock import patch

import pytest

from cscode.storage.event_store import EventStore


@pytest.fixture
async def db(tmp_path):
    from cscode.storage.db import Database

    db = Database(db_path=tmp_path / "test.db")
    await db.init()
    # Manually create tables needed by EventStore (will be migrated in Task 2)
    await db.conn.execute("""
        CREATE TABLE IF NOT EXISTS event_sequences (
            aggregate_id TEXT PRIMARY KEY,
            seq INTEGER NOT NULL DEFAULT 0
        )
    """)
    await db.conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aggregate_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            type TEXT NOT NULL,
            data TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            UNIQUE(aggregate_id, seq)
        )
    """)
    await db.conn.execute("CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events(aggregate_id, seq)")
    await db.conn.commit()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_append_and_read(db):
    store = EventStore(db)
    sid = "s1"
    events = await store.append(sid, [{"type": "a"}, {"type": "b"}])
    assert [e.seq for e in events] == [1, 2]
    read = await store.read(sid)
    assert len(read) == 2
    read_after = await store.read(sid, after_seq=1)
    assert len(read_after) == 1
    assert read_after[0].type == "b"


@pytest.mark.asyncio
async def test_append_twice_continuity(db):
    store = EventStore(db)
    await store.append("s1", [{"type": "a"}])
    await store.append("s1", [{"type": "b"}, {"type": "c"}])
    events = await store.read("s1")
    assert [e.seq for e in events] == [1, 2, 3]


@pytest.mark.asyncio
async def test_subscribe_receives_events(db):
    store = EventStore(db)
    sid = "s1"

    collected = []
    async def subscriber():
        async for event in store.subscribe(sid):
            collected.append(event.type)
            if len(collected) == 2:
                break

    sub_task = asyncio.create_task(subscriber())
    await asyncio.sleep(0.05)

    await store.append(sid, [{"type": "a"}, {"type": "b"}])

    await asyncio.wait_for(sub_task, timeout=3.0)
    assert collected == ["a", "b"]


@pytest.mark.asyncio
async def test_concurrent_append_same_aggregate(db):
    store = EventStore(db)
    sid = "s1"

    async def append_batch(start: int):
        return await store.append(sid, [{"type": f"e{i}"} for i in range(start, start + 5)])

    r1 = asyncio.create_task(append_batch(0))
    r2 = asyncio.create_task(append_batch(5))
    results = await asyncio.gather(r1, r2)

    all_seqs = [e.seq for batch in results for e in batch]
    assert sorted(all_seqs) == list(range(1, 11))


@pytest.mark.asyncio
async def test_append_logs_timing(db, caplog: pytest.LogCaptureFixture) -> None:
    """EventStore.append should log duration_ms at INFO level."""
    caplog.set_level(logging.INFO)
    store = EventStore(db)
    await store.append("s1", [{"type": "a"}, {"type": "b"}])
    assert any(
        "duration_ms" in msg and "event_store.append" in msg
        for msg in caplog.messages
    ), "append should log duration_ms"


@pytest.mark.asyncio
async def test_read_logs_timing(db, caplog: pytest.LogCaptureFixture) -> None:
    """EventStore.read should log duration_ms at INFO level."""
    caplog.set_level(logging.INFO)
    store = EventStore(db)
    await store.append("s1", [{"type": "a"}])
    caplog.clear()
    await store.read("s1")
    assert any(
        "duration_ms" in msg and "event_store.read" in msg
        for msg in caplog.messages
    ), "read should log duration_ms"


# ─── scan_events_by_type ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_by_type_single(db) -> None:
    """scan_events_by_type with one type returns only matching events."""
    store = EventStore(db)
    await store.append("agg1", [{"type": "user.created"}])
    await store.append("agg2", [{"type": "order.placed"}, {"type": "payment.received"}])
    await store.append("agg1", [{"type": "user.updated"}])

    results = await store.scan_events_by_type("user.created")
    assert len(results) == 1
    assert results[0].type == "user.created"
    assert results[0].aggregate_id == "agg1"
    assert results[0].seq == 1


@pytest.mark.asyncio
async def test_scan_by_type_multiple(db) -> None:
    """scan_events_by_type with multiple types returns all matching events."""
    store = EventStore(db)
    await store.append("agg1", [{"type": "a"}, {"type": "b"}, {"type": "c"}])
    await store.append("agg2", [{"type": "b"}, {"type": "d"}])

    results = await store.scan_events_by_type("a", "b")
    types = [e.type for e in results]
    assert types == ["a", "b", "b"]
    assert len(results) == 3


@pytest.mark.asyncio
async def test_scan_by_type_no_match(db) -> None:
    """scan_events_by_type returns empty list when no events match."""
    store = EventStore(db)
    await store.append("agg1", [{"type": "user.created"}])

    results = await store.scan_events_by_type("nonexistent.type")
    assert results == []


@pytest.mark.asyncio
async def test_scan_by_type_ordering(db) -> None:
    """scan_events_by_type orders results by aggregate_id then seq."""
    store = EventStore(db)
    await store.append("z_agg", [{"type": "evt"}, {"type": "evt"}])
    await store.append("a_agg", [{"type": "evt"}])

    results = await store.scan_events_by_type("evt")
    # a_agg (seq=1), z_agg (seq=1), z_agg (seq=2)
    assert results[0].aggregate_id == "a_agg"
    assert results[0].seq == 1
    assert results[1].aggregate_id == "z_agg"
    assert results[1].seq == 1
    assert results[2].aggregate_id == "z_agg"
    assert results[2].seq == 2


@pytest.mark.asyncio
async def test_scan_by_type_with_data(db) -> None:
    """scan_events_by_type deserializes data payload correctly."""
    store = EventStore(db)
    await store.append("agg1", [{"type": "evt", "data": {"key": "value", "count": 42}}])

    results = await store.scan_events_by_type("evt")
    assert len(results) == 1
    assert results[0].data == {"key": "value", "count": 42}


@pytest.mark.asyncio
async def test_scan_by_type_empty_store(db) -> None:
    """scan_events_by_type on empty store returns empty list."""
    store = EventStore(db)
    results = await store.scan_events_by_type("anything")
    assert results == []


@pytest.mark.asyncio
async def test_append_rollback_on_error(db) -> None:
    """_append_impl failure triggers rollback handler, re-raises, store still usable."""
    store = EventStore(db)

    orig = db.conn.execute
    call_count: list[int] = [0]

    async def failing_execute(sql: str, parameters: object = None) -> object:
        call_count[0] += 1
        if call_count[0] >= 4:  # Fail during INSERT INTO events
            raise RuntimeError("simulated db error")
        return await orig(sql, parameters)

    with patch.object(db.conn, "execute", failing_execute):
        with pytest.raises(RuntimeError, match="simulated db error"):
            await store.append("agg1", [{"type": "a"}])

    # After rollback, store should still work for subsequent operations
    events = await store.append("agg1", [{"type": "b"}])
    assert len(events) == 1
    assert events[0].type == "b"


@pytest.mark.asyncio
async def test_subscribe_poll_timeout(db) -> None:
    """subscribe's poll loop handles TimeoutError — polls then continues."""
    store = EventStore(db)
    sid = "s1"
    await store.append(sid, [{"type": "a"}])

    collected: list[str] = []
    # Subscribe reads initial events, then enters 5s poll loop.
    # We use asyncio.timeout(6) to bound the total test.
    with pytest.raises(asyncio.TimeoutError):
        async with asyncio.timeout(6):
            async for event in store.subscribe(sid):
                collected.append(event.type)

    # Before timeout: got the initial event, at least one poll cycle ran
    assert collected == ["a"]


@pytest.mark.asyncio
async def test_list_aggregate_ids(db) -> None:
    """list_aggregate_ids returns distinct aggregate IDs with events."""
    store = EventStore(db)
    # Empty store
    ids = await store.list_aggregate_ids()
    assert ids == []

    # Append events to multiple aggregates
    await store.append("agg1", [{"type": "a"}])
    await store.append("agg2", [{"type": "b"}, {"type": "c"}])
    await store.append("agg1", [{"type": "d"}])

    ids = await store.list_aggregate_ids()
    assert ids == ["agg1", "agg2"]
