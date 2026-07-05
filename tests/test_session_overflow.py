"""Tests for P2-12: Session Overflow — message count threshold detection.

Tests cover:
1. check_overflow returns overflowing=false when under threshold
2. check_overflow returns overflowing=true when at/over threshold
3. check_overflow returns near_overflow=true when near threshold
4. Session with zero messages is not overflowing
5. API endpoint returns overflow status
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
    _db = Database(db_path=tmp_path / "overflow.db")
    await _db.init()
    yield _db
    await _db.close()


@pytest.fixture
async def event_store(db) -> EventStore:
    return EventStore(db)


@pytest.fixture
async def session(event_store: EventStore) -> SessionV2:
    return await SessionV2.create(event_store, "gpt-4o", title="Overflow Test")


@pytest.fixture
async def app(event_store: EventStore) -> FastAPI:
    from fastapi import APIRouter
    from cscode.core.session import SessionID

    _app = FastAPI()
    router = APIRouter()

    @router.get("/api/sessions/{session_id}/overflow")
    async def get_overflow(session_id: str):
        sess = await SessionV2.load(event_store, SessionID(session_id))
        if sess.state.seq == 0:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found")
        info = sess.check_overflow()
        return {
            "overflowing": info["overflowing"],
            "near_overflow": info["near_overflow"],
            "message_count": info["message_count"],
            "threshold": info["threshold"],
        }

    _app.include_router(router)
    return _app


# ═══════════════════════════════════════════════════════════════════
# Tests: SessionV2.check_overflow
# ═══════════════════════════════════════════════════════════════════


class TestCheckOverflow:
    async def test_new_session_not_overflowing(self, session: SessionV2) -> None:
        """New session with no messages is not overflowing."""
        info = session.check_overflow()
        assert not info["overflowing"]
        assert not info["near_overflow"]
        assert info["message_count"] == 0

    async def test_under_threshold_not_overflowing(
        self, session: SessionV2
    ) -> None:
        """Session with few messages is not overflowing."""
        await session.prompt("Hello")
        await session.add_text("Hi")
        await session.prompt("How are you?")
        await session.add_text("Good")
        info = session.check_overflow()
        assert not info["overflowing"]
        assert info["message_count"] == 4

    async def test_over_threshold_is_overflowing(
        self, session: SessionV2, event_store: EventStore
    ) -> None:
        """Session at threshold is overflowing using custom threshold."""
        for i in range(10):
            await session.prompt(f"Q{i}")
            await session.add_text(f"A{i}")
        info = session.check_overflow(threshold=20)
        assert info["overflowing"]
        assert info["message_count"] == 20
        assert info["threshold"] == 20

    async def test_near_overflow(self, session: SessionV2) -> None:
        """Session near threshold reports near_overflow."""
        for i in range(8):  # 8 pairs = 16 messages (80% of 20)
            await session.prompt(f"Q{i}")
            await session.add_text(f"A{i}")
        info = session.check_overflow(threshold=20)
        assert not info["overflowing"]
        assert info["near_overflow"]

    async def test_just_over_threshold(self, session: SessionV2) -> None:
        """Session just over threshold (21 msgs, threshold 20)."""
        for i in range(10):
            await session.prompt(f"Q{i}")
            await session.add_text(f"A{i}")
        info = session.check_overflow(threshold=20)
        assert info["overflowing"]
        assert info["message_count"] == 20
        assert info["threshold"] == 20

    async def test_custom_threshold(self, session: SessionV2) -> None:
        """Custom threshold parameter works."""
        await session.prompt("Q1")
        await session.add_text("A1")
        info = session.check_overflow(threshold=2)
        assert info["overflowing"]
        info = session.check_overflow(threshold=100)
        assert not info["overflowing"]

    async def test_deleted_session_not_overflowing(
        self, session: SessionV2
    ) -> None:
        """Deleted session returns normal overflow check."""
        await session.prompt("Q")
        await session.add_text("A")
        await session.delete()
        info = session.check_overflow()
        assert not info["overflowing"]


# ═══════════════════════════════════════════════════════════════════
# Tests: API endpoint
# ═══════════════════════════════════════════════════════════════════


class TestOverflowAPI:
    async def test_get_overflow(
        self, app: FastAPI, session: SessionV2
    ) -> None:
        """GET /api/sessions/{id}/overflow returns overflow status."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/sessions/{session.session_id}/overflow"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "overflowing" in data
        assert "near_overflow" in data
        assert "message_count" in data
        assert "threshold" in data
        assert data["message_count"] == 0
        assert not data["overflowing"]

    async def test_get_overflow_with_messages(
        self, app: FastAPI, event_store: EventStore
    ) -> None:
        """Endpoint reflects actual message count."""
        sess = await SessionV2.create(event_store, "gpt-4o")
        for i in range(5):
            await sess.prompt(f"Q{i}")
            await sess.add_text(f"A{i}")

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/sessions/{sess.session_id}/overflow")
        data = resp.json()
        assert data["message_count"] == 10
        assert not data["overflowing"]

    async def test_get_overflow_nonexistent(
        self, app: FastAPI, event_store: EventStore
    ) -> None:
        """Returns 404 for nonexistent session."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sessions/nonexistent/overflow")
        assert resp.status_code == 404
