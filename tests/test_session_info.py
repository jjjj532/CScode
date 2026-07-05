"""Tests for P2-7: Session Info — session metadata endpoint.

Tests cover:
1. GET /api/sessions/{id}/info returns full metadata
2. GET with non-existent session returns 404
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx._transports.asgi import ASGITransport

from cscode.core.session import SessionV2
from cscode.schema.ids import SessionID
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
async def db(tmp_path):
    _db = Database(db_path=tmp_path / "session_info.db")
    await _db.init()
    yield _db
    await _db.close()


@pytest.fixture
async def event_store(db) -> EventStore:
    return EventStore(db)


@pytest.fixture
async def app(event_store: EventStore) -> FastAPI:
    from fastapi import APIRouter

    _app = FastAPI()
    router = APIRouter()

    @router.get("/api/sessions/{session_id}/info")
    async def get_session_info(session_id: str):
        from fastapi import HTTPException

        sess = await SessionV2.load(event_store, SessionID(session_id))
        if sess.state.seq == 0:
            raise HTTPException(status_code=404, detail="Session not found")

        st = sess.state
        return {
            "session_id": str(st.session_id),
            "title": st.title,
            "model": st.model,
            "provider": st.provider,
            "agent": st.agent,
            "status": st.status,
            "workspace_id": st.workspace_id,
            "message_count": len(st.messages),
            "event_count": st.seq,
            "tool_rounds": st.tool_rounds,
            "created_at": st.created_at,
            "updated_at": st.updated_at,
            "seq": st.seq,
        }

    _app.include_router(router)
    return _app


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════


class TestSessionInfo:
    async def test_get_info(self, app: FastAPI, event_store: EventStore) -> None:
        """GET /api/sessions/{id}/info returns full metadata."""
        sess = await SessionV2.create(event_store, "gpt-4o", title="Test Chat", provider="openai")
        await sess.set_instruction("Custom instruction")
        await sess.prompt("Hello")
        await sess.add_text("Hi!")

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/sessions/{sess.session_id}/info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["session_id"] == str(sess.session_id)
        assert data["title"] == "Test Chat"
        assert data["model"] == "gpt-4o"
        assert data["provider"] == "openai"
        assert data["status"] == "active"
        assert data["message_count"] == 2
        assert data["event_count"] >= 4
        assert isinstance(data["created_at"], float)
        assert isinstance(data["updated_at"], float)
        assert data["seq"] >= 4

    async def test_get_info_no_messages(self, app: FastAPI, event_store: EventStore) -> None:
        """Session with no messages returns message_count=0."""
        sess = await SessionV2.create(event_store, "gpt-4o")

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/sessions/{sess.session_id}/info")
        assert resp.status_code == 200
        assert resp.json()["message_count"] == 0

    async def test_get_info_nonexistent(self, app: FastAPI) -> None:
        """Non-existent session returns 404."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sessions/nonexistent/info")
        assert resp.status_code == 404

    async def test_get_info_deleted_session(self, app: FastAPI, event_store: EventStore) -> None:
        """Deleted session returns status=deleted."""
        sess = await SessionV2.create(event_store, "gpt-4o")
        await sess.delete()

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/sessions/{sess.session_id}/info")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
