"""Tests for P2-6: Session Instruction — per-session custom instructions.

Tests cover:
1. SessionProjector — instruction.set / instruction.deleted event handling
2. SessionV2.set_instruction() / delete_instruction()
3. build_context() instruction injection
4. API endpoints: GET/PUT/DELETE /api/sessions/{id}/instruction
"""

from __future__ import annotations

import time

import httpx
import pytest
from fastapi import FastAPI
from httpx._transports.asgi import ASGITransport

from cscode.core.session import SessionProjector, SessionV2
from cscode.schema.ids import SessionID
from cscode.schema.messages import MessageRole
from cscode.storage.db import Database
from cscode.storage.event_store import Event, EventStore




# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
async def db(tmp_path):
    _db = Database(db_path=tmp_path / "instruction_test.db")
    await _db.init()
    yield _db
    await _db.close()


@pytest.fixture
async def event_store(db) -> EventStore:
    return EventStore(db)


@pytest.fixture
async def session(event_store: EventStore) -> SessionV2:
    return await SessionV2.create(event_store, "gpt-4o")


# ═══════════════════════════════════════════════════════════════════
# SessionProjector — instruction event handling
# ═══════════════════════════════════════════════════════════════════


class TestProjectorInstruction:
    def test_instruction_set(self) -> None:
        """instruction.set updates state.instruction."""
        events = [
            Event("sess_1", 1, "session.created",
                  {"title": "T", "provider": "openai", "model": "gpt-4o", "agent": "auto"}, 100),
            Event("sess_1", 2, "instruction.set",
                  {"instruction": "Always use Japanese."}, 101),
        ]
        state = SessionProjector.project(events)
        assert state.instruction == "Always use Japanese."

    def test_instruction_update(self) -> None:
        """Multiple instruction.set updates replace previous."""
        events = [
            Event("sess_1", 1, "session.created",
                  {"title": "T", "provider": "openai", "model": "gpt-4o", "agent": "auto"}, 100),
            Event("sess_1", 2, "instruction.set",
                  {"instruction": "v1"}, 101),
            Event("sess_1", 3, "instruction.set",
                  {"instruction": "v2"}, 102),
        ]
        state = SessionProjector.project(events)
        assert state.instruction == "v2"

    def test_instruction_deleted(self) -> None:
        """instruction.deleted clears state.instruction."""
        events = [
            Event("sess_1", 1, "session.created",
                  {"title": "T", "provider": "openai", "model": "gpt-4o", "agent": "auto"}, 100),
            Event("sess_1", 2, "instruction.set",
                  {"instruction": "Some instruction"}, 101),
            Event("sess_1", 3, "instruction.deleted",
                  {}, 102),
        ]
        state = SessionProjector.project(events)
        assert state.instruction == ""

    def test_instruction_default_empty(self) -> None:
        """Session without instruction events has empty instruction."""
        events = [
            Event("sess_1", 1, "session.created",
                  {"title": "T", "provider": "openai", "model": "gpt-4o", "agent": "auto"}, 100),
        ]
        state = SessionProjector.project(events)
        assert state.instruction == ""


# ═══════════════════════════════════════════════════════════════════
# SessionV2 — set_instruction / delete_instruction
# ═══════════════════════════════════════════════════════════════════


class TestSessionV2Instruction:
    pytestmark = pytest.mark.asyncio

    async def test_set_instruction(self, session: SessionV2) -> None:
        """set_instruction appends event and updates state."""
        await session.set_instruction("Always use Chinese.")
        assert session.state.instruction == "Always use Chinese."

    async def test_set_instruction_persists(self, event_store: EventStore, session: SessionV2) -> None:
        """set_instruction persists across session load."""
        await session.set_instruction("Persistent instruction")
        loaded = await SessionV2.load(event_store, session.session_id)
        assert loaded.state.instruction == "Persistent instruction"

    async def test_set_instruction_updates(self, session: SessionV2) -> None:
        """set_instruction overwrites previous instruction."""
        await session.set_instruction("v1")
        await session.set_instruction("v2")
        assert session.state.instruction == "v2"

    async def test_delete_instruction(self, session: SessionV2) -> None:
        """delete_instruction clears instruction."""
        await session.set_instruction("Temporary")
        await session.delete_instruction()
        assert session.state.instruction == ""

    async def test_delete_instruction_persists(self, event_store: EventStore, session: SessionV2) -> None:
        """delete_instruction persists across session load."""
        await session.set_instruction("Will be deleted")
        await session.delete_instruction()
        loaded = await SessionV2.load(event_store, session.session_id)
        assert loaded.state.instruction == ""

    async def test_delete_instruction_noop_when_empty(self, session: SessionV2) -> None:
        """delete_instruction on empty session does not error."""
        await session.delete_instruction()
        assert session.state.instruction == ""

    async def test_instruction_separate_per_session(self, event_store: EventStore) -> None:
        """Each session has its own instruction."""
        s1 = await SessionV2.create(event_store, "gpt-4o")
        s2 = await SessionV2.create(event_store, "gpt-4o")
        await s1.set_instruction("Instruction for s1")
        assert s1.state.instruction == "Instruction for s1"
        assert s2.state.instruction == ""


# ═══════════════════════════════════════════════════════════════════
# build_context — instruction injection
# ═══════════════════════════════════════════════════════════════════


class TestBuildContextInstruction:
    pytestmark = pytest.mark.asyncio
    async def test_instruction_injected_as_system_message(
        self, session: SessionV2
    ) -> None:
        """build_context includes instruction as first system message."""
        await session.set_instruction("Speak in Chinese.")
        context = SessionProjector.build_context(session.state)
        assert len(context) >= 1
        assert context[0].role == MessageRole.SYSTEM
        assert "Speak in Chinese." in str(context[0].parts[0].text)

    async def test_instruction_before_session_messages(
        self, session: SessionV2
    ) -> None:
        """Instruction system message appears before conversation messages."""
        await session.set_instruction("Be concise.")
        await session.prompt("Hello")
        context = SessionProjector.build_context(session.state)
        assert context[0].role == MessageRole.SYSTEM
        assert context[1].role != MessageRole.SYSTEM

    async def test_no_instruction_no_system_message(
        self, session: SessionV2
    ) -> None:
        """build_context without instruction does not inject system message."""
        await session.prompt("Hello")
        context = SessionProjector.build_context(session.state)
        assert not any(m.role == MessageRole.SYSTEM for m in context)


# ═══════════════════════════════════════════════════════════════════
# API endpoints
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def instruction_app(api_app: FastAPI) -> FastAPI:
    """Register instruction endpoints on test app."""
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/api/sessions/{session_id}/instruction")
    async def get_instruction(session_id: str):
        from cscode.storage.event_store import EventStore as ES
        es: ES = api_app.state.event_store
        sess = await SessionV2.load(es, SessionID(session_id))
        return {"instruction": sess.state.instruction}

    @router.put("/api/sessions/{session_id}/instruction")
    async def set_instruction(session_id: str, body: dict):
        from cscode.storage.event_store import EventStore as ES
        es: ES = api_app.state.event_store
        sess = await SessionV2.load(es, SessionID(session_id))
        await sess.set_instruction(body["instruction"])
        return {"instruction": sess.state.instruction}

    @router.delete("/api/sessions/{session_id}/instruction")
    async def delete_instruction(session_id: str):
        from cscode.storage.event_store import EventStore as ES
        es: ES = api_app.state.event_store
        sess = await SessionV2.load(es, SessionID(session_id))
        await sess.delete_instruction()
        return {"deleted": True}

    api_app.include_router(router)
    return api_app


class TestInstructionAPI:
    pytestmark = pytest.mark.asyncio
    @pytest.fixture
    async def api_db(self, tmp_path):
        from cscode.storage.db import Database as DB
        _db = DB(db_path=tmp_path / "api_instruction.db")
        await _db.init()
        yield _db
        await _db.close()

    @pytest.fixture
    async def api_app(self, api_db) -> FastAPI:
        app = FastAPI()
        app.state.event_store = EventStore(api_db)
        return app

    async def test_get_instruction_empty(
        self, instruction_app: FastAPI
    ) -> None:
        """GET returns empty string when no instruction set."""
        es: EventStore = instruction_app.state.event_store
        sess = await SessionV2.create(es, "gpt-4o")
        transport = ASGITransport(app=instruction_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/sessions/{sess.session_id}/instruction")
        assert resp.status_code == 200
        data = resp.json()
        assert data["instruction"] == ""

    async def test_put_instruction(
        self, instruction_app: FastAPI
    ) -> None:
        """PUT sets instruction."""
        es: EventStore = instruction_app.state.event_store
        sess = await SessionV2.create(es, "gpt-4o")
        transport = ASGITransport(app=instruction_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                f"/api/sessions/{sess.session_id}/instruction",
                json={"instruction": "API instruction"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["instruction"] == "API instruction"

    async def test_delete_instruction(
        self, instruction_app: FastAPI
    ) -> None:
        """DELETE removes instruction."""
        es: EventStore = instruction_app.state.event_store
        sess = await SessionV2.create(es, "gpt-4o")
        await sess.set_instruction("To be deleted")
        transport = ASGITransport(app=instruction_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(f"/api/sessions/{sess.session_id}/instruction")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    async def test_get_instruction_after_set(
        self, instruction_app: FastAPI
    ) -> None:
        """GET returns instruction after PUT."""
        es: EventStore = instruction_app.state.event_store
        sess = await SessionV2.create(es, "gpt-4o")
        transport = ASGITransport(app=instruction_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.put(
                f"/api/sessions/{sess.session_id}/instruction",
                json={"instruction": "Persistent"},
            )
            resp = await client.get(f"/api/sessions/{sess.session_id}/instruction")
        assert resp.status_code == 200
        assert resp.json()["instruction"] == "Persistent"
