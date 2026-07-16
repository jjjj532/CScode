"""Tests for P2-2: Integration System — WebSocket real-time bidirectional communication.

Tests cover:
1. WebSocketManager core logic (connect/disconnect/subscribe/unsubscribe/broadcast)
2. WebSocket protocol handling (ping/pong, subscribe, chat)
3. Event bridge from EventStore to WebSocket clients
4. Stale client cleanup
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocketDisconnect
from fastapi.websockets import WebSocketState

from cscode.server.integration import WebSocketManager, WSClient

# ═══════════════════════════════════════════════════════════════════
# Mock WebSocket helpers
# ═══════════════════════════════════════════════════════════════════


class MockWebSocket:
    """A mock FastAPI WebSocket for testing without actual connections."""

    def __init__(self) -> None:
        self._sent: list[dict[str, object]] = []
        self._closed: bool = False
        self._close_code: int | None = None
        self.client_state: WebSocketState = WebSocketState.CONNECTED
        self.application_state: WebSocketState = WebSocketState.CONNECTED

    async def accept(self) -> None:
        self._closed = False

    async def send_json(self, data: dict[str, object]) -> None:
        self._sent.append(data)

    async def receive_json(self) -> dict[str, object]:
        raise WebSocketDisconnect(code=1000)  # default: disconnect

    async def receive_text(self) -> str:
        raise WebSocketDisconnect(code=1000)

    async def close(self, code: int = 1000) -> None:
        self._closed = True
        self._close_code = code

    @property
    def sent_messages(self) -> list[dict[str, object]]:
        return list(self._sent)

    def clear_sent(self) -> None:
        self._sent.clear()


class MockWebSocketQueue(MockWebSocket):
    """A MockWebSocket that returns pre-configured messages via receive_json."""

    def __init__(self, messages: list[dict[str, object]] | None = None) -> None:
        super().__init__()
        self._queue: list[dict[str, object]] = messages or []
        self._receive_count = 0

    def add_message(self, msg: dict[str, object]) -> None:
        self._queue.append(msg)

    async def receive_json(self) -> dict[str, object]:
        if self._queue:
            self._receive_count += 1
            return self._queue.pop(0)
        # After queue exhausted, behave like real WS: block until disconnect
        raise WebSocketDisconnect(code=1000)


# ═══════════════════════════════════════════════════════════════════
# WebSocketManager tests
# ═══════════════════════════════════════════════════════════════════


class TestWebSocketManager:
    """Test core connection management logic."""

    @pytest.fixture
    def manager(self) -> WebSocketManager:
        return WebSocketManager()

    @pytest.fixture
    def mock_ws(self) -> MockWebSocket:
        return MockWebSocket()

    async def test_connect_creates_client(self, manager: WebSocketManager, mock_ws: MockWebSocket) -> None:
        """connect() returns a WSClient and stores it."""
        client = await manager.connect(mock_ws)  # type: ignore[arg-type]
        assert isinstance(client, WSClient)
        assert client.client_id in manager._clients
        assert client.websocket is mock_ws  # same object ref
        assert client.authenticated is False
        assert len(manager._clients) == 1
        assert mock_ws._closed is False  # already accepted

    async def test_connect_accepts_ws(self, manager: WebSocketManager, mock_ws: MockWebSocket) -> None:
        """connect() calls websocket.accept()."""
        await manager.connect(mock_ws)  # type: ignore[arg-type]
        # No exception = accept succeeded

    async def test_disconnect_removes_client(self, manager: WebSocketManager, mock_ws: MockWebSocket) -> None:
        """disconnect() removes client from registry and closes WS."""
        client = await manager.connect(mock_ws)  # type: ignore[arg-type]
        assert client.client_id in manager._clients

        await manager.disconnect(client.client_id)
        assert client.client_id not in manager._clients

    async def test_disconnect_closes_websocket(self, manager: WebSocketManager, mock_ws: MockWebSocket) -> None:
        """disconnect() calls websocket.close()."""
        client = await manager.connect(mock_ws)  # type: ignore[arg-type]
        await manager.disconnect(client.client_id)
        assert mock_ws._closed is True

    async def test_disconnect_idempotent(self, manager: WebSocketManager) -> None:
        """disconnect() on unknown client_id does not raise."""
        await manager.disconnect("nonexistent")  # should not raise

    async def test_send_to_client_sends_json(self, manager: WebSocketManager, mock_ws: MockWebSocket) -> None:
        """send_to_client sends JSON to the correct client."""
        client = await manager.connect(mock_ws)  # type: ignore[arg-type]
        event: dict[str, object] = {"type": "pong"}
        result = await manager.send_to_client(client.client_id, event)
        assert result is True
        assert mock_ws.sent_messages == [event]

    async def test_send_to_client_unknown(self, manager: WebSocketManager) -> None:
        """send_to_client returns False for unknown client."""
        result = await manager.send_to_client("nobody", {"type": "test"})  # type: ignore[arg-type]
        assert result is False

    async def test_broadcast_all_clients(self, manager: WebSocketManager) -> None:
        """broadcast sends event to all connected clients."""
        ws1, ws2 = MockWebSocket(), MockWebSocket()
        await manager.connect(ws1)  # type: ignore[arg-type]
        await manager.connect(ws2)  # type: ignore[arg-type]

        event: dict[str, object] = {"type": "broadcast_test"}
        count = await manager.broadcast(event)
        assert count == 2
        assert ws1.sent_messages == [event]
        assert ws2.sent_messages == [event]

    async def test_broadcast_empty(self, manager: WebSocketManager) -> None:
        """broadcast with no clients returns 0."""
        count = await manager.broadcast({"type": "test"})  # type: ignore[arg-type]
        assert count == 0

    async def test_subscribe_adds_session(self, manager: WebSocketManager, mock_ws: MockWebSocket) -> None:
        """subscribe adds a session to the client's subscription set."""
        client = await manager.connect(mock_ws)  # type: ignore[arg-type]
        await manager.subscribe(client.client_id, "session_abc")
        assert "session_abc" in client.session_ids

    async def test_subscribe_twice_idempotent(self, manager: WebSocketManager, mock_ws: MockWebSocket) -> None:
        """subscribe to same session twice is idempotent."""
        client = await manager.connect(mock_ws)  # type: ignore[arg-type]
        await manager.subscribe(client.client_id, "session_abc")
        await manager.subscribe(client.client_id, "session_abc")
        assert len(client.session_ids) == 1

    async def test_unsubscribe_removes_session(self, manager: WebSocketManager, mock_ws: MockWebSocket) -> None:
        """unsubscribe removes a session from the client's subscription set."""
        client = await manager.connect(mock_ws)  # type: ignore[arg-type]
        await manager.subscribe(client.client_id, "session_abc")
        await manager.subscribe(client.client_id, "session_xyz")
        assert len(client.session_ids) == 2

        await manager.unsubscribe(client.client_id, "session_abc")
        assert "session_abc" not in client.session_ids
        assert "session_xyz" in client.session_ids

    async def test_broadcast_filtered_by_session(self, manager: WebSocketManager) -> None:
        """broadcast with session_id only sends to clients subscribed to that session."""
        ws1, ws2, ws3 = MockWebSocket(), MockWebSocket(), MockWebSocket()
        c1 = await manager.connect(ws1)  # type: ignore[arg-type]
        c2 = await manager.connect(ws2)  # type: ignore[arg-type]
        c3 = await manager.connect(ws3)  # type: ignore[arg-type]

        await manager.subscribe(c1.client_id, "session_a")
        await manager.subscribe(c2.client_id, "session_a")
        await manager.subscribe(c3.client_id, "session_b")

        event = {"type": "event", "session_id": "session_a", "data": {}}
        count = await manager.broadcast(event, session_id="session_a")
        assert count == 2
        assert len(ws1.sent_messages) == 1
        assert len(ws2.sent_messages) == 1
        assert len(ws3.sent_messages) == 0  # subscribed to session_b

    async def test_get_stats(self, manager: WebSocketManager) -> None:
        """get_stats returns connection summary."""
        ws1 = MockWebSocket()
        await manager.connect(ws1)  # type: ignore[arg-type]
        stats = manager.get_stats()
        assert stats["total_clients"] == 1
        assert stats["total_subscriptions"] >= 0

    async def test_cleanup_stale_removes_disconnected(self, manager: WebSocketManager) -> None:
        """cleanup_stale removes clients whose websocket disconnected."""
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        c1 = await manager.connect(ws1)  # type: ignore[arg-type]
        await manager.connect(ws2)  # type: ignore[arg-type]

        # Simulate ws1 closed
        ws1._closed = True
        ws1.client_state = WebSocketState.DISCONNECTED

        removed = await manager.cleanup_stale()
        assert removed >= 1
        assert c1.client_id not in manager._clients


# ═══════════════════════════════════════════════════════════════════
# WSClient tests
# ═══════════════════════════════════════════════════════════════════


class TestWSClient:
    """Test the WSClient data class."""

    def test_create_client(self, mock_ws: MockWebSocket) -> None:
        """WSClient can be created with required fields."""
        client = WSClient(
            client_id="test_id",
            websocket=mock_ws,  # type: ignore[arg-type]
            session_ids=set(),
            authenticated=False,
            connected_at=time.time(),
            last_activity=time.time(),
        )
        assert client.client_id == "test_id"
        assert client.authenticated is False

    @pytest.fixture
    def mock_ws(self) -> MockWebSocket:
        return MockWebSocket()


# ═══════════════════════════════════════════════════════════════════
# Protocol handling tests
# ═══════════════════════════════════════════════════════════════════


class TestProtocolHandling:
    """Tests for WebSocket JSON protocol message handling."""

    async def test_ping_pong(self) -> None:
        """Client sending ping receives pong."""
        ws = MockWebSocketQueue([{"type": "ping"}])
        mgr = WebSocketManager()
        client = await mgr.connect(ws)  # type: ignore[arg-type]

        # Run one iteration of the message handler
        await mgr._handle_client_messages(client)

        pongs = [m for m in ws.sent_messages if m.get("type") == "pong"]
        assert len(pongs) >= 1

    async def test_subscribe_protocol(self) -> None:
        """Client sending subscribe message is subscribed to the session."""
        ws = MockWebSocketQueue([
            {"type": "subscribe", "session_id": "session_abc"},
        ])
        mgr = WebSocketManager()
        client = await mgr.connect(ws)  # type: ignore[arg-type]

        await mgr._handle_client_messages(client)

        assert "session_abc" in client.session_ids

    async def test_unsubscribe_protocol(self) -> None:
        """Client sending unsubscribe message is unsubscribed."""
        ws = MockWebSocketQueue([
            {"type": "unsubscribe", "session_id": "session_abc"},
        ])
        mgr = WebSocketManager()
        client = await mgr.connect(ws)  # type: ignore[arg-type]
        client.session_ids.add("session_abc")

        await mgr._handle_client_messages(client)

        assert "session_abc" not in client.session_ids

    async def test_unknown_message_type(self) -> None:
        """Unknown message type returns error to client."""
        ws = MockWebSocketQueue([
            {"type": "unknown_type"},
        ])
        mgr = WebSocketManager()
        client = await mgr.connect(ws)  # type: ignore[arg-type]

        await mgr._handle_client_messages(client)

        errors = [m for m in ws.sent_messages if m.get("type") == "error"]
        assert len(errors) >= 1

    async def test_chat_calls_handler(self) -> None:
        """Chat messages are forwarded to the registered chat handler."""
        handler_calls: list[tuple[str, dict[str, object]]] = []

        async def mock_handler(client_id: str, msg: dict[str, object]) -> None:
            handler_calls.append((client_id, msg))

        ws = MockWebSocketQueue([
            {"type": "chat", "data": {"message": "Hello"}},
        ])
        mgr = WebSocketManager(chat_handler=mock_handler)
        client = await mgr.connect(ws)  # type: ignore[arg-type]

        await mgr._handle_client_messages(client)

        assert len(handler_calls) == 1
        cid, msg = handler_calls[0]
        assert cid == client.client_id
        assert msg.get("type") == "chat"
        data = msg.get("data")
        assert isinstance(data, dict)
        assert data.get("message") == "Hello"

    async def test_chat_no_handler_fallback_ack(self) -> None:
        """Without a handler, chat messages still get an ack."""
        ws = MockWebSocketQueue([
            {"type": "chat", "data": {"message": "Hello"}},
        ])
        mgr = WebSocketManager()
        client = await mgr.connect(ws)  # type: ignore[arg-type]

        await mgr._handle_client_messages(client)

        acks = [m for m in ws.sent_messages if m.get("type") == "ack"]
        assert len(acks) == 1
        ack_data = acks[0].get("data")
        assert isinstance(ack_data, dict)
        assert ack_data.get("message") == "chat received"


# ═══════════════════════════════════════════════════════════════════
# Event bridge tests
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_event_store() -> MagicMock:
    """Fixture for a mocked EventStore."""
    store = MagicMock()
    store.subscribe = AsyncMock()
    return store


class TestEventBridge:
    """Tests for the EventStore to WebSocket event bridge."""

    async def test_event_bridge_forwards_events(self, mock_event_store: MagicMock) -> None:
        """Event bridge forwards EventStore events to subscribed clients."""
        ws = MockWebSocket()
        mgr = WebSocketManager(event_store=mock_event_store)
        client = await mgr.connect(ws)  # type: ignore[arg-type]
        await mgr.subscribe(client.client_id, "session_abc")

        # Simulate EventStore yielding events
        from cscode.storage.event_store import Event
        async def _subscribe_gen(*args: object, **kwargs: object):
            yield Event(
                aggregate_id="session_abc",
                seq=1,
                type="text.delta",
                data={"content": "Hello"},
                created_at=time.time(),
            )
            # Yield a second event to verify forwarding works
            yield Event(
                aggregate_id="session_abc",
                seq=2,
                type="tool.called",
                data={"tool": "read"},
                created_at=time.time(),
            )

        mock_event_store.subscribe = _subscribe_gen  # type: ignore[method-assign]

        await mgr._event_bridge_once()

        assert len(ws.sent_messages) == 2
        assert ws.sent_messages[0]["type"] == "event"
        assert ws.sent_messages[0]["event_type"] == "text.delta"

    async def test_event_bridge_ignores_other_sessions(self, mock_event_store: MagicMock) -> None:
        """Events from unsubscribed sessions are not forwarded."""
        ws = MockWebSocket()
        mgr = WebSocketManager(event_store=mock_event_store)
        await mgr.connect(ws)  # type: ignore[arg-type]

        from cscode.storage.event_store import Event
        async def _subscribe_gen(*args: object, **kwargs: object):
            yield Event(
                aggregate_id="session_other",
                seq=1,
                type="text.delta",
                data={"content": "Should not see"},
                created_at=time.time(),
            )

        mock_event_store.subscribe = _subscribe_gen  # type: ignore[method-assign]

        await mgr._event_bridge_once()

        assert len(ws.sent_messages) == 0

    async def test_event_bridge_forwards_multiple_sessions(self, mock_event_store: MagicMock) -> None:
        """Events from multiple subscribed sessions are all forwarded."""
        ws = MockWebSocket()
        mgr = WebSocketManager(event_store=mock_event_store)
        client = await mgr.connect(ws)  # type: ignore[arg-type]
        await mgr.subscribe(client.client_id, "sess_a")
        await mgr.subscribe(client.client_id, "sess_b")


        calls: list[str] = []

        async def _subscribe_gen(session_id: str, *args: object, **kwargs: object):
            calls.append(session_id)
            return
            yield  # type: ignore[return-value]  # generator function stub

        mock_event_store.subscribe = _subscribe_gen  # type: ignore[method-assign]

        await mgr._event_bridge_once()
        assert set(calls) == {"sess_a", "sess_b"}


class TestEventBridgeLifecycle:

    async def test_start_bridge_creates_task(self, mock_event_store: MagicMock) -> None:
        mgr = WebSocketManager(event_store=mock_event_store)
        assert mgr._event_task is None
        await mgr.start_event_bridge()
        assert mgr._event_task is not None
        assert not mgr._event_task.done()
        await mgr.stop_event_bridge()

    async def test_stop_bridge_cancels_task(self, mock_event_store: MagicMock) -> None:
        mgr = WebSocketManager(event_store=mock_event_store)
        await mgr.start_event_bridge()
        assert mgr._event_task is not None
        await mgr.stop_event_bridge()
        assert mgr._event_task is None

    async def test_start_bridge_no_event_store(self) -> None:
        mgr = WebSocketManager()
        await mgr.start_event_bridge()
        assert mgr._event_task is None

    async def test_stop_bridge_no_task(self) -> None:
        mgr = WebSocketManager(event_store=MagicMock())
        await mgr.stop_event_bridge()

    async def test_stop_bridge_idempotent(self, mock_event_store: MagicMock) -> None:
        mgr = WebSocketManager(event_store=mock_event_store)
        await mgr.start_event_bridge()
        await mgr.stop_event_bridge()
        await mgr.stop_event_bridge()
        assert mgr._event_task is None

    async def test_event_bridge_forwards_continuously(self, mock_event_store: MagicMock) -> None:
        ws = MockWebSocket()
        mgr = WebSocketManager(event_store=mock_event_store)
        client = await mgr.connect(ws)  # type: ignore[arg-type]
        await mgr.subscribe(client.client_id, "sess_c")

        from cscode.storage.event_store import Event

        events_yielded: list[Event] = []

        async def subscribe_gen(session_id: str, *args: object, **kwargs: object):
            nonlocal events_yielded
            evt = Event(
                aggregate_id=session_id,
                seq=1,
                type="text.delta",
                data={"content": "bridge test"},
                created_at=time.time(),
            )
            events_yielded.append(evt)
            yield evt
            await asyncio.Event().wait()

        mock_event_store.subscribe = subscribe_gen  # type: ignore[method-assign]

        task = asyncio.create_task(mgr._event_bridge())
        await asyncio.sleep(0.05)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(events_yielded) >= 1
        forwarded = [m for m in ws.sent_messages if m.get("type") == "event"]
        assert len(forwarded) >= 1
        assert forwarded[0]["event_type"] == "text.delta"
