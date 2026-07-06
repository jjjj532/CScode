"""TDD: CQRS Projection + BatchProjector.

Tests cover:
1. Projector.on_event — maintains messages projection table
2. Projector.get_messages — reads from projection table
3. BatchProjector.rebuild — rebuilds projection from events
4. API endpoint GET /api/sessions/{id}/messages
"""
from __future__ import annotations

import pytest
from cscode.schema.messages import MessageRole
from cscode.server.projector import BatchProjector, Projector
from cscode.storage.event_store import EventStore


@pytest.fixture
async def db(tmp_path):
    from cscode.storage.db import Database

    db = Database(db_path=tmp_path / "test_cqrs.db")
    await db.init()
    yield db
    await db.close()


@pytest.fixture
async def store(db):
    return EventStore(db)


@pytest.fixture
async def projector(db):
    return Projector(db)


# ── Projector.on_event ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_event_prompt_admitted_inserts_user_message(
    store: EventStore, projector: Projector
) -> None:
    """prompt.admitted should insert a USER message into projection."""
    events = await store.append("s1", [
        {"type": "prompt.admitted", "data": {"prompt": "hello"}},
    ])
    await projector.on_event(events[0])

    msgs = await projector.get_messages("s1")
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "hello"


@pytest.mark.asyncio
async def test_on_event_text_ended_inserts_assistant_message(
    store: EventStore, projector: Projector
) -> None:
    """text.ended should insert an ASSISTANT message."""
    events = await store.append("s1", [
        {"type": "text.ended", "data": {"content": "hello back"}},
    ])
    await projector.on_event(events[0])

    msgs = await projector.get_messages("s1")
    assert len(msgs) == 1
    assert msgs[0]["role"] == "assistant"
    assert msgs[0]["content"] == "hello back"


@pytest.mark.asyncio
async def test_on_event_tool_success_inserts_tool_message(
    store: EventStore, projector: Projector
) -> None:
    """tool.success should insert a TOOL message."""
    events = await store.append("s1", [
        {"type": "tool.success", "data": {"name": "Bash", "result": "done"}},
    ])
    await projector.on_event(events[0])

    msgs = await projector.get_messages("s1")
    assert len(msgs) == 1
    assert msgs[0]["role"] == "tool"
    assert msgs[0]["content"] == "done"
    assert msgs[0]["name"] == "Bash"


@pytest.mark.asyncio
async def test_on_event_tool_failed_inserts_tool_message(
    store: EventStore, projector: Projector
) -> None:
    """tool.failed should insert a TOOL message with error content."""
    events = await store.append("s1", [
        {"type": "tool.failed", "data": {"name": "Bash", "error": "timeout"}},
    ])
    await projector.on_event(events[0])

    msgs = await projector.get_messages("s1")
    assert len(msgs) == 1
    assert msgs[0]["role"] == "tool"
    assert "timeout" in msgs[0]["content"]


@pytest.mark.asyncio
async def test_on_event_ignores_text_delta(
    store: EventStore, projector: Projector
) -> None:
    """text.delta is transient — must NOT be persisted."""
    events = await store.append("s1", [
        {"type": "text.delta", "data": {"content": "partial"}},
    ])
    await projector.on_event(events[0])
    msgs = await projector.get_messages("s1")
    assert len(msgs) == 0


@pytest.mark.asyncio
async def test_on_event_ignores_step_events(
    store: EventStore, projector: Projector
) -> None:
    """step.started/step.ended are metadata — must NOT be persisted."""
    events = await store.append("s1", [
        {"type": "step.started", "data": {"round": 1}},
    ])
    await projector.on_event(events[0])
    events2 = await store.append("s1", [
        {"type": "step.ended", "data": {"round": 1}},
    ])
    await projector.on_event(events2[0])
    msgs = await projector.get_messages("s1")
    assert len(msgs) == 0


@pytest.mark.asyncio
async def test_on_event_multiple_events_preserves_order(
    store: EventStore, projector: Projector
) -> None:
    """Multiple events should be inserted in event_seq order."""
    await store.append("s1", [
        {"type": "prompt.admitted", "data": {"prompt": "first"}},
        {"type": "text.ended", "data": {"content": "response1"}},
        {"type": "prompt.admitted", "data": {"prompt": "second"}},
        {"type": "text.ended", "data": {"content": "response2"}},
    ])
    events = await store.read("s1")
    for evt in events:
        await projector.on_event(evt)

    msgs = await projector.get_messages("s1")
    assert len(msgs) == 4
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in msgs] == ["first", "response1", "second", "response2"]


# ── Projector.get_messages ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_messages_empty_for_new_session(
    projector: Projector,
) -> None:
    """Sessions with no events should return empty list."""
    msgs = await projector.get_messages("nonexistent")
    assert msgs == []


@pytest.mark.asyncio
async def test_get_messages_only_for_requested_session(
    store: EventStore, projector: Projector
) -> None:
    """Messages from different sessions must not leak."""
    for sid in ("s1", "s2"):
        events = await store.append(sid, [
            {"type": "prompt.admitted", "data": {"prompt": f"msg for {sid}"}},
            {"type": "text.ended", "data": {"content": f"reply for {sid}"}},
        ])
        for evt in events:
            await projector.on_event(evt)

    msgs_s1 = await projector.get_messages("s1")
    assert len(msgs_s1) == 2
    assert all(m["content"].endswith("for s1") for m in msgs_s1)

    msgs_s2 = await projector.get_messages("s2")
    assert len(msgs_s2) == 2
    assert all(m["content"].endswith("for s2") for m in msgs_s2)


# ── BatchProjector.rebuild ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_rebuild_reprojects_all_events(
    store: EventStore, projector: Projector
) -> None:
    """rebuild should clear and reproject all events."""
    await store.append("s1", [
        {"type": "prompt.admitted", "data": {"prompt": "hello"}},
        {"type": "text.ended", "data": {"content": "world"}},
    ])
    # Manually insert a stale message to simulate corruption
    db = projector._db
    await db.conn.execute(
        "INSERT INTO messages (session_id, role, content, event_seq, created_at) VALUES (?, ?, ?, ?, ?)",
        ("s1", "user", "STALE", 99, 0.0),
    )
    await db.conn.commit()

    batch = BatchProjector(db, store)
    await batch.rebuild("s1")

    msgs = await projector.get_messages("s1")
    assert len(msgs) == 2
    assert msgs[0]["content"] == "hello"
    assert msgs[1]["content"] == "world"


@pytest.mark.asyncio
async def test_rebuild_empty_session(
    store: EventStore, projector: Projector
) -> None:
    """rebuild on empty session should produce empty projection."""
    batch = BatchProjector(projector._db, store)
    await batch.rebuild("empty")
    msgs = await projector.get_messages("empty")
    assert msgs == []


@pytest.mark.asyncio
async def test_rebuild_all_sessions(
    store: EventStore, projector: Projector
) -> None:
    """rebuild_all should rebuild every session's projection."""
    for sid in ("s1", "s2", "s3"):
        await store.append(sid, [
            {"type": "prompt.admitted", "data": {"prompt": f"msg_{sid}"}},
            {"type": "text.ended", "data": {"content": f"reply_{sid}"}},
        ])

    batch = BatchProjector(projector._db, store)
    await batch.rebuild_all()

    for sid in ("s1", "s2", "s3"):
        msgs = await projector.get_messages(sid)
        assert len(msgs) == 2, f"Failed for {sid}"
        assert msgs[0]["content"] == f"msg_{sid}"


# ── API endpoint ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_projection_end_to_end(
    db, store: EventStore, projector: Projector
) -> None:
    """Events appended via EventStore → on_event → projection table contains the data."""
    events = await store.append("session-e2e", [
        {"type": "prompt.admitted", "data": {"prompt": "hello"}},
        {"type": "text.ended", "data": {"content": "world"}},
    ])
    for evt in events:
        await projector.on_event(evt)

    msgs = await projector.get_messages("session-e2e")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "hello"
    assert msgs[1]["role"] == "assistant"
