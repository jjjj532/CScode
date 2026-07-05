"""Tests for P2-9: Session Run State — track LLM execution status.

Tests cover:
1. mark_run_start() sets status to "running"
2. mark_run_stop() sets status to "stopped"
3. mark_run_error() sets status to "errored" with error info
4. mark_run_complete() sets status to "completed"
5. Run state persists across session load
6. API endpoint returns run state
7. API endpoint sets run state
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx._transports.asgi import ASGITransport

from cscode.core.session import SessionState, SessionV2
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
async def db(tmp_path):
    _db = Database(db_path=tmp_path / "run_state.db")
    await _db.init()
    yield _db
    await _db.close()


@pytest.fixture
async def event_store(db) -> EventStore:
    return EventStore(db)


@pytest.fixture
async def session(event_store: EventStore) -> SessionV2:
    return await SessionV2.create(event_store, "gpt-4o", title="RunState Test")


# ═══════════════════════════════════════════════════════════════════
# Dummy app fixture for API tests
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
async def app(event_store: EventStore) -> FastAPI:
    from fastapi import APIRouter

    _app = FastAPI()
    router = APIRouter()

    @router.get("/api/sessions/{session_id}/run-state")
    async def get_run_state(session_id: str):
        from cscode.core.session import SessionID as SID
        sess = await SessionV2.load(event_store, SID(session_id))
        if sess.state.seq == 0:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "status": sess.state.run_status,
            "error": sess.state.run_error,
        }

    @router.put("/api/sessions/{session_id}/run-state")
    async def set_run_state(session_id: str, body: dict[str, str]):
        from cscode.core.session import SessionID as SID
        sess = await SessionV2.load(event_store, SID(session_id))
        if sess.state.seq == 0:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found")
        status = body.get("status", "")
        method_map = {
            "running": sess.mark_run_start,
            "stopped": sess.mark_run_stop,
            "errored": lambda: sess.mark_run_error(error=body.get("error", "")),
            "completed": sess.mark_run_complete,
        }
        fn = method_map.get(status)
        if fn is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        await fn()
        from cscode.core.session import SessionID as SID
        sess2 = await SessionV2.load(event_store, SID(session_id))
        return {
            "status": sess2.state.run_status,
            "error": sess2.state.run_error,
        }

    _app.include_router(router)
    return _app


# ═══════════════════════════════════════════════════════════════════
# Tests: SessionV2 methods
# ═══════════════════════════════════════════════════════════════════


class TestSessionV2RunState:
    async def test_initial_run_status_is_idle(self, session: SessionV2) -> None:
        """New session starts with idle run status."""
        assert session.state.run_status == "idle"
        assert session.state.run_error == ""

    async def test_mark_run_start(self, session: SessionV2) -> None:
        """mark_run_start sets run_status to 'running'."""
        await session.mark_run_start()
        assert session.state.run_status == "running"

    async def test_mark_run_stop(self, session: SessionV2) -> None:
        """mark_run_stop sets run_status to 'stopped'."""
        await session.mark_run_start()
        await session.mark_run_stop()
        assert session.state.run_status == "stopped"

    async def test_mark_run_error(self, session: SessionV2) -> None:
        """mark_run_error sets run_status to 'errored' with error message."""
        await session.mark_run_error(error="Connection timeout")
        assert session.state.run_status == "errored"
        assert session.state.run_error == "Connection timeout"

    async def test_mark_run_complete(self, session: SessionV2) -> None:
        """mark_run_complete sets run_status to 'completed'."""
        await session.mark_run_start()
        await session.mark_run_complete()
        assert session.state.run_status == "completed"

    async def test_run_state_persists_across_load(
        self, session: SessionV2, event_store: EventStore
    ) -> None:
        """Run state survives session reload."""
        await session.mark_run_start()
        await session.mark_run_stop()

        loaded = await SessionV2.load(event_store, session.session_id)
        assert loaded.state.run_status == "stopped"

    async def test_error_persists_across_load(
        self, session: SessionV2, event_store: EventStore
    ) -> None:
        """Error message survives session reload."""
        await session.mark_run_error(error="Rate limit exceeded")

        loaded = await SessionV2.load(event_store, session.session_id)
        assert loaded.state.run_status == "errored"
        assert loaded.state.run_error == "Rate limit exceeded"

    async def test_run_states_are_sequential(self, session: SessionV2) -> None:
        """Multiple run state transitions work sequentially."""
        await session.mark_run_start()
        assert session.state.run_status == "running"

        await session.mark_run_complete()
        assert session.state.run_status == "completed"

        await session.mark_run_start()
        assert session.state.run_status == "running"

        await session.mark_run_error(error="OOM")
        assert session.state.run_status == "errored"
        assert session.state.run_error == "OOM"


# ═══════════════════════════════════════════════════════════════════
# Tests: API endpoints
# ═══════════════════════════════════════════════════════════════════


class TestRunStateAPI:
    async def test_get_run_state(
        self, app: FastAPI, session: SessionV2, event_store: EventStore
    ) -> None:
        """GET /api/sessions/{id}/run-state returns current run state."""
        await session.mark_run_start()

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/sessions/{session.session_id}/run-state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["error"] == ""

    async def test_put_run_state(
        self, app: FastAPI, session: SessionV2, event_store: EventStore
    ) -> None:
        """PUT /api/sessions/{id}/run-state sets run state."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                f"/api/sessions/{session.session_id}/run-state",
                json={"status": "errored", "error": "API timeout"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "errored"
        assert data["error"] == "API timeout"

    async def test_get_run_state_nonexistent(
        self, app: FastAPI, event_store: EventStore
    ) -> None:
        """GET returns 404 for nonexistent session."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sessions/nonexistent/run-state")
        assert resp.status_code == 404

    async def test_put_invalid_status(
        self, app: FastAPI, session: SessionV2, event_store: EventStore
    ) -> None:
        """PUT with invalid status returns 400."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                f"/api/sessions/{session.session_id}/run-state",
                json={"status": "invalid_status"},
            )
        assert resp.status_code == 400
