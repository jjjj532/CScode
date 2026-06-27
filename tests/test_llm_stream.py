"""Tests for LLM stream — event sequence from LegacyProviderAdapter.stream()."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from cscode.llm import LegacyProviderAdapter
from cscode.providers.base import LLMProvider, LLMResult
from cscode.schema.events import (
    Finish,
    LLMEvent,
    Pending,
    TextDelta,
    TextEnded,
    TextStarted,
    ToolCallDelta,
    ToolCallEnded,
    ToolCallStarted,
    ToolResult as EventToolResult,
)
from cscode.schema.ids import ModelID
from cscode.schema.messages import Message, TextPart


class _MockStreamProvider(LLMProvider):
    """Mock provider for stream testing."""

    def __init__(self) -> None:
        super().__init__(None)  # type: ignore[arg-type]
        self._model = "mock"
        self.result: LLMResult | None = None

    def set_result(self, result: LLMResult) -> None:
        self.result = result

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        if self.result is None:
            raise RuntimeError("No result set")
        return self.result

    def stream(
        self,
        messages: list[Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        raise NotImplementedError

    def build_messages(self, messages: list[Any]) -> list[dict[str, Any]]:
        return []


class TestStreamEventSequence:
    """Verify stream() yields correct LLMEvent sequence."""

    @pytest.mark.asyncio
    async def test_stream_emits_pending_first(self) -> None:
        provider = _MockStreamProvider()
        provider.set_result(LLMResult(content="hi"))
        adapter = LegacyProviderAdapter(provider)
        msg = Message.user("hello")

        events: list[LLMEvent] = []
        async for event in adapter.stream(ModelID("mock"), [msg]):
            events.append(event)

        assert len(events) > 0
        assert isinstance(events[0], Pending)

    @pytest.mark.asyncio
    async def test_stream_text_only(self) -> None:
        provider = _MockStreamProvider()
        provider.set_result(LLMResult(content="Hello world", model="mock-m", finish_reason="stop"))
        adapter = LegacyProviderAdapter(provider)
        msg = Message.user("hi")

        events: list[LLMEvent] = []
        async for event in adapter.stream(ModelID("mock"), [msg]):
            events.append(event)

        # Should get: Pending, TextStarted, TextDelta, TextEnded, Finish
        assert len(events) >= 4
        # Find the text events
        text_deltas = [e for e in events if isinstance(e, TextDelta)]
        assert len(text_deltas) == 1
        assert text_deltas[0].text == "Hello world"

        finishes = [e for e in events if isinstance(e, Finish)]
        assert len(finishes) == 1
        assert finishes[0].finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_stream_with_tool_call(self) -> None:
        provider = _MockStreamProvider()
        provider.set_result(LLMResult(
            content="Calling tool",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "read", "arguments": '{"path": "/tmp/x"}'},
            }],
            finish_reason="tool_use",
        ))
        adapter = LegacyProviderAdapter(provider)
        msg = Message.user("read file")

        events: list[LLMEvent] = []
        async for event in adapter.stream(ModelID("mock"), [msg]):
            events.append(event)

        # Should include tool call events
        tool_starts = [e for e in events if isinstance(e, ToolCallStarted)]
        assert len(tool_starts) == 1
        assert tool_starts[0].name == "read"

        tool_ends = [e for e in events if isinstance(e, ToolCallEnded)]
        assert len(tool_ends) == 1
        assert tool_ends[0].args == {"path": "/tmp/x"}

    @pytest.mark.asyncio
    async def test_stream_tool_call_unknown(self) -> None:
        """Unknown tool call in stream produces EventToolFailure."""
        from cscode.schema.events import ToolFailure as EventToolFailure

        provider = _MockStreamProvider()
        provider.set_result(LLMResult(
            content="Calling unknown",
            tool_calls=[{
                "id": "call_bad",
                "type": "function",
                "function": {"name": "nonexistent_tool", "arguments": "{}"},
            }],
            finish_reason="tool_use",
        ))
        adapter = LegacyProviderAdapter(provider)
        msg = Message.user("do it")

        events: list[LLMEvent] = []
        async for event in adapter.stream(ModelID("mock"), [msg]):
            events.append(event)

        failures = [e for e in events if isinstance(e, EventToolFailure)]
        assert len(failures) == 1
        assert "Unknown tool" in failures[0].error or "nonexistent" in failures[0].error
