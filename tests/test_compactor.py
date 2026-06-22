from __future__ import annotations

import pytest

from cscode.core.messages import MessageRole
from cscode.server.compactor import Compactor
from cscode.server.projector import Projector
from cscode.storage.event_store import EventStore


@pytest.fixture
async def db(tmp_path):
    from cscode.storage.db import Database
    db = Database(db_path=tmp_path / "test.db")
    await db.init()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_compact_creates_epoch_and_event(db):
    """Compaction creates a context_epochs row + compaction event in EventStore."""
    store = EventStore(db)
    projector = Projector(db)
    compactor = Compactor(db, store, projector)
    sid = "s1"

    await store.append(sid, [
        {"type": "prompt.admitted", "data": {"content": "hello"}},
        {"type": "text.ended", "data": {"content": "hi"}},
    ])

    baseline_seq = await compactor.compact(sid, system_prompt="sys")

    events = await store.read(sid)
    compaction_events = [e for e in events if e.type == "compaction"]
    assert len(compaction_events) == 1
    ce = compaction_events[0]
    assert ce.data["baseline_seq"] == baseline_seq

    epoch = await projector._get_latest_epoch(sid)
    assert epoch is not None
    assert epoch["baseline_seq"] == baseline_seq
    assert epoch["epoch"] == 1


@pytest.mark.asyncio
async def test_build_context_uses_epoch(db):
    """After compaction, build_context uses snapshot + events after baseline."""
    store = EventStore(db)
    projector = Projector(db)
    compactor = Compactor(db, store, projector)
    sid = "s1"

    await store.append(sid, [
        {"type": "prompt.admitted", "data": {"content": "hello"}},
        {"type": "text.ended", "data": {"content": "hi there"}},
    ])

    await compactor.compact(sid, system_prompt="sys")

    await store.append(sid, [
        {"type": "prompt.admitted", "data": {"content": "followup"}},
        {"type": "text.ended", "data": {"content": "sure thing"}},
    ])

    msgs = await projector.build_context(sid, store, system_prompt="sys")
    assert len(msgs) == 3
    assert msgs[0].role == MessageRole.SYSTEM
    assert "compact" in msgs[0].content.lower()
    assert msgs[1].role == MessageRole.USER
    assert msgs[1].content == "followup"
    assert msgs[2].role == MessageRole.ASSISTANT
    assert msgs[2].content == "sure thing"


@pytest.mark.asyncio
async def test_build_context_no_epoch(db):
    """No epoch = original behavior unchanged."""
    store = EventStore(db)
    projector = Projector(db)
    sid = "s1"

    await store.append(sid, [
        {"type": "prompt.admitted", "data": {"content": "hello"}},
        {"type": "text.ended", "data": {"content": "hi"}},
    ])

    msgs = await projector.build_context(sid, store, system_prompt="sys")
    assert len(msgs) == 3
    assert msgs[0].role == MessageRole.SYSTEM
    assert msgs[0].content == "sys"
    assert msgs[1].role == MessageRole.USER
    assert msgs[2].role == MessageRole.ASSISTANT


@pytest.mark.asyncio
async def test_multiple_compactions(db):
    """Second compaction creates epoch 2, build_context uses latest."""
    store = EventStore(db)
    projector = Projector(db)
    compactor = Compactor(db, store, projector)
    sid = "s1"

    await store.append(sid, [
        {"type": "prompt.admitted", "data": {"content": "msg1"}},
        {"type": "text.ended", "data": {"content": "reply1"}},
    ])
    await compactor.compact(sid, system_prompt="sys")
    epoch1 = await projector._get_latest_epoch(sid)

    await store.append(sid, [
        {"type": "prompt.admitted", "data": {"content": "msg2"}},
        {"type": "text.ended", "data": {"content": "reply2"}},
    ])
    await compactor.compact(sid, system_prompt="sys")
    epoch2 = await projector._get_latest_epoch(sid)

    assert epoch1 is not None
    assert epoch2 is not None
    assert epoch2["epoch"] == 2
    assert epoch2["baseline_seq"] > epoch1["baseline_seq"]

    await store.append(sid, [
        {"type": "prompt.admitted", "data": {"content": "msg3"}},
        {"type": "text.ended", "data": {"content": "reply3"}},
    ])

    msgs = await projector.build_context(sid, store, system_prompt="sys")
    assert len(msgs) == 3
    assert msgs[0].role == MessageRole.SYSTEM
    assert msgs[1].content == "msg3"
    assert msgs[2].content == "reply3"


@pytest.mark.asyncio
async def test_compact_empty_session(db):
    """Compacting a session with no events creates nothing."""
    store = EventStore(db)
    projector = Projector(db)
    compactor = Compactor(db, store, projector)
    sid = "s1"

    baseline_seq = await compactor.compact(sid)
    assert baseline_seq == 0

    epoch = await projector._get_latest_epoch(sid)
    assert epoch is None
