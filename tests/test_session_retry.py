"""Tests for P2-13: Session Retry — retry the last failed LLM prompt.

Tests cover:
1. get_last_prompt returns the last user message content
2. get_last_prompt returns None when session is empty
3. get_last_prompt returns None when last message is from assistant
4. retry() creates a new prompt event with the last user input
5. retry() works after multiple messages
6. API endpoint POST /api/sessions/{id}/retry
7. API endpoint returns 404 for nonexistent session
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx._transports.asgi import ASGITransport

from cscode.core.session import SessionID, SessionState, SessionV2
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
async def db(tmp_path):
    _db = Database(db_path=tmp_path / "retry.db")
    await _db.init()
    yield _db
    await _db.close()


@pytest.fixture
async def event_store(db) -> EventStore:
    return EventStore(db)


@pytest.fixture
async def session(event_store: EventStore) -> SessionV2:
    return await SessionV2.create(event_store, "gpt-4o", title="Retry Test")


@pytest.fixture
async def app(event_store: EventStore) -> FastAPI:
    from fastapi import APIRouter

    _app = FastAPI()
    router = APIRouter()

    @router.post("/api/sessions/{session_id}/retry")
    async def retry_session(session_id: str):
        sess = await SessionV2.load(event_store, SessionID(session_id))
        if sess.state.seq == 0:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found")
        last = sess.get_last_prompt()
        if last is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="No prompt to retry")
        evts = await sess.retry()
        return {
            "retried": True,
            "last_prompt": last,
            "event_count": len(evts),
        }

    _app.include_router(router)
    return _app


# ═══════════════════════════════════════════════════════════════════
# Tests: get_last_prompt
# ═══════════════════════════════════════════════════════════════════


class TestGetLastPrompt:
    async def test_empty_session_returns_none(self, session: SessionV2) -> None:
        """get_last_prompt returns None for empty session."""
        assert session.get_last_prompt() is None

    async def test_after_prompt_returns_text(self, session: SessionV2) -> None:
        """get_last_prompt returns the last user prompt text."""
        await session.prompt("What is Python?")
        result = session.get_last_prompt()
        assert result == "What is Python?"

    async def test_after_text_returns_last_prompt(self, session: SessionV2) -> None:
        """After assistant response, get_last_prompt still returns last user prompt."""
        await session.prompt("What is Python?")
        await session.add_text("Python is a programming language.")
        result = session.get_last_prompt()
        assert result == "What is Python?"

    async def test_multiple_turns(self, session: SessionV2) -> None:
        """After multiple turns, returns the most recent user prompt."""
        await session.prompt("Q1")
        await session.add_text("A1")
        await session.prompt("Q2")
        await session.add_text("A2")
        await session.prompt("Q3")
        result = session.get_last_prompt()
        assert result == "Q3"

    async def test_after_retry_returns_new_prompt(self, session: SessionV2) -> None:
        """get_last_prompt reflects retried prompt too."""
        await session.prompt("Hello")
        await session.retry()
        result = session.get_last_prompt()
        assert result == "Hello"


# ═══════════════════════════════════════════════════════════════════
# Tests: retry
# ═══════════════════════════════════════════════════════════════════


class TestRetry:
    async def test_retry_adds_event(self, session: SessionV2) -> None:
        """retry() adds a new prompt.admitted event."""
        await session.prompt("Hello")
        old_seq = session.state.seq
        await session.retry()
        assert session.state.seq > old_seq

    async def test_retry_increases_message_count(self, session: SessionV2) -> None:
        """retry() adds a new user message."""
        await session.prompt("Hello")
        await session.add_text("Hi")
        old_count = len(session.state.messages)
        await session.retry()
        assert len(session.state.messages) == old_count + 1
        # Last message should be the retried prompt from user
        last_msg = session.state.messages[-1]
        assert last_msg.role == "user"

    async def test_retry_empty_session_returns_none(self, session: SessionV2) -> None:
        """retry() on empty session returns empty list (no-op)."""
        result = await session.retry()
        assert result == []


# ═══════════════════════════════════════════════════════════════════
# Tests: API endpoint
# ═══════════════════════════════════════════════════════════════════


class TestRetryAPI:
    async def test_retry_endpoint_returns_last_prompt(
        self, app: FastAPI, event_store: EventStore
    ) -> None:
        """POST retry returns the last prompt and confirms retry."""
        sess = await SessionV2.create(event_store, "gpt-4o")
        await sess.prompt("Retry this")
        await sess.add_text("Some response")

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/sessions/{sess.session_id}/retry")
        assert resp.status_code == 200
        data = resp.json()
        assert data["retried"]
        assert data["last_prompt"] == "Retry this"

    async def test_retry_empty_session_returns_400(
        self, app: FastAPI, event_store: EventStore
    ) -> None:
        """POST retry on empty session returns 400."""
        sess = await SessionV2.create(event_store, "gpt-4o")

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/sessions/{sess.session_id}/retry")
        assert resp.status_code == 400

    async def test_retry_nonexistent_session_returns_404(
        self, app: FastAPI, event_store: EventStore
    ) -> None:
        """POST retry on nonexistent session returns 404."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/sessions/nonexistent/retry")
        assert resp.status_code == 404
