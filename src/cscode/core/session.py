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

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from cscode.schema.ids import SessionID
from cscode.schema.messages import Message, MessageRole, TextPart
from cscode.storage.event_store import Event, EventStore
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class EventLock:
    """Per-session lock with try_acquire() for Python <3.13 compatibility.

    Uses an asyncio.Event-based waiter queue so that concurrent
    acquire() calls are queued and woken in FIFO order.
    """

    def __init__(self) -> None:
        self._locked = False
        self._waiters: list[asyncio.Event] = []

    async def acquire(self) -> bool:
        while self._locked:
            evt = asyncio.Event()
            self._waiters.append(evt)
            await evt.wait()
        self._locked = True
        return True

    def try_acquire(self) -> bool:
        if self._locked:
            return False
        self._locked = True
        return True

    def release(self) -> None:
        self._locked = False
        if self._waiters:
            self._waiters.pop(0).set()

    @property
    def locked(self) -> bool:
        return self._locked


class SessionLockManager:
    """Manages per-session EventLocks for concurrency control.

    Usage:
        if not await SessionLockManager.try_lock(session_id):
            # Session is already processing — reject
            return
        try:
            # ... process ...
        finally:
            SessionLockManager.unlock(session_id)
    """

    _locks: dict[str, EventLock] = {}
    _dict_lock = asyncio.Lock()

    @classmethod
    async def try_lock(cls, session_id: str) -> bool:
        async with cls._dict_lock:
            if session_id not in cls._locks:
                cls._locks[session_id] = EventLock()
        return cls._locks[session_id].try_acquire()

    @classmethod
    def unlock(cls, session_id: str) -> None:
        lock = cls._locks.get(session_id)
        if lock is not None:
            lock.release()

    @classmethod
    def cleanup(cls, session_id: str) -> None:
        """Remove the lock entry for an idle session."""
        cls._locks.pop(session_id, None)


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
    workspace_id: str = ""
    """Associated workspace id (empty = not associated)."""
    instruction: str = ""
    """Per-session custom instruction injected into system prompt."""
    run_status: str = "idle"
    """Execution run status: idle, running, stopped, errored, completed."""
    run_error: str = ""
    """Error message when run_status is 'errored'."""
    reminders: list[dict[str, object]] = field(default_factory=list)
    """Per-session reminders (event-sourced)."""


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

                case "session.workspace.associated":
                    state.workspace_id = str(event.data.get("workspace_id", ""))

                case "session.workspace.moved":
                    state.workspace_id = str(event.data.get("to_workspace_id", ""))

                case "instruction.set":
                    state.instruction = str(event.data.get("instruction", ""))

                case "instruction.deleted":
                    state.instruction = ""

                case "session.run_started":
                    state.run_status = "running"
                    state.run_error = ""

                case "session.run_stopped":
                    state.run_status = "stopped"

                case "session.run_errored":
                    state.run_status = "errored"
                    state.run_error = str(event.data.get("error", ""))

                case "session.run_completed":
                    state.run_status = "completed"
                    state.run_error = ""

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

                case "session.reminder_added":
                    reminder_data = {
                        "id": event.data.get("id", ""),
                        "text": event.data.get("text", ""),
                        "created_at": event.created_at,
                    }
                    # Use a list-compatible approach for the frozen state
                    state.reminders = [*state.reminders, reminder_data]

                case _:
                    logger.warning("Unknown event type in projection: %s", event.type)

        state.messages = tuple(messages)
        return state

    @staticmethod
    def build_context(state: SessionState) -> list[Message]:
        """Build the LLM context message list from session state.

        If the session has a custom instruction, it is injected as the
        first system message.

        Returns messages suitable for passing to LLMClient.generate/stream.
        """
        messages = list(state.messages)
        if state.instruction:
            messages.insert(0, Message.system(state.instruction))
        return messages


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
        workspace_id: str = "",
    ) -> SessionV2:
        """Create a new session by appending a session.created event."""
        session_id = SessionID(str(time.time_ns()))
        now = time.time()
        events: list[dict[str, Any]] = [
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
        if workspace_id:
            events.append({
                "type": "session.workspace.associated",
                "data": {"workspace_id": workspace_id},
            })

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
            workspace_id=workspace_id,
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

    async def associate_workspace(self, workspace_id: str) -> SessionState:
        """Associate this session with a workspace.

        Args:
            workspace_id: The workspace ID to associate with.
                         Must be non-empty.

        Returns:
            The updated SessionState.

        Raises:
            ValueError: If workspace_id is empty.
        """
        if not workspace_id:
            raise ValueError("workspace_id must be non-empty")

        await self._event_store.append(
            self._session_id,
            [{
                "type": "session.workspace.associated",
                "data": {"workspace_id": workspace_id},
            }],
        )
        logger.info(
            "Session workspace associated: id=%s workspace=%s",
            self._session_id, workspace_id,
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return self._state

    async def move_workspace(self, to_workspace_id: str) -> SessionState:
        """Move this session to a different workspace.

        Returns the updated SessionState.
        """
        from_ws = self.state.workspace_id
        await self._event_store.append(
            self._session_id,
            [{
                "type": "session.workspace.moved",
                "data": {
                    "from_workspace_id": from_ws,
                    "to_workspace_id": to_workspace_id,
                },
            }],
        )
        logger.info(
            "Session workspace moved: id=%s from=%s to=%s",
            self._session_id, from_ws, to_workspace_id,
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return self._state

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

    async def set_instruction(self, instruction: str) -> list[Event]:
        """Set or update the per-session custom instruction.

        Appends an instruction.set event. The instruction will be
        injected as a system message in build_context().

        Args:
            instruction: The instruction text. Empty string removes it.
        """
        logger.debug(
            "Set instruction: session=%s len=%d",
            self._session_id, len(instruction),
        )
        events = await self._event_store.append(
            self._session_id,
            [{"type": "instruction.set", "data": {"instruction": instruction}}],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return events

    async def delete_instruction(self) -> list[Event]:
        """Remove the per-session custom instruction.

        Appends an instruction.deleted event.
        """
        logger.debug("Delete instruction: session=%s", self._session_id)
        events = await self._event_store.append(
            self._session_id,
            [{"type": "instruction.deleted", "data": {}}],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return events

    async def mark_run_start(self) -> list[Event]:
        """Mark the session as currently running an LLM execution."""
        logger.debug("Run start: session=%s", self._session_id)
        events = await self._event_store.append(
            self._session_id,
            [{"type": "session.run_started", "data": {}}],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return events

    async def mark_run_stop(self) -> list[Event]:
        """Mark the session run as stopped (user interruption)."""
        logger.debug("Run stop: session=%s", self._session_id)
        events = await self._event_store.append(
            self._session_id,
            [{"type": "session.run_stopped", "data": {}}],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return events

    async def mark_run_error(self, error: str = "") -> list[Event]:
        """Mark the session run as errored."""
        logger.debug("Run error: session=%s error=%s", self._session_id, error[:80])
        events = await self._event_store.append(
            self._session_id,
            [{"type": "session.run_errored", "data": {"error": error}}],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return events

    async def mark_run_complete(self) -> list[Event]:
        """Mark the session run as completed successfully."""
        logger.debug("Run complete: session=%s", self._session_id)
        events = await self._event_store.append(
            self._session_id,
            [{"type": "session.run_completed", "data": {}}],
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

    def check_overflow(self, threshold: int = 100) -> dict[str, bool | int]:
        """P2-12: Check if this session is overflowing (too many messages).

        Returns:
            dict with keys:
                overflowing (bool): message_count >= threshold
                near_overflow (bool): message_count >= threshold * 0.8
                message_count (int): current number of messages
                threshold (int): the threshold used
        """
        msg_count = len(self.state.messages)
        near_threshold = int(threshold * 0.8)
        return {
            "overflowing": msg_count >= threshold,
            "near_overflow": msg_count >= near_threshold,
            "message_count": msg_count,
            "threshold": threshold,
        }

    def get_last_prompt(self) -> str | None:
        """P2-13: Return the last user prompt text, or None if empty/not a prompt."""
        for msg in reversed(self.state.messages):
            if msg.role == MessageRole.USER:
                parts = msg.parts
                if parts and hasattr(parts[0], "text"):
                    return parts[0].text
                return None
        return None

    async def retry(self) -> list[Event]:
        """P2-13: Re-submit the last user prompt.

        Calls get_last_prompt() and if a prompt exists, appends a new
        prompt.admitted event with the same content.

        Returns:
            The stored events, or an empty list if no prompt to retry.
        """
        last = self.get_last_prompt()
        if last is None:
            return []
        return await self.prompt(last)

    async def add_reminder(self, text: str) -> dict[str, object]:
        """P2-14: Add a reminder note to this session.

        Args:
            text: The reminder text.

        Returns:
            The reminder dict with id, text, created_at.
        """
        reminder_id = f"rem_{time.time_ns()}"
        events = await self._event_store.append(
            self._session_id,
            [{"type": "session.reminder_added", "data": {"id": reminder_id, "text": text}}],
        )
        self._state = SessionProjector.project(
            await self._event_store.read(self._session_id)
        )
        return {
            "id": reminder_id,
            "text": text,
            "created_at": events[-1].created_at,
        }

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
