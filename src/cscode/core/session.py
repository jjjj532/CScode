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
        msg_seqs: list[int] = []
        tool_seqs: list[int] = []

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
                    msg = Message(
                        id=None,
                        role=MessageRole.USER,
                        parts=(TextPart(text=str(content)),),
                    )
                    messages.append(msg)
                    msg_seqs.append(event.seq)

                case "text.ended":
                    msg = Message(
                        id=None,
                        role=MessageRole.ASSISTANT,
                        parts=(TextPart(text=str(event.data.get("content", ""))),),
                    )
                    messages.append(msg)
                    msg_seqs.append(event.seq)

                case "tool.called":
                    state.tool_rounds += 1
                    tool_seqs.append(event.seq)

                case "session.reverted":
                    target_seq = event.data.get("target_seq", 0)
                    if target_seq > 0:
                        filtered: list[tuple[Message, int]] = [
                            (m, s) for m, s in zip(messages, msg_seqs)
                            if s <= target_seq
                        ]
                        messages = [m for m, _ in filtered]
                        msg_seqs = [s for _, s in filtered]
                        tool_seqs = [s for s in tool_seqs if s <= target_seq]
                        state.tool_rounds = len(tool_seqs)

                case "compaction":
                    baseline_seq = event.data.get("baseline_seq", 0)
                    filtered = [
                        (m, s) for m, s in zip(messages, msg_seqs)
                        if s >= baseline_seq
                    ]
                    messages = [m for m, _ in filtered]
                    msg_seqs = [s for _, s in filtered]

                case "msg.edited":
                    idx = int(event.data.get("msg_index", -1))
                    if idx < 0 or idx >= len(messages):
                        raise IndexError(
                            f"msg.edited: msg_index {idx} out of range "
                            f"(0-{len(messages) - 1})"
                        )
                    new_content = str(event.data.get("new_content", ""))
                    old = messages[idx]
                    messages[idx] = Message(
                        id=old.id,
                        role=old.role,
                        parts=(TextPart(text=new_content), *old.parts[1:]),
                    )

                case "msg.deleted":
                    idx = int(event.data.get("msg_index", -1))
                    if idx < 0 or idx >= len(messages):
                        raise IndexError(
                            f"msg.deleted: msg_index {idx} out of range "
                            f"(0-{len(messages) - 1})"
                        )
                    messages.pop(idx)
                    msg_seqs.pop(idx)

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

    async def revert(self, target_seq: int) -> list[Event]:
        """Revert session to a previous state by target event sequence.

        Appends a session.reverted event. The projector will truncate
        messages to only those with seq <= target_seq on next project.

        Args:
            target_seq: Target event sequence to revert to.
                        Must be > 0 and < current seq.

        Returns:
            The stored events.

        Raises:
            ValueError: If target_seq is out of valid range.
        """
        current_seq = self.state.seq
        if target_seq <= 0:
            msg = f"target_seq must be > 0, got {target_seq}"
            raise ValueError(msg)
        if target_seq >= current_seq:
            msg = f"target_seq ({target_seq}) must be < current seq ({current_seq})"
            raise ValueError(msg)

        logger.info(
            "Session revert: id=%s target_seq=%d current_seq=%d",
            self._session_id, target_seq, current_seq,
        )
        events = await self._event_store.append(
            self._session_id,
            [{"type": "session.reverted", "data": {"target_seq": target_seq}}],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return events

    async def edit_message(self, msg_index: int, new_content: str) -> list[Event]:
        """Edit the content of a message at the given index.

        Appends a msg.edited event. The projector will replace the
        message text while preserving the role and any non-text parts.

        Args:
            msg_index: 0-based index of the message to edit.
            new_content: Replacement text content (must be non-empty).

        Returns:
            The stored events.

        Raises:
            IndexError: If msg_index is out of range.
            ValueError: If new_content is empty.
        """
        if not new_content.strip():
            msg = "new_content must not be empty"
            raise ValueError(msg)
        n = len(self.state.messages)
        if msg_index < 0 or msg_index >= n:
            raise IndexError(
                f"edit_message: msg_index {msg_index} out of range "
                f"(0-{n - 1})"
            )
        logger.debug(
            "Edit message: session=%s msg_index=%d",
            self._session_id, msg_index,
        )
        events = await self._event_store.append(
            self._session_id,
            [{
                "type": "msg.edited",
                "data": {"msg_index": msg_index, "new_content": new_content},
            }],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return events

    async def delete_message(self, msg_index: int) -> list[Event]:
        """Delete a message at the given index.

        Appends a msg.deleted event. The projector will remove the
        message from the list. Subsequent messages shift down.

        Args:
            msg_index: 0-based index of the message to delete.

        Returns:
            The stored events.

        Raises:
            IndexError: If msg_index is out of range.
        """
        n = len(self.state.messages)
        if msg_index < 0 or msg_index >= n:
            raise IndexError(
                f"delete_message: msg_index {msg_index} out of range "
                f"(0-{n - 1})"
            )
        logger.debug(
            "Delete message: session=%s msg_index=%d",
            self._session_id, msg_index,
        )
        events = await self._event_store.append(
            self._session_id,
            [{
                "type": "msg.deleted",
                "data": {"msg_index": msg_index},
            }],
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
