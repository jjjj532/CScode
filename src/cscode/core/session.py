"""SessionV2 — Event Sourcing based Session.

Wraps EventStore to provide a session abstraction where all state
changes are immutable events. Session state is reconstructed by
replaying events through a projector.

Usage:
    session = await SessionV2.create(event_store, "gpt-4o", "openai")
    await session.prompt("Hello, world!")
    state = session.state  # reconstructed from events
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from cscode.schema.ids import SessionID
from cscode.schema.messages import Message, MessageRole, TextPart
from cscode.storage.event_store import Event, EventStore
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SessionState:
    """Reconstructed state of a session from its event stream."""

    session_id: SessionID
    title: str = ""
    provider: str = "openai"
    model: str = "gpt-4o"
    agent: str = "auto"
    messages: tuple[Message, ...] = ()
    tool_rounds: int = 0
    status: str = "active"
    created_at: float = 0.0
    updated_at: float = 0.0
    seq: int = 0
    """The latest event seq applied to this state."""


class SessionProjector:
    """Projects events into SessionState and Message lists."""

    @staticmethod
    def project(events: list[Event]) -> SessionState:
        """Reconstruct session state from a list of events."""
        logger.debug("Projecting %d events", len(events))
        state = SessionState(session_id=SessionID(""), created_at=time.time())
        messages: list[Message] = []

        for event in events:
            state.seq = event.seq
            state.updated_at = event.created_at

            match event.type:
                case "session.created":
                    d = event.data
                    state.session_id = SessionID(event.aggregate_id)
                    state.title = d.get("title", "")
                    state.provider = d.get("provider", "openai")
                    state.model = d.get("model", "gpt-4o")
                    state.agent = d.get("agent", "auto")
                    state.created_at = event.created_at

                case "session.updated":
                    d = event.data
                    if "title" in d:
                        state.title = str(d["title"])
                    if "provider" in d:
                        state.provider = str(d["provider"])
                    if "model" in d:
                        state.model = str(d["model"])
                    if "agent" in d:
                        state.agent = str(d["agent"])

                case "prompt.admitted":
                    content = event.data.get("prompt") or event.data.get("content", "")
                    messages.append(
                        Message(
                            id=None,
                            role=MessageRole.USER,
                            parts=(TextPart(text=str(content)),),
                        )
                    )

                case "text.ended":
                    messages.append(
                        Message(
                            id=None,
                            role=MessageRole.ASSISTANT,
                            parts=(TextPart(text=str(event.data.get("content", ""))),),
                        )
                    )

                case "tool.called":
                    state.tool_rounds += 1

                case "compaction":
                    baseline_seq = event.data.get("baseline_seq", 0)
                    messages = [
                        m for m in messages
                        if getattr(m, "_seq", float("inf")) >= baseline_seq
                    ]

                case "session.deleted":
                    state.status = "deleted"

                case _:
                    logger.warning("Unknown event type in projection: %s", event.type)

        state.messages = tuple(messages)
        return state

    @staticmethod
    def build_context(state: SessionState) -> list[Message]:
        """Build the LLM context message list from session state.

        Returns messages suitable for passing to LLMClient.generate/stream.
        """
        return list(state.messages)


class SessionV2:
    """Event Sourcing based session.

    All mutations go through EventStore.append(). Session state is
    reconstructed by replaying events via SessionProjector.

    Thread-safe: yes (delegates to EventStore's per-aggregate lock).
    """

    def __init__(
        self,
        event_store: EventStore,
        session_id: SessionID,
        state: SessionState | None = None,
    ) -> None:
        self._event_store = event_store
        self._session_id = session_id
        self._state = state

    @property
    def session_id(self) -> SessionID:
        return self._session_id

    @property
    def state(self) -> SessionState:
        """Current session state, reconstructed from events."""
        if self._state is None:
            msg = "Session state not loaded. Call load() or use create()."
            raise RuntimeError(msg)
        return self._state

    # ─── Factory Methods ──────────────────────────────────────────

    @classmethod
    async def create(
        cls,
        event_store: EventStore,
        model: str,
        provider: str = "openai",
        title: str = "",
        agent: str = "auto",
    ) -> SessionV2:
        """Create a new session by appending a session.created event."""
        session_id = SessionID(str(time.time_ns()))
        now = time.time()
        events = [
            {
                "type": "session.created",
                "data": {
                    "title": title,
                    "provider": provider,
                    "model": model,
                    "agent": agent,
                },
            }
        ]
        stored = await event_store.append(session_id, events)

        logger.info(
            "Session created: id=%s model=%s provider=%s agent=%s",
            session_id, model, provider, agent,
        )

        state = SessionState(
            session_id=session_id,
            title=title,
            provider=provider,
            model=model,
            agent=agent,
            status="active",
            created_at=now,
            updated_at=now,
            seq=stored[-1].seq if stored else 0,
        )
        return cls(event_store, session_id, state)

    @classmethod
    async def load(cls, event_store: EventStore, session_id: SessionID) -> SessionV2:
        """Load an existing session by replaying all its events."""
        events = await event_store.read(session_id)
        logger.info("Session loaded: id=%s events=%d", session_id, len(events))
        state = SessionProjector.project(events)
        return cls(event_store, session_id, state)

    # ─── Mutations ────────────────────────────────────────────────

    async def prompt(self, user_input: str) -> list[Event]:
        """Append a user prompt event. Non-blocking."""
        logger.debug("Prompt admitted: len=%d preview=%s", len(user_input), user_input[:80])
        events = await self._event_store.append(
            self._session_id,
            [{"type": "prompt.admitted", "data": {"prompt": user_input}}],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return events

    async def add_text(self, content: str) -> list[Event]:
        """Append a text completion event (assistant response)."""
        logger.debug("Text added: len=%d", len(content))
        events = await self._event_store.append(
            self._session_id,
            [{"type": "text.ended", "data": {"content": content}}],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return events

    async def add_tool_call(
        self, name: str, args: dict[str, object]
    ) -> list[Event]:
        """Append a tool.called event."""
        logger.debug("Tool call: %s round=%d", name, self.state.tool_rounds + 1)
        events = await self._event_store.append(
            self._session_id,
            [
                {
                    "type": "tool.called",
                    "data": {"name": name, "args": args, "round": self.state.tool_rounds + 1},
                }
            ],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return events

    async def update_metadata(
        self, title: str | None = None, model: str | None = None, agent: str | None = None
    ) -> list[Event]:
        """Update session metadata."""
        data: dict[str, object] = {}
        if title is not None:
            data["title"] = title
        if model is not None:
            data["model"] = model
        if agent is not None:
            data["agent"] = agent
        if not data:
            logger.debug("update_metadata: no changes for session=%s", self._session_id)
            return []
        logger.debug("Metadata updated: session=%s keys=%s", self._session_id, list(data.keys()))
        events = await self._event_store.append(
            self._session_id,
            [{"type": "session.updated", "data": data}],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return events

    async def delete(self) -> list[Event]:
        """Mark the session as deleted."""
        logger.info("Session deleted: id=%s", self._session_id)
        events = await self._event_store.append(
            self._session_id,
            [{"type": "session.deleted", "data": {}}],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return events

    async def refresh(self) -> None:
        """Reload state from the event store."""
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )

    def __repr__(self) -> str:
        return (
            f"SessionV2(id={self._session_id!r}, "
            f"model={self.state.model if self._state else '?'}, "
            f"messages={len(self.state.messages) if self._state else 0})"
        )
