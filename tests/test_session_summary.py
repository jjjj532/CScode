"""Tests for Session Summary — P1-8.

Tests SessionSummary class for generating session summaries.
"""

from __future__ import annotations

import pytest

from cscode.core.session import SessionV2
from cscode.core.session_summary import SessionSummary
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore


@pytest.fixture
async def event_store() -> EventStore:
    db = Database(":memory:")
    await db.init()
    return EventStore(db)


class TestSessionSummary:
    async def test_empty_session_summary(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", "openai", title="Test Chat")
        summary = SessionSummary(session)
        result = summary.generate()
        assert result["session_id"] == str(session.session_id)
        assert result["title"] == "Test Chat"
        assert result["message_count"] == 0
        assert result["tool_call_count"] == 0
        assert result["character_count"] == 0
        assert result["word_count"] == 0

    async def test_single_message_summary(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("Hello, world!")
        summary = SessionSummary(session)
        result = summary.generate()
        assert result["message_count"] == 1
        assert result["user_message_count"] == 1
        assert result["assistant_message_count"] == 0
        assert result["word_count"] > 0
        assert result["character_count"] > 0

    async def test_multiple_messages(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("What is Python?")
        await session.add_text("Python is a programming language.")
        await session.prompt("Thanks!")
        await session.add_text("You're welcome!")
        summary = SessionSummary(session)
        result = summary.generate()
        assert result["message_count"] == 4
        assert result["user_message_count"] == 2
        assert result["assistant_message_count"] == 2
        assert result["first_message_preview"] == "What is Python?"
        assert "Thanks" in result["last_message_preview"] or "You're" in result["last_message_preview"]

    async def test_preview_truncation(self, event_store: EventStore) -> None:
        long_text = "A" * 500
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt(long_text)
        summary = SessionSummary(session)
        result = summary.generate()
        preview = result["first_message_preview"]
        assert len(preview) <= 200
        assert preview.endswith("...")

    async def test_duration(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("Hello")
        await session.add_text("Hi")
        summary = SessionSummary(session)
        result = summary.generate()
        assert "duration_seconds" in result
        assert isinstance(result["duration_seconds"], float)
        assert result["duration_seconds"] >= 0

    async def test_summary_after_delete_message(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("First")
        await session.add_text("Response")
        await session.prompt("Second")
        await session.add_text("Response 2")
        await session.delete_message(1)  # Remove "Response"
        summary = SessionSummary(session)
        result = summary.generate()
        assert result["message_count"] == 3
        assert result["assistant_message_count"] == 1

    async def test_time_ordering(self, event_store: EventStore) -> None:
        """created_at should be <= updated_at."""
        session = await SessionV2.create(event_store, "gpt-4o", "openai")
        await session.prompt("Hello")
        await session.add_text("Hi")
        summary = SessionSummary(session)
        result = summary.generate()
        assert result["created_at"] <= result["updated_at"]

    async def test_without_title(self, event_store: EventStore) -> None:
        session = await SessionV2.create(event_store, "gpt-4o", "openai", title="")
        summary = SessionSummary(session)
        result = summary.generate()
        assert "title" in result
