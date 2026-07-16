"""P2-2: Integration System — WebSocket real-time bidirectional communication.

Provides WebSocketManager for client connection lifecycle, session subscription,
event broadcasting, and EventStore event bridging.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field

from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from cscode.storage.event_store import Event, EventStore
from cscode.utils.logging import get_logger

ChatHandler = Callable[..., Awaitable[None]]

logger = get_logger(__name__)

_TOKEN_EXPIRY_SECONDS = 3600


@dataclass
class IntegrationToken:
    """A lightweight WS auth token (UUID-based, in-memory)."""
    token: str
    created_at: float
    expires_at: float
    revoked: bool = False


class IntegrationTokenStore:
    """In-memory token store for WebSocket authentication.

    Tokens expire after TOKEN_EXPIRY_SECONDS (1 hour) and can be revoked.
    This is a simplified version of a JWT system — no external deps needed.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, IntegrationToken] = {}

    async def create(self, api_key: str) -> IntegrationToken:
        now = time.time()
        token = IntegrationToken(
            token=str(uuid.uuid4()),
            created_at=now,
            expires_at=now + _TOKEN_EXPIRY_SECONDS,
        )
        self._tokens[token.token] = token
        return token

    async def validate(self, token: str) -> bool:
        entry = self._tokens.get(token)
        if entry is None:
            return False
        if entry.revoked:
            return False
        if time.time() > entry.expires_at:
            self._tokens.pop(token, None)
            return False
        return True

    async def revoke(self, token: str) -> bool:
        entry = self._tokens.get(token)
        if entry is None:
            return False
        entry.revoked = True
        return True

    async def cleanup_expired(self) -> int:
        now = time.time()
        expired = [t for t, e in self._tokens.items() if now > e.expires_at]
        for t in expired:
            self._tokens.pop(t, None)
        return len(expired)

    def get_stats(self) -> dict[str, int]:
        now = time.time()
        active = sum(1 for e in self._tokens.values() if not e.revoked and now <= e.expires_at)
        return {"total_issued": len(self._tokens), "active": active}


@dataclass
class WSClient:
    """A connected WebSocket client with session subscriptions."""

    client_id: str
    websocket: WebSocket
    session_ids: set[str] = field(default_factory=set)
    authenticated: bool = False
    connected_at: float = 0.0
    last_activity: float = 0.0


class WebSocketManager:
    """Manages connected WebSocket clients, subscriptions, and event forwarding.

    Provides:
    - Client connect/disconnect lifecycle
    - Per-session subscription management
    - Targeted broadcast to subscribed clients
    - EventStore event bridge (forward persisted events to WebSocket clients)
    - Stale connection cleanup
    """

    def __init__(
        self,
        event_store: EventStore | None = None,
        chat_handler: ChatHandler | None = None,
    ) -> None:
        self._clients: dict[str, WSClient] = {}
        self._event_store = event_store
        self._chat_handler = chat_handler
        self._event_task: asyncio.Task[None] | None = None

    # ── Connection lifecycle ─────────────────────────────────────────

    async def connect(self, websocket: WebSocket) -> WSClient:
        """Accept a new WebSocket connection and register the client.

        Returns the created WSClient.
        """
        await websocket.accept()
        client_id = str(uuid.uuid4())
        now = time.time()
        client = WSClient(
            client_id=client_id,
            websocket=websocket,
            authenticated=False,
            connected_at=now,
            last_activity=now,
        )
        self._clients[client_id] = client
        logger.info(
            "[WS] Client connected: %s (total: %d)",
            client_id,
            len(self._clients),
        )
        return client

    async def disconnect(self, client_id: str) -> None:
        """Disconnect a client: close WebSocket and remove from registry.

        Idempotent — safe to call for unknown client_id.
        """
        client = self._clients.pop(client_id, None)
        if client is None:
            return
        logger.info(
            "[WS] Client disconnected: %s (total: %d)",
            client_id,
            len(self._clients),
        )
        try:
            await client.websocket.close(code=1000)
        except Exception:
            pass

    # ── Sending ──────────────────────────────────────────────────────

    async def send_to_client(self, client_id: str, event: Mapping[str, object]) -> bool:
        """Send a JSON event to a specific client.

        Returns True if sent, False if client not found.
        """
        client = self._clients.get(client_id)
        if client is None:
            return False
        try:
            await client.websocket.send_json(event)
            client.last_activity = time.time()
            return True
        except Exception:
            # Connection likely broken — remove from registry
            await self.disconnect(client_id)
            return False

    async def broadcast(
        self,
        event: Mapping[str, object],
        session_id: str | None = None,
    ) -> int:
        """Send an event to all clients (optionally filtered by session subscription).

        If session_id is provided, only clients subscribed to that session receive it.
        Returns the number of clients the event was sent to.
        """
        sent_count = 0
        for client in list(self._clients.values()):
            if session_id is not None and session_id not in client.session_ids:
                continue
            try:
                await client.websocket.send_json(event)
                client.last_activity = time.time()
                sent_count += 1
            except Exception:
                await self.disconnect(client.client_id)
        return sent_count

    # ── Subscription management ──────────────────────────────────────

    async def subscribe(self, client_id: str, session_id: str) -> None:
        """Subscribe a client to a session's events. Idempotent."""
        client = self._clients.get(client_id)
        if client is None:
            return
        client.session_ids.add(session_id)

    async def unsubscribe(self, client_id: str, session_id: str) -> None:
        """Unsubscribe a client from a session's events. Idempotent."""
        client = self._clients.get(client_id)
        if client is None:
            return
        client.session_ids.discard(session_id)

    # ── Client message handling ──────────────────────────────────────

    async def _handle_client_messages(self, client: WSClient) -> None:
        """Read and dispatch JSON messages from a client until disconnect.

        Supported message types:
        - ping        → pong
        - subscribe   → subscribe to session events
        - unsubscribe → unsubscribe from session events
        - unknown     → error response
        """
        try:
            while True:
                raw = await client.websocket.receive_json()
                client.last_activity = time.time()
                msg_type = raw.get("type", "")

                if msg_type == "ping":
                    await client.websocket.send_json({"type": "pong"})

                elif msg_type == "subscribe":
                    session_id = raw.get("session_id")
                    if session_id:
                        await self.subscribe(client.client_id, session_id)
                        logger.debug(
                            "[WS] Client %s subscribed to %s",
                            client.client_id,
                            session_id,
                        )

                elif msg_type == "unsubscribe":
                    session_id = raw.get("session_id")
                    if session_id:
                        await self.unsubscribe(client.client_id, session_id)

                elif msg_type == "chat":
                    if self._chat_handler is not None:
                        await self._chat_handler(client.client_id, raw)
                    else:
                        await client.websocket.send_json({
                            "type": "ack",
                            "data": {"message": "chat received"},
                        })

                else:
                    await client.websocket.send_json({
                        "type": "error",
                        "data": {"message": f"Unknown message type: {msg_type}"},
                    })

        except Exception:
            # Client disconnected or send failed
            pass

    # ── Event bridge ─────────────────────────────────────────────────

    async def _event_bridge(self) -> None:
        """Background task: subscribe to ALL session events from EventStore
        and forward them to subscribed WebSocket clients.
        """
        if self._event_store is None:
            return

        event_store: EventStore = self._event_store

        async def _forward_session(session_id: str) -> None:
            """Forward events from one session to subscribed clients."""
            try:
                async for event in event_store.subscribe(session_id, after_seq=0):
                    await self._broadcast_event(event, session_id)
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("[WS] Event bridge error for session %s", session_id)

        sessions: set[str] = set()
        for client in self._clients.values():
            sessions.update(client.session_ids)

        if not sessions:
            return

        tasks = [asyncio.create_task(_forward_session(sid)) for sid in sessions]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _event_bridge_once(self) -> None:
        """Forward one round of events from all known sessions (used in tests)."""
        if self._event_store is None:
            return
        # Collect all sessions that have subscribed clients
        sessions: set[str] = set()
        for client in self._clients.values():
            sessions.update(client.session_ids)

        for session_id in sessions:
            try:
                async for event in self._event_store.subscribe(session_id, after_seq=0):
                    await self._broadcast_event(event, session_id)
            except Exception:
                pass

    async def _broadcast_event(self, event: Event, session_id: str) -> None:
        """Forward a single EventStore event to clients subscribed to that session."""
        ws_event: dict[str, object] = {
            "type": "event",
            "event_type": event.type,
            "session_id": session_id,
            "data": event.data,
        }
        await self.broadcast(ws_event, session_id=session_id)

    # ── Lifecycle management ─────────────────────────────────────────

    async def cleanup_stale(self) -> int:
        """Remove clients whose WebSocket connection is closed.

        Returns the number of clients removed.
        """
        removed = 0
        for client_id, client in list(self._clients.items()):
            try:
                closed = client.websocket.client_state == WebSocketState.DISCONNECTED
            except Exception:
                closed = True
            if closed:
                self._clients.pop(client_id, None)
                removed += 1
        if removed:
            logger.info("[WS] Cleaned %d stale connections", removed)
        return removed

    def get_stats(self) -> dict[str, int]:
        """Return connection statistics."""
        return {
            "total_clients": len(self._clients),
            "total_subscriptions": sum(
                len(c.session_ids) for c in self._clients.values()
            ),
        }

    async def start_event_bridge(self) -> None:
        """Start the background event bridge task."""
        if self._event_store is not None and self._event_task is None:
            self._event_task = asyncio.create_task(self._event_bridge())

    async def stop_event_bridge(self) -> None:
        """Stop the background event bridge task."""
        if self._event_task is not None:
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
            self._event_task = None
