"""Tests for SessionV2 revert functionality — P0-2.

Tests the session.reverted event type, projector handling,
and SessionV2.revert() method.
"""

from __future__ import annotations

import time

import pytest

from cscode.core.session import SessionProjector, SessionV2
from cscode.schema.ids import SessionID
from cscode.schema.messages import MessageRole
from cscode.storage.db import Database
from cscode.storage.event_store import Event, EventStore


@pytest.fixture
async def event_store() -> EventStore:
    db = Database(":memory:")
    await db.init()
    return EventStore(db)


@pytest.fixture
def sample_events() -> list[Event]:
    """5 events: create + 2 prompt+text pairs."""
    t = time.time()
    return [
        Event("sess_001", 1, "session.created",
              {"title": "Chat", "provider": "openai", "model": "gpt-4o", "agent": "auto"}, t),
        Event("sess_001", 2, "prompt.admitted", {"prompt": "Hello"}, t + 1),
        Event("sess_001", 3, "text.ended", {"content": "Hi there!"}, t + 2),
        Event("sess_001", 4, "prompt.admitted", {"prompt": "How are you?"}, t + 3),
        Event("sess_001", 5, "text.ended", {"content": "I'm good!"}, t + 4),
    ]


# ---------------------------------------------------------------------------
# SessionProjector: revert handling
# ---------------------------------------------------------------------------

class TestSessionProjectorRevert:
    def test_revert_truncates_messages(self, sample_events: list[Event]) -> None:
        """Revert to seq 3 should keep only first prompt+text pair."""
        events = sample_events + [
            Event("sess_001", 6, "session.reverted", {"target_seq": 3}, time.time()),
        ]
        state = SessionProjector.project(events)
        assert len(state.messages) == 2  # Hello + Hi there!
        assert state.messages[0].content == "Hello"
        assert state.messages[1].content == "Hi there!"
        assert state.seq == 6  # Latest event seq

    def test_revert_to_seq_1_clears_all_messages(self, sample_events: list[Event]) -> None:
        """Revert to seq 1 (create only) should clear all messages."""
        events = sample_events + [
            Event("sess_001", 6, "session.reverted", {"target_seq": 1}, time.time()),
        ]
        state = SessionProjector.project(events)
        assert state.messages == ()

    def test_revert_resets_tool_rounds(self) -> None:
        """Revert should reset tool_rounds counter."""
        t = time.time()
        events = [
            Event("sess_001", 1, "session.created",
                  {"title": "X", "provider": "openai", "model": "gpt-4o", "agent": "auto"}, t),
            Event("sess_001", 2, "tool.called", {"name": "Bash", "args": {}, "round": 1}, t + 1),
            Event("sess_001", 3, "tool.called", {"name": "Read", "args": {}, "round": 2}, t + 2),
            Event("sess_001", 4, "session.reverted", {"target_seq": 2}, t + 3),
        ]
        state = SessionProjector.project(events)
        # Only first tool.called (seq=2) should remain
        assert state.tool_rounds == 1

    def test_revert_and_continue(self, sample_events: list[Event]) -> None:
        """After revert, new events should be appended normally."""
        events = sample_events + [
            Event("sess_001", 6, "session.reverted", {"target_seq": 3}, time.time()),
            Event("sess_001", 7, "prompt.admitted", {"prompt": "New question"}, time.time()),
            Event("sess_001", 8, "text.ended", {"content": "New answer"}, time.time()),
        ]
        state = SessionProjector.project(events)
        # Should have 2 (original) + 2 (new) = 4 messages
        assert len(state.messages) == 4
        assert state.messages[2].content == "New question"
        assert state.messages[3].content == "New answer"

    def test_revert_twice(self, sample_events: list[Event]) -> None:
        """Multiple reverts should work correctly."""
        events = sample_events + [
            Event("sess_001", 6, "session.reverted", {"target_seq": 3}, time.time()),
            Event("sess_001", 7, "prompt.admitted", {"prompt": "Middle"}, time.time()),
            Event("sess_001", 8, "text.ended", {"content": "Middle answer"}, time.time()),
            # Revert again to seq 3 (undoing the middle Q&A)
            Event("sess_001", 9, "session.reverted", {"target_seq": 3}, time.time()),
        ]
        state = SessionProjector.project(events)
        assert len(state.messages) == 2
        assert state.messages[0].content == "Hello"

    def test_revert_nonexistent_seq_ignored(self, sample_events: list[Event]) -> None:
        """Revert with target_seq > current max should keep all messages."""
        events = sample_events + [
            Event("sess_001", 6, "session.reverted", {"target_seq": 999}, time.time()),
        ]
        state = SessionProjector.project(events)
        # All messages preserved since target is beyond current
        assert len(state.messages) == 4

    def test_revert_preserves_session_metadata(self, sample_events: list[Event]) -> None:
        """Revert should not affect session metadata (title, model, etc)."""
        events = sample_events + [
            Event("sess_001", 6, "session.reverted", {"target_seq": 3}, time.time()),
        ]
        state = SessionProjector.project(events)
        assert state.title == "Chat"
        assert state.provider == "openai"
        assert state.model == "gpt-4o"


# ---------------------------------------------------------------------------
# SessionV2.revert() method
# ---------------------------------------------------------------------------

class TestSessionV2Revert:
    async def test_revert_method(self, event_store: EventStore) -> None:
        """SessionV2.revert() should append event and update state."""
        session = await SessionV2.create(event_store, "gpt-4o")
        await session.prompt("Hello")
        await session.add_text("Hi!")
        await session.prompt("How are you?")
        await session.add_text("Good!")
        assert len(session.state.messages) == 4

        await session.revert(target_seq=3)
        assert len(session.state.messages) == 2  # Only first pair
        assert session.state.messages[0].content == "Hello"

    async def test_revert_validation_too_small(self, event_store: EventStore) -> None:
        """Revert with seq <= 0 should raise ValueError."""
        session = await SessionV2.create(event_store, "gpt-4o")
        with pytest.raises(ValueError, match="target_seq"):
            await session.revert(target_seq=0)

    async def test_revert_validation_too_large(self, event_store: EventStore) -> None:
        """Revert with seq >= current max should raise ValueError."""
        session = await SessionV2.create(event_store, "gpt-4o")
        await session.prompt("Hello")
        with pytest.raises(ValueError, match="target_seq"):
            await session.revert(target_seq=100)

    async def test_revert_persistence(self, event_store: EventStore) -> None:
        """Revert should persist across session load."""
        session = await SessionV2.create(event_store, "gpt-4o")
        await session.prompt("Hello")
        await session.add_text("Hi!")
        await session.prompt("Q2")
        await session.add_text("A2")
        assert len(session.state.messages) == 4

        await session.revert(target_seq=3)

        # Load from a new instance
        loaded = await SessionV2.load(event_store, session.session_id)
        assert len(loaded.state.messages) == 2
        assert loaded.state.messages[0].content == "Hello"

    async def test_revert_then_continue(self, event_store: EventStore) -> None:
        """After revert, new messages can be added."""
        session = await SessionV2.create(event_store, "gpt-4o")
        await session.prompt("Hello")
        await session.add_text("Hi!")
        await session.revert(target_seq=2)  # Undo the response
        assert len(session.state.messages) == 1

        await session.prompt("New question")
        await session.add_text("New answer")
        assert len(session.state.messages) == 3
        assert session.state.messages[2].content == "New answer"
