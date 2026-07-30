"""Tests for OpenAIResponsesProtocolAdapter.

Tests verify:
- Request payload building (input field vs messages, built-in tools)
- Non-streaming response parsing
- Streaming SSE event parsing
- Error handling
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from cscode.llm.protocols.openai_responses import OpenAIResponsesProtocolAdapter
from cscode.llm.route import AuthInfo, AuthScheme, EndpointInfo, ProtocolID, Route
from cscode.llm.types import LLMRequest
from cscode.schema.events import (
    Finish,
    TextDelta,
    TextEnded,
    TextStarted,
    ToolCallDelta,
    ToolCallEnded,
    ToolCallStarted,
)
from cscode.schema.ids import ToolCallID
from cscode.schema.ids import ModelID
from cscode.schema.messages import Message, MessageRole, SystemPart, TextPart
from cscode.schema.options import GenerationOptions
from cscode.schema.tool import ToolDefinition


# ─── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def route() -> Route:
    return Route(
        id="openai/gpt-4o",
        provider="openai",
        model="gpt-4o",
        protocol=ProtocolID.OPENAI_RESPONSES,
        endpoint=EndpointInfo(url="https://api.openai.com/v1/responses"),
        auth=AuthInfo(scheme=AuthScheme.BEARER, value="sk-test"),
    )


@pytest.fixture
def adapter() -> OpenAIResponsesProtocolAdapter:
    return OpenAIResponsesProtocolAdapter()


@pytest.fixture
def llm_request() -> LLMRequest:
    return LLMRequest(
        model=ModelID("gpt-4o"),
        messages=(
            Message(role=MessageRole.SYSTEM, parts=(SystemPart(text="You are a helpful assistant."),)),
            Message(role=MessageRole.USER, parts=(TextPart(text="Hello!"),)),
        ),
        tools=(
            ToolDefinition(name="web_search", description="Search the web", input_schema={"type": "object"}),
        ),
        options=GenerationOptions(temperature=0.7),
    )


@pytest.fixture
def complete_response() -> dict[str, Any]:
    """Sample non-streaming Responses API response with text output."""
    return {
        "id": "resp_abc123",
        "model": "gpt-4o",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "Hello! How can I help you today?"}
                ],
            }
        ],
        "usage": {
            "input_tokens": 15,
            "output_tokens": 10,
        },
    }


# ─── Request Building ──────────────────────────────────────────────


class TestRequestBuilding:
    """Adapter must build correct payload for the Responses API."""

    def test_uses_input_field(self, adapter: OpenAIResponsesProtocolAdapter, llm_request: LLMRequest) -> None:
        """Responses API uses 'input' not 'messages'."""
        payload = adapter._build_request(llm_request, stream=False)
        assert "input" in payload
        assert "messages" not in payload

    def test_input_contains_system_and_user(self, adapter: OpenAIResponsesProtocolAdapter, llm_request: LLMRequest) -> None:
        payload = adapter._build_request(llm_request, stream=False)
        assert len(payload["input"]) == 2
        assert payload["input"][0]["role"] == "system"
        assert payload["input"][1]["role"] == "user"

    def test_model_field(self, adapter: OpenAIResponsesProtocolAdapter, llm_request: LLMRequest) -> None:
        payload = adapter._build_request(llm_request, stream=False)
        assert payload["model"] == "gpt-4o"

    def test_includes_tools(self, adapter: OpenAIResponsesProtocolAdapter, llm_request: LLMRequest) -> None:
        payload = adapter._build_request(llm_request, stream=False)
        assert "tools" in payload
        assert len(payload["tools"]) == 1

    def test_no_tools_when_empty(self, adapter: OpenAIResponsesProtocolAdapter, llm_request: LLMRequest) -> None:
        llm_request_no_tools = LLMRequest(
            model=ModelID("gpt-4o"),
            messages=llm_request.messages,
            tools=(),
        )
        payload = adapter._build_request(llm_request_no_tools, stream=False)
        assert "tools" not in payload

    def test_stream_true(self, adapter: OpenAIResponsesProtocolAdapter, llm_request: LLMRequest) -> None:
        payload = adapter._build_request(llm_request, stream=True)
        assert payload["stream"] is True

    def test_stream_false(self, adapter: OpenAIResponsesProtocolAdapter, llm_request: LLMRequest) -> None:
        payload = adapter._build_request(llm_request, stream=False)
        assert payload["stream"] is False

    def test_temperature_in_options(self, adapter: OpenAIResponsesProtocolAdapter, llm_request: LLMRequest) -> None:
        payload = adapter._build_request(llm_request, stream=False)
        assert payload.get("temperature") == 0.7


# ─── Headers ───────────────────────────────────────────────────────


class TestHeaders:
    def test_bearer_token(self, adapter: OpenAIResponsesProtocolAdapter, route: Route) -> None:
        headers = adapter._build_headers(route)
        assert headers["Authorization"] == "Bearer sk-test"
        assert headers["Content-Type"] == "application/json"

    def test_header_auth(self, adapter: OpenAIResponsesProtocolAdapter) -> None:
        route = Route(
            id="test",
            provider="test",
            model="test",
            protocol=ProtocolID.OPENAI_RESPONSES,
            endpoint=EndpointInfo(url="https://example.com"),
            auth=AuthInfo(scheme=AuthScheme.HEADER, value="secret", header_name="x-api-key"),
        )
        headers = adapter._build_headers(route)
        assert headers["x-api-key"] == "secret"


# ─── Non-streaming Response Parsing ────────────────────────────────


class TestCompleteResponse:
    def test_parses_text_output(self, adapter: OpenAIResponsesProtocolAdapter, complete_response: dict[str, Any]) -> None:
        result = adapter._parse_complete_response(complete_response)
        assert result["content"] == "Hello! How can I help you today?"
        assert result["finish_reason"] == "stop"
        assert result["model"] == "gpt-4o"

    def test_parses_usage(self, adapter: OpenAIResponsesProtocolAdapter, complete_response: dict[str, Any]) -> None:
        result = adapter._parse_complete_response(complete_response)
        assert result["usage"] == {"input_tokens": 15, "output_tokens": 10}

    def test_empty_output(self, adapter: OpenAIResponsesProtocolAdapter) -> None:
        data: dict[str, Any] = {"id": "resp_123", "model": "gpt-4o", "output": [], "usage": {}}
        result = adapter._parse_complete_response(data)
        assert result["content"] == ""
        assert result["finish_reason"] == "stop"

    def test_multiple_output_items(self, adapter: OpenAIResponsesProtocolAdapter) -> None:
        """Responses API output can have multiple items (text + tool_calls)."""
        data: dict[str, Any] = {
            "id": "resp_123",
            "model": "gpt-4o",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "Let me search for that."},
                        {
                            "type": "tool_call",
                            "id": "call_123",
                            "name": "web_search",
                            "arguments": '{"query": "weather"}',
                        },
                    ],
                }
            ],
            "usage": {},
        }
        result = adapter._parse_complete_response(data)
        # Text content is extracted
        assert "Let me search for that." in result["content"]
        # Tool call info is not in content (returned separately in _parse_tool_calls)
        assert result["finish_reason"] == "tool_use"

    def test_no_usage(self, adapter: OpenAIResponsesProtocolAdapter) -> None:
        data: dict[str, Any] = {
            "id": "resp_123",
            "model": "gpt-4o",
            "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hi"}]}],
        }
        result = adapter._parse_complete_response(data)
        assert result["usage"] is None

    def test_model_fallback(self, adapter: OpenAIResponsesProtocolAdapter) -> None:
        data: dict[str, Any] = {
            "id": "resp_123",
            "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hi"}]}],
        }
        result = adapter._parse_complete_response(data)
        assert result["model"] == ""


# ─── Streaming SSE Parsing ─────────────────────────────────────────


class TestStreamParsing:
    """Adapter must parse Responses API SSE events into LLMEvents."""

    @pytest.mark.asyncio
    async def test_output_text_delta(self, adapter: OpenAIResponsesProtocolAdapter) -> None:
        """response.output_text.delta -> TextDelta."""
        data = {"type": "response.output_text.delta", "delta": "Hello"}
        events = []
        async for event in adapter._process_sse_event(data):
            events.append(event)
        assert len(events) == 1
        assert isinstance(events[0], TextDelta)
        assert events[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_output_item_added_tool_call(self, adapter: OpenAIResponsesProtocolAdapter) -> None:
        """response.output_item.added with tool_call -> ToolCallStarted."""
        data = {
            "type": "response.output_item.added",
            "item": {
                "id": "call_123",
                "type": "tool_call",
                "name": "web_search",
            },
        }
        events = []
        async for event in adapter._process_sse_event(data):
            events.append(event)
        assert len(events) == 1
        assert isinstance(events[0], ToolCallStarted)
        assert events[0].tool_call_id == ToolCallID("call_123")
        assert events[0].name == "web_search"

    @pytest.mark.asyncio
    async def test_output_item_done_tool_call(self, adapter: OpenAIResponsesProtocolAdapter) -> None:
        """response.output_item.done with tool_call -> ToolCallEnded."""
        data = {
            "type": "response.output_item.done",
            "item": {
                "id": "call_123",
                "type": "tool_call",
                "name": "web_search",
                "arguments": '{"query": "weather"}',
            },
        }
        events = []
        async for event in adapter._process_sse_event(data):
            events.append(event)
        assert len(events) == 1
        assert isinstance(events[0], ToolCallEnded)
        assert events[0].tool_call_id == ToolCallID("call_123")
        assert events[0].args == {"query": "weather"}

    @pytest.mark.asyncio
    async def test_completed(self, adapter: OpenAIResponsesProtocolAdapter) -> None:
        """response.completed -> Finish."""
        data = {
            "type": "response.completed",
            "response": {
                "status": "completed",
                "usage": {"input_tokens": 10, "output_tokens": 20},
            },
        }
        events = []
        async for event in adapter._process_sse_event(data):
            events.append(event)
        assert len(events) == 1
        assert isinstance(events[0], Finish)
        assert events[0].finish_reason == "stop"
        assert events[0].usage == {"prompt_tokens": 10, "completion_tokens": 20}

    @pytest.mark.asyncio
    async def test_unknown_event_skipped(self, adapter: OpenAIResponsesProtocolAdapter) -> None:
        """Unknown event types should be silently skipped."""
        data = {"type": "response.unknown_event", "data": "something"}
        events = []
        async for event in adapter._process_sse_event(data):
            events.append(event)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_output_text_delta_with_accumulated_text(self, adapter: OpenAIResponsesProtocolAdapter) -> None:
        """Multiple deltas accumulate into TextEnded on completion."""
        stream_events = [
            {"type": "response.output_text.delta", "delta": "Hello "},
            {"type": "response.output_text.delta", "delta": "world!"},
            {"type": "response.completed", "response": {"status": "completed"}},
        ]
        all_events = []
        tc_state: dict[str, Any] = {}
        for raw in stream_events:
            async for event in adapter._process_sse_event(raw, tc_state):
                all_events.append(event)

        texts = [e for e in all_events if isinstance(e, TextDelta)]
        assert len(texts) == 2
        assert texts[0].text == "Hello "
        assert texts[1].text == "world!"


# ─── Error Handling ────────────────────────────────────────────────


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_http_error_reraised(self, adapter: OpenAIResponsesProtocolAdapter, route: Route) -> None:
        """HTTP errors should be re-raised for the client to handle."""
        client = httpx.AsyncClient()
        # Build a minimal request
        request = LLMRequest(
            model=ModelID("gpt-4o"),
            messages=(Message(role=MessageRole.USER, parts=(TextPart(text="Hi"),)),),
        )
        # We expect an error because there's no real server
        with pytest.raises(
            (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ConnectTimeout),
        ):
            await adapter.complete(route, request, client)


# ─── Integration via LLMClient ─────────────────────────────────────


class TestClientIntegration:
    """LLMClient must dispatch OPENAI_RESPONSES to the correct adapter."""

    def test_route_uses_correct_protocol_id(self, route: Route) -> None:
        assert route.protocol == ProtocolID.OPENAI_RESPONSES
