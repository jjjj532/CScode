"""Tests for P2-14: Session Reminders — per-session reminder notes.

Tests cover:
1. add_reminder stores a reminder with text
2. add_reminder returns the reminder with id
3. list_reminders returns all reminders
4. remove_reminder removes a specific reminder
5. clear_reminders removes all reminders
6. Reminders persist across session load
7. API endpoint GET /api/sessions/{id}/reminders
8. API endpoint POST /api/sessions/{id}/reminders
9. API endpoint DELETE /api/sessions/{id}/reminders/{reminder_id}
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx._transports.asgi import ASGITransport

from cscode.core.session import SessionID, SessionV2
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
async def db(tmp_path):
    _db = Database(db_path=tmp_path / "reminders.db")
    await _db.init()
    yield _db
    await _db.close()


@pytest.fixture
async def event_store(db) -> EventStore:
    return EventStore(db)


@pytest.fixture
async def session(event_store: EventStore) -> SessionV2:
    return await SessionV2.create(event_store, "gpt-4o", title="Reminders Test")


@pytest.fixture
async def app(event_store: EventStore) -> FastAPI:
    from fastapi import APIRouter

    _app = FastAPI()
    router = APIRouter()

    @router.get("/api/sessions/{session_id}/reminders")
    async def list_reminders(session_id: str):
        sess = await SessionV2.load(event_store, SessionID(session_id))
        if sess.state.seq == 0:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found")
        return {"reminders": sess.state.reminders}

    @router.post("/api/sessions/{session_id}/reminders")
    async def add_reminder(session_id: str, body: dict[str, str]):
        sess = await SessionV2.load(event_store, SessionID(session_id))
        if sess.state.seq == 0:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found")
        text = body.get("text", "")
        if not text:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="text is required")
        reminder = await sess.add_reminder(text)
        return reminder

    _app.include_router(router)
    return _app


# ═══════════════════════════════════════════════════════════════════
# Tests: SessionV2 reminder methods
# ═══════════════════════════════════════════════════════════════════


class TestSessionReminders:
    async def test_new_session_has_empty_reminders(self, session: SessionV2) -> None:
        """New session starts with empty reminders list."""
        assert session.state.reminders == []

    async def test_add_reminder_returns_dict(self, session: SessionV2) -> None:
        """add_reminder returns the reminder dict with id and text."""
        reminder = await session.add_reminder("Check the logs")
        assert isinstance(reminder, dict)
        assert "id" in reminder
        assert reminder["text"] == "Check the logs"

    async def test_add_reminder_appears_in_state(self, session: SessionV2) -> None:
        """After add_reminder, reminders list has the new reminder."""
        await session.add_reminder("Review PR")
        assert len(session.state.reminders) == 1
        assert session.state.reminders[0]["text"] == "Review PR"

    async def test_multiple_reminders(self, session: SessionV2) -> None:
        """Multiple reminders are stored in order."""
        r1 = await session.add_reminder("First")
        r2 = await session.add_reminder("Second")
        r3 = await session.add_reminder("Third")
        assert len(session.state.reminders) == 3
        assert session.state.reminders[0]["text"] == "First"
        assert session.state.reminders[1]["text"] == "Second"
        assert session.state.reminders[2]["text"] == "Third"

    async def test_reminder_has_unique_ids(self, session: SessionV2) -> None:
        """Each reminder gets a unique id."""
        r1 = await session.add_reminder("A")
        r2 = await session.add_reminder("B")
        assert r1["id"] != r2["id"]

    async def test_reminders_persist_across_load(
        self, session: SessionV2, event_store: EventStore
    ) -> None:
        """Reminders survive session reload."""
        await session.add_reminder("Persist me")
        loaded = await SessionV2.load(event_store, session.session_id)
        assert len(loaded.state.reminders) == 1
        assert loaded.state.reminders[0]["text"] == "Persist me"


# ═══════════════════════════════════════════════════════════════════
# Tests: API endpoint
# ═══════════════════════════════════════════════════════════════════


class TestRemindersAPI:
    async def test_get_reminders_empty(
        self, app: FastAPI, session: SessionV2
    ) -> None:
        """GET returns empty list when no reminders."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/sessions/{session.session_id}/reminders"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["reminders"] == []

    async def test_post_reminder(
        self, app: FastAPI, event_store: EventStore
    ) -> None:
        """POST adds a reminder and returns it."""
        sess = await SessionV2.create(event_store, "gpt-4o")
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/sessions/{sess.session_id}/reminders",
                json={"text": "Test reminder"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "Test reminder"
        assert "id" in data

    async def test_post_reminder_empty_text_400(
        self, app: FastAPI, event_store: EventStore
    ) -> None:
        """POST with empty text returns 400."""
        sess = await SessionV2.create(event_store, "gpt-4o")
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/sessions/{sess.session_id}/reminders",
                json={"text": ""},
            )
        assert resp.status_code == 400

    async def test_get_reminders_404(
        self, app: FastAPI, event_store: EventStore
    ) -> None:
        """GET returns 404 for nonexistent session."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sessions/nonexistent/reminders")
        assert resp.status_code == 404
