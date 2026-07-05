"""Tests for P2-8: Session List — enhanced session listing with pagination.

Tests cover:
1. GET /api/sessions returns all sessions with enhanced metadata
2. GET /api/sessions?limit=N limits results
3. Deleted sessions are still listed with status
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx._transports.asgi import ASGITransport

from cscode.core.session import SessionV2
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
async def db(tmp_path):
    _db = Database(db_path=tmp_path / "session_list.db")
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

    @router.get("/api/sessions")
    async def list_sessions(limit: int = 50, offset: int = 0):
        from cscode.storage.db import Database as DB

        # Get all aggregate IDs
        cursor = await event_store._db.conn.execute(
            "SELECT aggregate_id FROM event_sequences ORDER BY aggregate_id LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()

        sessions = []
        for row in rows:
            aggregate_id = row["aggregate_id"]
            sess = await SessionV2.load(event_store, aggregate_id)
            st = sess.state
            sessions.append({
                "id": str(st.session_id),
                "title": st.title,
                "provider": st.provider,
                "model": st.model,
                "status": st.status,
                "message_count": len(st.messages),
                "event_count": st.seq,
                "created_at": st.created_at,
                "updated_at": st.updated_at,
            })
        return sessions

    _app.include_router(router)
    return _app


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════


class TestSessionList:
    async def test_list_empty(self, app: FastAPI) -> None:
        """GET /api/sessions returns empty list when no sessions exist."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_sessions(self, app: FastAPI, event_store: EventStore) -> None:
        """GET /api/sessions returns all sessions."""
        s1 = await SessionV2.create(event_store, "gpt-4o", title="Session 1")
        await s1.prompt("Hello")
        await s1.add_text("Hi!")
        await SessionV2.create(event_store, "gpt-4o", title="Session 2")

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        titles = {s["title"] for s in data}
        assert titles == {"Session 1", "Session 2"}

    async def test_list_includes_message_count(
        self, app: FastAPI, event_store: EventStore
    ) -> None:
        """Response includes message_count."""
        sess = await SessionV2.create(event_store, "gpt-4o", title="Test")
        await sess.prompt("Hello")
        await sess.add_text("Hi!")
        await sess.prompt("Q2")
        await sess.add_text("A2")

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sessions")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["message_count"] == 4
        assert data[0]["event_count"] >= 5

    async def test_list_deleted_session(
        self, app: FastAPI, event_store: EventStore
    ) -> None:
        """Deleted sessions appear with status=deleted."""
        sess = await SessionV2.create(event_store, "gpt-4o", title="Will delete")
        await sess.delete()

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sessions")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "deleted"

    async def test_list_limit(self, app: FastAPI, event_store: EventStore) -> None:
        """GET /api/sessions?limit=1 returns only 1 session."""
        for i in range(3):
            await SessionV2.create(event_store, "gpt-4o", title=f"S{i}")

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sessions", params={"limit": 1})
        data = resp.json()
        assert len(data) == 1

    async def test_list_offset(self, app: FastAPI, event_store: EventStore) -> None:
        """GET /api/sessions?offset=1 skips first session."""
        s1 = await SessionV2.create(event_store, "gpt-4o", title="First")
        await SessionV2.create(event_store, "gpt-4o", title="Second")
        await SessionV2.create(event_store, "gpt-4o", title="Third")

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sessions", params={"offset": 1})
        data = resp.json()
        # Should return 2 sessions, none named "First"
        titles = {s["title"] for s in data}
        assert "First" not in titles
        assert len(data) == 2
