from __future__ import annotations

import asyncio
import logging

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
