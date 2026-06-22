from __future__ import annotations
import pytest
from cscode.core.messages import MessageRole
from cscode.storage.event_store import EventStore
from cscode.server.projector import Projector


@pytest.fixture
async def db(tmp_path):
    from cscode.storage.db import Database
    db = Database(db_path=tmp_path / "test.db")
    await db.init()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_build_context_empty(db):
    """No events = context with only system prompt."""
    projector = Projector(db)
    store = EventStore(db)
    msgs = await projector.build_context("s1", store, system_prompt="You are a bot")
    assert len(msgs) == 1
    assert msgs[0].role == MessageRole.SYSTEM
    assert msgs[0].content == "You are a bot"


@pytest.mark.asyncio
async def test_build_context_with_events(db):
    projector = Projector(db)
    store = EventStore(db)
    sid = "s1"
    await store.append(sid, [
        {"type": "prompt.admitted", "data": {"content": "hello"}},
        {"type": "text.ended", "data": {"content": "hi there"}},
        {"type": "tool.called", "data": {"name": "Bash"}},
        {"type": "tool.success", "data": {"name": "Bash", "result": "done"}},
        {"type": "text.ended", "data": {"content": "finished"}},
    ])
    msgs = await projector.build_context(sid, store, system_prompt="sys")
    assert len(msgs) == 5
    assert msgs[0].role == MessageRole.SYSTEM
    assert msgs[1].role == MessageRole.USER
    assert msgs[2].role == MessageRole.ASSISTANT
    assert msgs[3].role == MessageRole.TOOL
    assert msgs[4].role == MessageRole.ASSISTANT


@pytest.mark.asyncio
async def test_build_context_no_system(db):
    projector = Projector(db)
    store = EventStore(db)
    msgs = await projector.build_context("s1", store)
    assert msgs == []


@pytest.mark.asyncio
async def test_build_context_skips_empty_prompt(db):
    projector = Projector(db)
    store = EventStore(db)
    await store.append("s1", [
        {"type": "prompt.admitted", "data": {}},  # empty content
    ])
    msgs = await projector.build_context("s1", store)
    assert msgs == []
