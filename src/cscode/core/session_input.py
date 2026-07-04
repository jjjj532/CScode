"""P0-3: Session Input Inbox — event-sourced input queue.

Provides an InputInbox that decouples input submission from LLM processing.
Inputs are queued as events, enabling non-blocking enqueue during LLM streams.

Events:
    input.queued — adds a new input to the pending queue
    input.dequeued — pops from pending, sets as processing
    input.processed — clears the processing slot
    input.cancelled — removes a specific pending input
    input.cleared — empties all pending inputs
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from cscode.storage.event_store import Event, EventStore
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class QueuedInput:
    """A single queued input waiting to be processed."""

    id: str
    content: str
    files: tuple[str, ...] = ()
    created_at: float = 0.0


@dataclass
class InputInboxState:
    """Reconstructed state of the inbox from its event stream."""

    pending: tuple[QueuedInput, ...] = ()
    processing_id: str | None = None
    seq: int = 0


class InputInbox:
    """Event-sourced input queue for a session.

    Uses the same EventStore as the session it belongs to, sharing the
    session's aggregate_id. All mutations append events and rebuild
    state by projection.

    Usage:
        inbox = InputInbox(event_store, aggregate_id)
        inp = await inbox.enqueue("Hello")
        next_inp = await inbox.dequeue()
        await inbox.mark_processed(inp.id)
    """

    def __init__(self, event_store: EventStore, aggregate_id: str) -> None:
        self._event_store = event_store
        self._aggregate_id = aggregate_id
        self._state = InputInboxState()

    @property
    def state(self) -> InputInboxState:
        return self._state

    # ─── Projection ─────────────────────────────────────────────────

    @staticmethod
    def project(events: list[Event]) -> InputInboxState:
        """Reconstruct InputInboxState from a list of events.

        Only processes event types with the 'input.' prefix; all other
        events (session.created, prompt.admitted, etc.) are ignored.
        """
        pending: list[QueuedInput] = []
        processing_id: str | None = None
        seq = 0

        for event in events:
            seq = event.seq

            match event.type:
                case "input.queued":
                    d = event.data
                    pending.append(QueuedInput(
                        id=str(d["id"]),
                        content=str(d["content"]),
                        files=tuple(str(f) for f in d.get("files", [])),
                        created_at=event.created_at,
                    ))

                case "input.dequeued":
                    input_id = str(event.data["id"])
                    pending = [p for p in pending if p.id != input_id]
                    processing_id = input_id

                case "input.processed":
                    processing_id = None

                case "input.cancelled":
                    input_id = str(event.data["id"])
                    pending = [p for p in pending if p.id != input_id]

                case "input.cleared":
                    pending = []

                case _:
                    # Non-input events are ignored
                    pass

        return InputInboxState(
            pending=tuple(pending),
            processing_id=processing_id,
            seq=seq,
        )

    # ─── Persistence ─────────────────────────────────────────────────

    async def reload(self) -> None:
        """Reload state from the event store."""
        events = await self._event_store.read(self._aggregate_id)
        self._state = self.project(events)
        logger.debug(
            "Inbox reloaded: aggregate=%s pending=%d seq=%d",
            self._aggregate_id, len(self._state.pending), self._state.seq,
        )

    # ─── Mutations ───────────────────────────────────────────────────

    async def enqueue(
        self, content: str, files: list[str] | None = None,
    ) -> QueuedInput:
        """Add a new input to the pending queue.

        Args:
            content: The input text. Must be non-empty after stripping.
            files: Optional list of file paths attached to this input.

        Returns:
            The newly created QueuedInput.

        Raises:
            ValueError: If content is empty or whitespace-only.
        """
        if not content.strip():
            msg = "Input content cannot be empty"
            raise ValueError(msg)

        input_id = f"inp_{uuid.uuid4().hex[:12]}"
        now = time.time()

        logger.debug(
            "Enqueue input: aggregate=%s id=%s content_len=%d",
            self._aggregate_id, input_id, len(content),
        )

        await self._event_store.append(self._aggregate_id, [
            {
                "type": "input.queued",
                "data": {
                    "id": input_id,
                    "content": content,
                    "files": files or [],
                },
            },
        ])
        await self.reload()

        return QueuedInput(
            id=input_id,
            content=content,
            files=tuple(files or []),
            created_at=now,
        )

    async def dequeue(self) -> QueuedInput | None:
        """Pop the next pending input and mark it as processing.

        Returns:
            The dequeued input, or None if the queue is empty.
        """
        if not self._state.pending:
            logger.debug("Dequeue: aggregate=%s queue empty", self._aggregate_id)
            return None

        inp = self._state.pending[0]
        logger.debug(
            "Dequeue input: aggregate=%s id=%s content=%s",
            self._aggregate_id, inp.id, inp.content[:60],
        )

        await self._event_store.append(self._aggregate_id, [
            {"type": "input.dequeued", "data": {"id": inp.id}},
        ])
        await self.reload()
        return inp

    async def mark_processed(self, input_id: str) -> None:
        """Mark a dequeued input as fully processed.

        Clears the processing_id slot so the next input can be dequeued.

        Args:
            input_id: The ID of the input that finished processing.
        """
        logger.debug(
            "Mark processed: aggregate=%s id=%s",
            self._aggregate_id, input_id,
        )
        await self._event_store.append(self._aggregate_id, [
            {"type": "input.processed", "data": {"id": input_id}},
        ])
        await self.reload()

    async def cancel(self, input_id: str) -> bool:
        """Cancel a pending input by ID.

        Has no effect if the input is already being processed (dequeued)
        or does not exist.

        Returns:
            True if a pending input was cancelled, False otherwise.
        """
        if not any(p.id == input_id for p in self._state.pending):
            logger.debug(
                "Cancel skipped: aggregate=%s id=%s not in pending",
                self._aggregate_id, input_id,
            )
            return False

        logger.debug(
            "Cancel input: aggregate=%s id=%s",
            self._aggregate_id, input_id,
        )
        await self._event_store.append(self._aggregate_id, [
            {"type": "input.cancelled", "data": {"id": input_id}},
        ])
        await self.reload()
        return True

    async def clear(self) -> int:
        """Clear all pending inputs.

        Returns:
            The number of pending inputs that were cleared.
        """
        count = len(self._state.pending)
        if count == 0:
            return 0

        logger.debug(
            "Clear input queue: aggregate=%s count=%d",
            self._aggregate_id, count,
        )

        await self._event_store.append(self._aggregate_id, [
            {"type": "input.cleared", "data": {}},
        ])
        await self.reload()
        return count
