"""Tests for P2-5: Sync — multi-instance event synchronization.

Tests cover:
1. EventStore.scan_events_global() — global event scanning by rowid
2. SyncEngine.pull() — pull events from remote (direct EventStore)
3. SyncEngine.push() — push events to remote (direct EventStore)
4. SyncEngine — idempotent sync (dedup by aggregate_id+seq)
5. Sync API endpoints — /api/sync/events, /api/sync/push
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI

from cscode.schema.ids import SessionID
from cscode.storage.db import Database
from cscode.storage.event_store import Event, EventStore
from httpx._transports.asgi import ASGITransport


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
async def db(tmp_path):
    _db = Database(db_path=str(tmp_path / "sync_test.db"))
    await _db.init()
    yield _db
    await _db.close()


@pytest.fixture
async def event_store(db: Database) -> EventStore:
    return EventStore(db)


@pytest.fixture
async def remote_db(tmp_path):
    _db = Database(db_path=str(tmp_path / "remote_test.db"))
    await _db.init()
    yield _db
    await _db.close()


@pytest.fixture
async def remote_store(remote_db: Database) -> EventStore:
    return EventStore(remote_db)


# ═══════════════════════════════════════════════════════════════════
# EventStore.scan_events_global
# ═══════════════════════════════════════════════════════════════════


class TestScanEventsGlobal:
    @pytest.mark.asyncio
    async def test_scan_empty(self, event_store: EventStore) -> None:
        """scan_events_global returns empty list when no events exist."""
        events = await event_store.scan_events_global()
        assert events == []

    @pytest.mark.asyncio
    async def test_scan_all_events(self, event_store: EventStore) -> None:
        """scan_events_global returns all events across aggregates."""
        await event_store.append("agg_1", [{"type": "test.a", "data": {"v": 1}}])
        await event_store.append("agg_2", [{"type": "test.b", "data": {"v": 2}}])

        events = await event_store.scan_events_global()
        assert len(events) == 2
        assert events[0].type == "test.a"
        assert events[1].type == "test.b"

    @pytest.mark.asyncio
    async def test_scan_after_id(self, event_store: EventStore) -> None:
        """scan_events_global(after_id=N) returns only events with id > N."""
        e1 = await event_store.append("agg_1", [{"type": "test.a", "data": {"v": 1}}])
        await event_store.append("agg_2", [{"type": "test.b", "data": {"v": 2}}])

        events = await event_store.scan_events_global(after_id=e1[0].id)
        assert len(events) == 1
        assert events[0].type == "test.b"

    @pytest.mark.asyncio
    async def test_scan_limit(self, event_store: EventStore) -> None:
        """scan_events_global respects limit."""
        for i in range(5):
            await event_store.append(f"agg_{i}", [{"type": "test", "data": {"i": i}}])

        events = await event_store.scan_events_global(limit=3)
        assert len(events) == 3


# ═══════════════════════════════════════════════════════════════════
# SyncEngine
# ═══════════════════════════════════════════════════════════════════


class TestSyncEngine:
    @pytest.mark.asyncio
    async def test_push_events(
        self, event_store: EventStore, remote_store: EventStore
    ) -> None:
        """push sends local events to remote EventStore."""
        from cscode.core.sync import SyncEngine

        # Populate local store
        await event_store.append(
            SessionID("sess_1"),
            [{"type": "session.created", "data": {"title": "Test"}}],
        )

        engine = SyncEngine(local_store=event_store)
        pushed = await engine.push(remote_store)
        assert pushed == 1

        # Verify remote has the events
        remote_events = await remote_store.read(SessionID("sess_1"))
        assert len(remote_events) == 1
        assert remote_events[0].type == "session.created"

    @pytest.mark.asyncio
    async def test_push_empty(self, event_store: EventStore, remote_store: EventStore) -> None:
        """push with no new events returns 0."""
        from cscode.core.sync import SyncEngine

        engine = SyncEngine(local_store=event_store)
        pushed = await engine.push(remote_store)
        assert pushed == 0

    @pytest.mark.asyncio
    async def test_pull_events(
        self, event_store: EventStore, remote_store: EventStore
    ) -> None:
        """pull fetches events from remote EventStore and applies locally."""
        from cscode.core.sync import SyncEngine

        # Populate remote store
        await remote_store.append(
            SessionID("sess_1"),
            [{"type": "session.created", "data": {"title": "Remote"}}],
        )

        engine = SyncEngine(local_store=event_store)
        pulled = await engine.pull(remote_store)
        assert pulled == 1

        # Verify local has the events
        local_events = await event_store.read(SessionID("sess_1"))
        assert len(local_events) == 1
        assert local_events[0].type == "session.created"

    @pytest.mark.asyncio
    async def test_pull_empty(self, event_store: EventStore, remote_store: EventStore) -> None:
        """pull with no remote events returns 0."""
        from cscode.core.sync import SyncEngine

        engine = SyncEngine(local_store=event_store)
        pulled = await engine.pull(remote_store)
        assert pulled == 0

    @pytest.mark.asyncio
    async def test_dedup_on_sync(
        self, event_store: EventStore, remote_store: EventStore
    ) -> None:
        """Pulling same events twice is idempotent — seq-based dedup."""
        from cscode.core.sync import SyncEngine

        await remote_store.append(
            SessionID("sess_1"),
            [{"type": "session.created", "data": {"title": "Test"}}],
        )

        engine = SyncEngine(local_store=event_store)
        await engine.pull(remote_store)
        pulled_again = await engine.pull(remote_store)

        # Second pull should bring 0 new events
        assert pulled_again == 0

    @pytest.mark.asyncio
    async def test_sync_state_tracking(
        self, event_store: EventStore, remote_store: EventStore
    ) -> None:
        """SyncEngine tracks state between operations."""
        from cscode.core.sync import SyncEngine

        await remote_store.append(
            SessionID("sess_1"),
            [{"type": "session.created", "data": {"title": "A"}}],
        )

        engine = SyncEngine(local_store=event_store, remote_url="test://local")
        assert engine.last_sync_seq == 0

        await engine.pull(remote_store)
        assert engine.last_sync_seq > 0

    @pytest.mark.asyncio
    async def test_reset_sync_state(self, event_store: EventStore) -> None:
        """reset_sync clears tracked state."""
        from cscode.core.sync import SyncEngine

        engine = SyncEngine(local_store=event_store)
        engine.set_sync_seq(42)
        engine.reset_sync()
        assert engine.last_sync_seq == 0

    @pytest.mark.asyncio
    async def test_push_updates_sync_seq(
        self, event_store: EventStore, remote_store: EventStore
    ) -> None:
        """push updates last_sync_seq after successful sync."""
        from cscode.core.sync import SyncEngine

        await event_store.append(
            SessionID("sess_1"),
            [{"type": "session.created", "data": {"title": "Test"}}],
        )

        engine = SyncEngine(local_store=event_store)
        await engine.push(remote_store)
        assert engine.last_sync_seq > 0

    @pytest.mark.asyncio
    async def test_full_roundtrip(
        self, event_store: EventStore, remote_store: EventStore
    ) -> None:
        """Bidirectional sync: push then pull yields consistent state."""
        from cscode.core.sync import SyncEngine

        # Local has event A, remote has event B
        await event_store.append(
            SessionID("sess_1"),
            [{"type": "session.created", "data": {"title": "Local"}}],
        )
        await remote_store.append(
            SessionID("sess_2"),
            [{"type": "session.created", "data": {"title": "Remote"}}],
        )

        local_engine = SyncEngine(local_store=event_store)
        remote_engine = SyncEngine(local_store=remote_store)

        # Push local -> remote
        await local_engine.push(remote_store)
        # Pull remote -> local
        await local_engine.pull(remote_store)

        # Both stores should have both events
        local_all = await event_store.scan_events_global()
        remote_all = await remote_store.scan_events_global()
        assert len(local_all) == 2
        assert len(remote_all) == 2


# ═══════════════════════════════════════════════════════════════════
# SyncEngine with HTTP transport (via respx mock)
# ═══════════════════════════════════════════════════════════════════


class TestSyncEngineHTTP:
    @pytest.mark.asyncio
    async def test_pull_via_http(
        self, event_store: EventStore, remote_store: EventStore
    ) -> None:
        """pull via HTTP transport fetches and applies events."""
        from cscode.core.sync import SyncEngine

        await remote_store.append(
            SessionID("sess_1"),
            [{"type": "session.created", "data": {"title": "HTTP"}}],
        )

        # Use the remote_store-based HTTP response mock
        async with respx.mock:
            # Mock the sync events endpoint
            route = respx.get("http://remote/api/sync/events").mock(
                return_value=httpx.Response(
                    200,
                    json=[
                        {
                            "id": 1,
                            "aggregate_id": "sess_1",
                            "seq": 1,
                            "type": "session.created",
                            "data": {"title": "HTTP"},
                            "created_at": time.time(),
                        }
                    ],
                )
            )

            engine = SyncEngine(local_store=event_store, remote_url="http://remote")
            pulled = await engine.pull()
            assert pulled == 1

            assert route.called

        # Verify local has events
        local_events = await event_store.read(SessionID("sess_1"))
        assert len(local_events) == 1
        assert local_events[0].type == "session.created"

    @pytest.mark.asyncio
    async def test_pull_via_http_empty(
        self, event_store: EventStore
    ) -> None:
        """pull via HTTP with no new events returns 0."""
        from cscode.core.sync import SyncEngine

        async with respx.mock:
            route = respx.get("http://remote/api/sync/events").mock(
                return_value=httpx.Response(200, json=[])
            )

            engine = SyncEngine(local_store=event_store, remote_url="http://remote")
            pulled = await engine.pull()
            assert pulled == 0
            assert route.called

    @pytest.mark.asyncio
    async def test_push_via_http(
        self, event_store: EventStore
    ) -> None:
        """push via HTTP sends events to remote server."""
        from cscode.core.sync import SyncEngine

        await event_store.append(
            SessionID("sess_1"),
            [{"type": "session.created", "data": {"title": "Push test"}}],
        )

        async with respx.mock:
            route = respx.post("http://remote/api/sync/push").mock(
                return_value=httpx.Response(200, json={"pushed": 1})
            )

            engine = SyncEngine(local_store=event_store, remote_url="http://remote")
            pushed = await engine.push()
            assert pushed == 1
            assert route.called

            # Verify request body
            assert route.calls[0].request.method == "POST"
            import json as _json
            body = _json.loads(route.calls[0].request.content)
            assert len(body["events"]) == 1


# ═══════════════════════════════════════════════════════════════════
# Sync API endpoints (via httpx.AsyncClient, not TestClient)
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def sync_app(event_store: EventStore) -> FastAPI:
    """Minimal FastAPI with sync endpoints for testing."""
    from fastapi import APIRouter

    app = FastAPI()
    sync_router = APIRouter()

    @sync_router.get("/api/sync/events")
    async def get_sync_events(after_id: int = 0):
        events = await event_store.scan_events_global(after_id=after_id)
        return [
            {
                "id": e.id,
                "aggregate_id": e.aggregate_id,
                "seq": e.seq,
                "type": e.type,
                "data": e.data,
                "created_at": e.created_at,
            }
            for e in events
        ]

    @sync_router.post("/api/sync/push")
    async def push_sync_events(body: dict):
        count = 0
        for evt_data in body.get("events", []):
            try:
                await event_store.append(
                    evt_data["aggregate_id"],
                    [{"type": evt_data["type"], "data": evt_data.get("data", {})}],
                )
                count += 1
            except Exception:
                pass
        return {"pushed": count}

    app.include_router(sync_router)
    return app


class TestSyncAPI:
    @pytest.mark.asyncio
    async def test_get_events_empty(
        self, sync_app: FastAPI
    ) -> None:
        """GET /api/sync/events returns empty list."""
        transport = ASGITransport(app=sync_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sync/events", params={"after_id": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_get_events_with_data(
        self, event_store: EventStore, sync_app: FastAPI
    ) -> None:
        """GET /api/sync/events returns stored events."""
        await event_store.append(
            SessionID("sess_a"),
            [{"type": "session.created", "data": {"title": "A"}}],
        )

        transport = ASGITransport(app=sync_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sync/events", params={"after_id": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

        evt = data[0]
        assert "id" in evt
        assert evt["aggregate_id"] == "sess_a"
        assert evt["type"] == "session.created"

    @pytest.mark.asyncio
    async def test_push_endpoint(
        self, event_store: EventStore, sync_app: FastAPI
    ) -> None:
        """POST /api/sync/push receives and stores events."""
        transport = ASGITransport(app=sync_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/sync/push",
                json={
                    "events": [
                        {
                            "aggregate_id": "sess_push",
                            "seq": 1,
                            "type": "session.created",
                            "data": {"title": "Pushed"},
                        }
                    ]
                },
            )
        assert resp.status_code == 200
        result = resp.json()
        assert result["pushed"] == 1

        events = await event_store.read(SessionID("sess_push"))
        assert len(events) == 1
        assert events[0].type == "session.created"


# ═══════════════════════════════════════════════════════════════════
# Event.id field
# ═══════════════════════════════════════════════════════════════════


class TestEventID:
    @pytest.mark.asyncio
    async def test_event_has_id(self, event_store: EventStore) -> None:
        """Appended events have an auto-increment id field."""
        stored = await event_store.append(
            SessionID("sess_1"),
            [{"type": "session.created", "data": {"title": "Test"}}],
        )
        assert stored[0].id > 0
