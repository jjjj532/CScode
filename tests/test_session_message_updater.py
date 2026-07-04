"""Tests for Session Message Updater — P1-7.

Tests msg.edited and msg.deleted event types, projector handling,
and SessionV2.edit_message() / delete_message() methods.
"""

from __future__ import annotations

import time

import pytest

from cscode.core.session import SessionProjector, SessionV2
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
    """5 events: create + 2 prompt+text pairs (4 messages)."""
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
# SessionProjector: msg.edited handling
# ---------------------------------------------------------------------------


class TestProjectorEdit:
    def test_edit_changes_message_content(self, sample_events: list[Event]) -> None:
        """Edit the first assistant message (index 1)."""
        events = sample_events + [
            Event("sess_001", 6, "msg.edited",
                  {"msg_index": 1, "new_content": "Hey, what's up?"}, time.time()),
        ]
        state = SessionProjector.project(events)
        assert len(state.messages) == 4
        msg = state.messages[1]
        assert msg.role == MessageRole.ASSISTANT
        assert msg.parts[0].text == "Hey, what's up?"

    def test_edit_last_message(self, sample_events: list[Event]) -> None:
        """Edit the last assistant message (index 3)."""
        events = sample_events + [
            Event("sess_001", 6, "msg.edited",
                  {"msg_index": 3, "new_content": "Doing great!"}, time.time()),
        ]
        state = SessionProjector.project(events)
        assert state.messages[3].parts[0].text == "Doing great!"

    def test_edit_out_of_bounds_negative(self, sample_events: list[Event]) -> None:
        """Negative msg_index should raise IndexError."""
        events = sample_events + [
            Event("sess_001", 6, "msg.edited",
                  {"msg_index": -1, "new_content": "edited"}, time.time()),
        ]
        with pytest.raises(IndexError):
            SessionProjector.project(events)

    def test_edit_out_of_bounds_too_high(self, sample_events: list[Event]) -> None:
        """Out-of-range msg_index should raise IndexError."""
        events = sample_events + [
            Event("sess_001", 6, "msg.edited",
                  {"msg_index": 10, "new_content": "edited"}, time.time()),
        ]
        with pytest.raises(IndexError):
            SessionProjector.project(events)

    def test_edit_user_message(self, sample_events: list[Event]) -> None:
        """Edit a user message (index 0)."""
        events = sample_events + [
            Event("sess_001", 6, "msg.edited",
                  {"msg_index": 0, "new_content": "Hey!"}, time.time()),
        ]
        state = SessionProjector.project(events)
        msg = state.messages[0]
        assert msg.role == MessageRole.USER
        assert msg.parts[0].text == "Hey!"

    def test_multiple_edits(self, sample_events: list[Event]) -> None:
        """Edit the same message twice — the second edit should win."""
        events = sample_events + [
            Event("sess_001", 6, "msg.edited",
                  {"msg_index": 1, "new_content": "First edit"}, time.time()),
            Event("sess_001", 7, "msg.edited",
                  {"msg_index": 1, "new_content": "Second edit"}, time.time()),
        ]
        state = SessionProjector.project(events)
        assert state.messages[1].parts[0].text == "Second edit"


# ---------------------------------------------------------------------------
# SessionProjector: msg.deleted handling
# ---------------------------------------------------------------------------


class TestProjectorDelete:
    def test_delete_message(self, sample_events: list[Event]) -> None:
        """Delete the first assistant message (index 1) — 3 remaining."""
        events = sample_events + [
            Event("sess_001", 6, "msg.deleted", {"msg_index": 1}, time.time()),
        ]
        state = SessionProjector.project(events)
        assert len(state.messages) == 3
        assert state.messages[1].parts[0].text == "How are you?"

    def test_delete_first_message(self, sample_events: list[Event]) -> None:
        """Delete user message at index 0."""
        events = sample_events + [
            Event("sess_001", 6, "msg.deleted", {"msg_index": 0}, time.time()),
        ]
        state = SessionProjector.project(events)
        assert len(state.messages) == 3
        assert state.messages[0].role == MessageRole.ASSISTANT
        assert state.messages[0].parts[0].text == "Hi there!"

    def test_delete_last_message(self, sample_events: list[Event]) -> None:
        """Delete the last message (index 3)."""
        events = sample_events + [
            Event("sess_001", 6, "msg.deleted", {"msg_index": 3}, time.time()),
        ]
        state = SessionProjector.project(events)
        assert len(state.messages) == 3
        assert state.messages[2].parts[0].text == "How are you?"

    def test_delete_out_of_bounds(self, sample_events: list[Event]) -> None:
        """Out-of-range msg_index should raise IndexError."""
        events = sample_events + [
            Event("sess_001", 6, "msg.deleted", {"msg_index": 10}, time.time()),
        ]
        with pytest.raises(IndexError):
            SessionProjector.project(events)

    def test_delete_multiple_then_edit(self, sample_events: list[Event]) -> None:
        """Delete index 0 and 1, then edit the remaining index 0."""
        events = sample_events + [
            Event("sess_001", 6, "msg.deleted", {"msg_index": 0}, time.time()),
            Event("sess_001", 7, "msg.deleted", {"msg_index": 0}, time.time()),
            Event("sess_001", 8, "msg.edited",
                  {"msg_index": 0, "new_content": "Updated!"}, time.time()),
        ]
        state = SessionProjector.project(events)
        assert len(state.messages) == 2
        assert state.messages[0].parts[0].text == "Updated!"


# ---------------------------------------------------------------------------
# SessionV2: edit_message and delete_message
# ---------------------------------------------------------------------------


class TestSessionV2MessageUpdater:
    async def test_edit_message(self, event_store: EventStore) -> None:
        """Create session, add messages, then edit one."""
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("Hello")
        await session.add_text("Hi there!")
        assert session.state.messages[1].parts[0].text == "Hi there!"

        await session.edit_message(1, "Hey, what's up?")
        msg = session.state.messages[1]
        assert msg.parts[0].text == "Hey, what's up?"
        assert msg.role == MessageRole.ASSISTANT  # role preserved

    async def test_edit_user_message(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("Old question")
        await session.add_text("Answer")

        await session.edit_message(0, "New question")
        assert session.state.messages[0].parts[0].text == "New question"
        assert session.state.messages[0].role == MessageRole.USER

    async def test_delete_message(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("Hello")
        await session.add_text("Hi")
        await session.prompt("How are you?")
        # Messages: [0]=USER Hello, [1]=ASSISTANT Hi, [2]=USER How are you?
        assert len(session.state.messages) == 3

        await session.delete_message(1)  # Delete assistant "Hi"
        assert len(session.state.messages) == 2
        assert session.state.messages[0].parts[0].text == "Hello"
        assert session.state.messages[1].parts[0].text == "How are you?"

    async def test_delete_preserves_other_messages(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("First")
        await session.add_text("Response 1")
        await session.prompt("Second")
        await session.add_text("Response 2")

        await session.delete_message(1)  # Delete "Response 1"
        remaining = session.state.messages
        assert len(remaining) == 3
        assert remaining[0].parts[0].text == "First"
        assert remaining[1].parts[0].text == "Second"
        assert remaining[2].parts[0].text == "Response 2"

    async def test_edit_out_of_bounds(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("Hello")
        await session.add_text("Hi")
        with pytest.raises(IndexError):
            await session.edit_message(99, "nope")

    async def test_delete_out_of_bounds(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("Hello")
        await session.add_text("Hi")
        with pytest.raises(IndexError):
            await session.delete_message(99)

    async def test_edit_with_empty_content(self, event_store: EventStore) -> None:
        """Editing with empty content should raise ValueError."""
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("Hello")
        await session.add_text("Hi")
        with pytest.raises(ValueError, match="empty"):
            await session.edit_message(1, "")

    async def test_edit_and_delete_persist_across_load(self, event_store: EventStore) -> None:
        """Edit/delete operations should survive session reload."""
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("Hello")
        await session.add_text("Original")
        await session.edit_message(1, "Edited")
        await session.delete_message(0)  # Remove user greeting

        sid = session.session_id
        loaded = await SessionV2.load(event_store, sid)
        assert len(loaded.state.messages) == 1
        assert loaded.state.messages[0].parts[0].text == "Edited"

    async def test_edit_after_delete_uses_correct_index(self, event_store: EventStore) -> None:
        """After deleting msg 0, msg index 1 becomes index 0 — edit should target correctly."""
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("Hello")
        await session.add_text("Response")
        await session.prompt("Follow-up")
        await session.add_text("Follow-up response")

        # Delete the first two messages (Hello, Response)
        await session.delete_message(0)  # remove Hello
        await session.delete_message(0)  # remove Response (now at index 0)

        # Now edit the message at index 0 (should be Follow-up)
        await session.edit_message(0, "Changed follow-up")
        assert session.state.messages[0].parts[0].text == "Changed follow-up"
