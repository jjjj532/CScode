"""Tests for P0-3: Session Input Inbox — event-sourced input queue.

Tests cover:
- InputInbox projection from events
- enqueue/dequeue/cancel/clear lifecycle
- Edge cases: empty content, empty queue, duplicate IDs
- Persistence through reload
"""

from __future__ import annotations

import time

import pytest

from cscode.core.session_input import InputInbox, QueuedInput
from cscode.storage.db import Database
from cscode.storage.event_store import Event, EventStore


@pytest.fixture
async def event_store() -> EventStore:
    db = Database(":memory:")
    await db.init()
    return EventStore(db)


# ─── Projection Tests ───────────────────────────────────────────────


class TestInputInboxProjection:
    """Verify event → InputInboxState reconstruction."""

    def test_empty_events(self) -> None:
        """No events → empty pending queue."""
        inbox = InputInbox(EventStore(Database(":memory:")), "sess_001")  # not used for static project
        state = InputInbox.project([])
        assert len(state.pending) == 0
        assert state.processing_id is None

    def test_queued_adds_to_pending(self) -> None:
        """input.queued adds a new QueuedInput to pending."""
        events = [
            Event("sess_001", 1, "input.queued",
                  {"id": "inp_001", "content": "Hello", "files": []}, 100.0),
        ]
        state = InputInbox.project(events)
        assert len(state.pending) == 1
        assert state.pending[0].id == "inp_001"
        assert state.pending[0].content == "Hello"
        assert state.pending[0].files == ()

    def test_multiple_inputs_fifo(self) -> None:
        """Multiple queued inputs maintain FIFO order."""
        events = [
            Event("sess_001", 1, "input.queued",
                  {"id": "inp_1", "content": "First", "files": []}, 100.0),
            Event("sess_001", 2, "input.queued",
                  {"id": "inp_2", "content": "Second", "files": []}, 101.0),
            Event("sess_001", 3, "input.queued",
                  {"id": "inp_3", "content": "Third", "files": []}, 102.0),
        ]
        state = InputInbox.project(events)
        assert len(state.pending) == 3
        assert [p.id for p in state.pending] == ["inp_1", "inp_2", "inp_3"]

    def test_dequeue_removes_and_sets_processing(self) -> None:
        """input.dequeued removes from pending and sets processing_id."""
        events = [
            Event("sess_001", 1, "input.queued",
                  {"id": "inp_1", "content": "A", "files": []}, 100.0),
            Event("sess_001", 2, "input.queued",
                  {"id": "inp_2", "content": "B", "files": []}, 101.0),
            Event("sess_001", 3, "input.dequeued", {"id": "inp_1"}, 102.0),
        ]
        state = InputInbox.project(events)
        assert len(state.pending) == 1
        assert state.pending[0].id == "inp_2"
        assert state.processing_id == "inp_1"

    def test_processed_clears_processing(self) -> None:
        """input.processed clears the processing_id."""
        events = [
            Event("sess_001", 1, "input.queued",
                  {"id": "inp_1", "content": "A", "files": []}, 100.0),
            Event("sess_001", 2, "input.dequeued", {"id": "inp_1"}, 101.0),
            Event("sess_001", 3, "input.processed", {"id": "inp_1"}, 102.0),
        ]
        state = InputInbox.project(events)
        assert state.processing_id is None
        assert len(state.pending) == 0

    def test_cancel_removes_specific_input(self) -> None:
        """input.cancelled removes a specific pending input by ID."""
        events = [
            Event("sess_001", 1, "input.queued",
                  {"id": "inp_1", "content": "A", "files": []}, 100.0),
            Event("sess_001", 2, "input.queued",
                  {"id": "inp_2", "content": "B", "files": []}, 101.0),
            Event("sess_001", 3, "input.cancelled", {"id": "inp_1"}, 102.0),
        ]
        state = InputInbox.project(events)
        assert len(state.pending) == 1
        assert state.pending[0].id == "inp_2"

    def test_cancel_nonexistent_ignored(self) -> None:
        """Cancelling a non-existent input should not affect pending."""
        events = [
            Event("sess_001", 1, "input.queued",
                  {"id": "inp_1", "content": "A", "files": []}, 100.0),
            Event("sess_001", 2, "input.cancelled", {"id": "inp_nonexistent"}, 101.0),
        ]
        state = InputInbox.project(events)
        assert len(state.pending) == 1

    def test_clear_removes_all_pending(self) -> None:
        """input.cleared empties the pending queue."""
        events = [
            Event("sess_001", 1, "input.queued",
                  {"id": "inp_1", "content": "A", "files": []}, 100.0),
            Event("sess_001", 2, "input.queued",
                  {"id": "inp_2", "content": "B", "files": []}, 101.0),
            Event("sess_001", 3, "input.cleared", {}, 102.0),
        ]
        state = InputInbox.project(events)
        assert len(state.pending) == 0

    def test_queued_with_files(self) -> None:
        """input.queued can include file attachments."""
        events = [
            Event("sess_001", 1, "input.queued",
                  {"id": "inp_1", "content": "Check this", "files": ["/tmp/a.py", "/tmp/b.py"]},
                  100.0),
        ]
        state = InputInbox.project(events)
        assert len(state.pending) == 1
        assert state.pending[0].files == ("/tmp/a.py", "/tmp/b.py")

    def test_seq_tracks_latest(self) -> None:
        """State.seq reflects latest event seq."""
        events = [
            Event("sess_001", 1, "input.queued",
                  {"id": "inp_1", "content": "A", "files": []}, 100.0),
            Event("sess_001", 5, "input.queued",
                  {"id": "inp_2", "content": "B", "files": []}, 101.0),
        ]
        state = InputInbox.project(events)
        assert state.seq == 5

    def test_non_input_events_ignored(self) -> None:
        """Non-input events are skipped during projection."""
        events = [
            Event("sess_001", 1, "session.created",
                  {"title": "Test", "provider": "openai", "model": "gpt-4o", "agent": "auto"}, 100.0),
            Event("sess_001", 2, "input.queued",
                  {"id": "inp_1", "content": "Hello", "files": []}, 101.0),
            Event("sess_001", 3, "prompt.admitted", {"prompt": "Hello"}, 102.0),
        ]
        state = InputInbox.project(events)
        assert len(state.pending) == 1
        assert state.pending[0].content == "Hello"


# ─── InputInbox Methods ────────────────────────────────────────────


class TestInputInboxMethods:
    """Test enqueue/dequeue/cancel/clear with real EventStore."""

    @pytest.mark.asyncio
    async def test_enqueue(self, event_store: EventStore) -> None:
        """enqueue() appends input.queued event and updates state."""
        inbox = InputInbox(event_store, "sess_001")
        inp = await inbox.enqueue("Hello, world!")
        assert inp.id is not None
        assert inp.content == "Hello, world!"
        assert len(inbox.state.pending) == 1
        assert inp.id == inbox.state.pending[0].id

    @pytest.mark.asyncio
    async def test_enqueue_empty_raises(self, event_store: EventStore) -> None:
        """enqueue() with empty/whitespace content raises ValueError."""
        inbox = InputInbox(event_store, "sess_001")
        with pytest.raises(ValueError, match="empty"):
            await inbox.enqueue("")
        with pytest.raises(ValueError, match="empty"):
            await inbox.enqueue("   ")

    @pytest.mark.asyncio
    async def test_enqueue_with_files(self, event_store: EventStore) -> None:
        """enqueue() with file attachments."""
        inbox = InputInbox(event_store, "sess_001")
        inp = await inbox.enqueue("Check this", files=["/tmp/a.py"])
        assert inp.files == ("/tmp/a.py",)
        assert len(inbox.state.pending) == 1

    @pytest.mark.asyncio
    async def test_enqueue_multiple(self, event_store: EventStore) -> None:
        """Multiple enqueues maintain order."""
        inbox = InputInbox(event_store, "sess_001")
        inp1 = await inbox.enqueue("First")
        inp2 = await inbox.enqueue("Second")
        inp3 = await inbox.enqueue("Third")
        assert [p.id for p in inbox.state.pending] == [inp1.id, inp2.id, inp3.id]

    @pytest.mark.asyncio
    async def test_dequeue(self, event_store: EventStore) -> None:
        """dequeue() returns first pending input and updates state."""
        inbox = InputInbox(event_store, "sess_001")
        await inbox.enqueue("First")
        await inbox.enqueue("Second")

        dequeued = await inbox.dequeue()
        assert dequeued is not None
        assert dequeued.content == "First"
        # Should be removed from pending, set as processing
        assert len(inbox.state.pending) == 1
        assert inbox.state.pending[0].content == "Second"
        assert inbox.state.processing_id == dequeued.id

    @pytest.mark.asyncio
    async def test_dequeue_empty_returns_none(self, event_store: EventStore) -> None:
        """dequeue() on empty inbox returns None."""
        inbox = InputInbox(event_store, "sess_001")
        result = await inbox.dequeue()
        assert result is None

    @pytest.mark.asyncio
    async def test_mark_processed(self, event_store: EventStore) -> None:
        """mark_processed() clears processing_id."""
        inbox = InputInbox(event_store, "sess_001")
        inp = await inbox.enqueue("Hello")
        await inbox.dequeue()
        assert inbox.state.processing_id == inp.id

        await inbox.mark_processed(inp.id)
        assert inbox.state.processing_id is None

    @pytest.mark.asyncio
    async def test_mark_processed_nonexistent_not_fails(self, event_store: EventStore) -> None:
        """mark_processed() with unknown ID is a no-op."""
        inbox = InputInbox(event_store, "sess_001")
        await inbox.mark_processed("nonexistent")  # Should not raise

    @pytest.mark.asyncio
    async def test_cancel(self, event_store: EventStore) -> None:
        """cancel() removes a pending input."""
        inbox = InputInbox(event_store, "sess_001")
        inp1 = await inbox.enqueue("First")
        await inbox.enqueue("Second")

        result = await inbox.cancel(inp1.id)
        assert result is True
        assert len(inbox.state.pending) == 1
        assert inbox.state.pending[0].content == "Second"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, event_store: EventStore) -> None:
        """cancel() with unknown ID returns False."""
        inbox = InputInbox(event_store, "sess_001")
        await inbox.enqueue("Hello")
        result = await inbox.cancel("inp_nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_processing_input(self, event_store: EventStore) -> None:
        """cancel() on a dequeued/processing input is a no-op (returns False)."""
        inbox = InputInbox(event_store, "sess_001")
        inp = await inbox.enqueue("Hello")
        await inbox.dequeue()

        result = await inbox.cancel(inp.id)
        assert result is False  # Not in pending anymore
        assert inbox.state.processing_id == inp.id  # Still processing

    @pytest.mark.asyncio
    async def test_clear(self, event_store: EventStore) -> None:
        """clear() removes all pending inputs."""
        inbox = InputInbox(event_store, "sess_001")
        await inbox.enqueue("First")
        await inbox.enqueue("Second")
        await inbox.enqueue("Third")

        cleared = await inbox.clear()
        assert cleared == 3
        assert len(inbox.state.pending) == 0

    @pytest.mark.asyncio
    async def test_clear_empty(self, event_store: EventStore) -> None:
        """clear() on empty inbox returns 0."""
        inbox = InputInbox(event_store, "sess_001")
        cleared = await inbox.clear()
        assert cleared == 0

    @pytest.mark.asyncio
    async def test_persistence(self, event_store: EventStore) -> None:
        """Inbox state persists across EventStore reload."""
        inbox1 = InputInbox(event_store, "sess_001")
        await inbox1.enqueue("Hello")
        await inbox1.enqueue("World")

        # New instance loading same aggregate
        inbox2 = InputInbox(event_store, "sess_001")
        await inbox2.reload()
        assert len(inbox2.state.pending) == 2
        assert inbox2.state.pending[0].content == "Hello"
        assert inbox2.state.pending[1].content == "World"

    @pytest.mark.asyncio
    async def test_enqueue_different_aggregates_isolated(self, event_store: EventStore) -> None:
        """Inputs for different sessions are isolated."""
        inbox_a = InputInbox(event_store, "sess_a")
        inbox_b = InputInbox(event_store, "sess_b")
        await inbox_a.enqueue("A only")
        await inbox_b.enqueue("B only")

        assert len(inbox_a.state.pending) == 1
        assert inbox_a.state.pending[0].content == "A only"
        assert len(inbox_b.state.pending) == 1
        assert inbox_b.state.pending[0].content == "B only"
