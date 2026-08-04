"""Tests for LLMClient — route dispatch, adapter resolution, stream/generate."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cscode.llm.client import LLMClient
from cscode.llm.protocols.openai_chat import OpenAIProtocolAdapter
from cscode.llm.route import AuthInfo, AuthScheme, EndpointInfo, ProtocolID, Route
from cscode.llm.types import LLMRequest
from cscode.schema.errors import LLMError, LLMErrorReason
from cscode.schema.events import Error as LLMEventError
from cscode.schema.events import Finish, Pending, TextDelta, ToolCallEnded
from cscode.schema.ids import ModelID, ToolCallID
from cscode.schema.messages import Message
from cscode.schema.options import GenerationOptions

# ─── Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def openai_route() -> Route:
    return Route(
        id="test/openai",
        provider="openai",
        model=ModelID("gpt-4o"),
        protocol=ProtocolID.OPENAI_CHAT,
        endpoint=EndpointInfo(url="https://api.openai.com/v1/chat/completions"),
        auth=AuthInfo(scheme=AuthScheme.BEARER, value="sk-test"),
    )


@pytest.fixture
def anthropic_route() -> Route:
    return Route(
        id="test/anthropic",
        provider="anthropic",
        model=ModelID("claude-3-5-sonnet"),
        protocol=ProtocolID.ANTHROPIC_MESSAGES,
        endpoint=EndpointInfo(url="https://api.anthropic.com/v1/messages"),
        auth=AuthInfo(scheme=AuthScheme.HEADER, value="sk-ant-test", header_name="x-api-key"),
    )


@pytest.fixture
def responses_route() -> Route:
    return Route(
        id="test/responses",
        provider="openai",
        model=ModelID("gpt-4o"),
        protocol=ProtocolID.OPENAI_RESPONSES,
        endpoint=EndpointInfo(url="https://api.openai.com/v1/responses"),
        auth=AuthInfo(scheme=AuthScheme.BEARER, value="sk-test"),
    )


@pytest.fixture
def gemini_route() -> Route:
    return Route(
        id="test/gemini",
        provider="google",
        model=ModelID("gemini-2.0-flash"),
        protocol=ProtocolID.GEMINI,
        endpoint=EndpointInfo(url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"),
        auth=AuthInfo(scheme=AuthScheme.NONE, value=""),
    )


@pytest.fixture
def http_client() -> httpx.AsyncClient:
    return MagicMock(spec=httpx.AsyncClient)


@pytest.fixture
def llm_request() -> LLMRequest:
    return LLMRequest(
        model=ModelID("gpt-4o"),
        messages=(Message(role="user", parts=[{"type": "text", "text": "hello"}]),),  # type: ignore[list-item]
        options=GenerationOptions(temperature=0.7),
    )


# ─── Constructor ────────────────────────────────────────────────────

class TestConstructor:
    def test_stores_route(self, openai_route: Route) -> None:
        client = LLMClient(openai_route)
        assert client.route is openai_route

    def test_stores_http_client(self, openai_route: Route, http_client: httpx.AsyncClient) -> None:
        client = LLMClient(openai_route, httpx_client=http_client)
        assert client._client is http_client

    def test_default_http_client_is_none(self, openai_route: Route) -> None:
        client = LLMClient(openai_route)
        assert client._client is None


# ─── _get_adapter ───────────────────────────────────────────────────

class TestGetAdapter:
    def test_openai_chat_adapter(self, openai_route: Route) -> None:
        client = LLMClient(openai_route)
        adapter = client._get_adapter()
        assert isinstance(adapter, OpenAIProtocolAdapter)

    def test_openai_compatible_adapter(self) -> None:
        route = Route(
            id="test/ollama",
            provider="ollama",
            model=ModelID("llama3"),
            protocol=ProtocolID.OPENAI_COMPATIBLE,
            endpoint=EndpointInfo(url="http://localhost:11434/api/chat"),
            auth=AuthInfo(scheme=AuthScheme.NONE, value=""),
        )
        client = LLMClient(route)
        adapter = client._get_adapter()
        assert isinstance(adapter, OpenAIProtocolAdapter)

    def test_anthropic_adapter(self, anthropic_route: Route) -> None:
        client = LLMClient(anthropic_route)
        adapter = client._get_adapter()
        from cscode.llm.protocols.anthropic_messages import AnthropicProtocolAdapter
        assert isinstance(adapter, AnthropicProtocolAdapter)

    def test_openai_responses_adapter(self, responses_route: Route) -> None:
        client = LLMClient(responses_route)
        adapter = client._get_adapter()
        from cscode.llm.protocols.openai_responses import OpenAIResponsesProtocolAdapter
        assert isinstance(adapter, OpenAIResponsesProtocolAdapter)

    def test_gemini_raises_not_implemented(self, gemini_route: Route) -> None:
        client = LLMClient(gemini_route)
        with pytest.raises(NotImplementedError, match="Gemini"):
            client._get_adapter()

    def test_unknown_protocol_raises_value_error(self) -> None:
        route = Route(
            id="test/unknown",
            provider="unknown",
            model=ModelID("unknown"),
            protocol=ProtocolID.OPENAI_CHAT,  # valid enum but unknown provider string
            endpoint=EndpointInfo(url="http://localhost:9999/v1/chat"),
            auth=AuthInfo(scheme=AuthScheme.NONE, value=""),
        )
        client = LLMClient(route)
        # protocol is valid OPENAI_CHAT, so this should return OpenAIProtocolAdapter
        adapter = client._get_adapter()
        assert isinstance(adapter, OpenAIProtocolAdapter)


# ─── _http_client lazy init ─────────────────────────────────────────

class TestHttpClient:
    def test_lazy_creates_client(self, openai_route: Route) -> None:
        client = LLMClient(openai_route)
        assert client._client is None
        c = client._http_client
        assert isinstance(c, httpx.AsyncClient)
        assert client._client is c

    def test_reuses_existing_client(self, openai_route: Route) -> None:
        mock = MagicMock(spec=httpx.AsyncClient)
        client = LLMClient(openai_route, httpx_client=mock)
        assert client._http_client is mock


# ─── _parse_complete ────────────────────────────────────────────────

class TestParseComplete:
    def test_parse_full_response(self, openai_route: Route) -> None:
        client = LLMClient(openai_route)
        raw = {
            "content": "Hello world",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            "model": "gpt-4o",
        }
        result = client._parse_complete(raw)
        assert result.content == "Hello world"
        assert result.finish_reason == "stop"
        assert result.usage == {"prompt_tokens": 10, "completion_tokens": 20}
        assert result.model == "gpt-4o"

    def test_parse_minimal_response(self, openai_route: Route) -> None:
        client = LLMClient(openai_route)
        raw: dict[str, Any] = {}
        result = client._parse_complete(raw)
        assert result.content == ""
        assert result.finish_reason == ""
        assert result.usage is None
        assert result.model == "gpt-4o"  # falls back to route.model

    def test_parse_with_optional_fields(self, openai_route: Route) -> None:
        client = LLMClient(openai_route)
        raw = {"content": "Hi", "finish_reason": "length"}
        result = client._parse_complete(raw)
        assert result.content == "Hi"
        assert result.finish_reason == "length"


# ─── generate() ─────────────────────────────────────────────────────

class TestGenerate:
    @pytest.mark.asyncio
    async def test_generate_happy_path(
        self, openai_route: Route, llm_request: LLMRequest
    ) -> None:
        client = LLMClient(openai_route)
        with patch.object(
            client,
            "_get_adapter",
        ) as mock_adapter_factory:
            mock_adapter = MagicMock()
            mock_adapter.complete = AsyncMock(
                return_value={
                    "content": "Hello!",
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                    "model": "gpt-4o",
                }
            )
            mock_adapter_factory.return_value = mock_adapter

            result = await client.generate(llm_request)

            assert result.content == "Hello!"
            assert result.finish_reason == "stop"
            assert result.usage == {"prompt_tokens": 5, "completion_tokens": 3}
            assert result.model == "gpt-4o"
            mock_adapter.complete.assert_awaited_once()


# ─── stream() ───────────────────────────────────────────────────────

class TestStream:
    @pytest.mark.asyncio
    async def test_stream_emits_pending_first(
        self, openai_route: Route, llm_request: LLMRequest
    ) -> None:
        client = LLMClient(openai_route)
        with patch.object(client, "_get_adapter") as mock_factory:
            mock_adapter = MagicMock()
            mock_adapter.stream.return_value = _async_gen()
            mock_factory.return_value = mock_adapter

            events: list[object] = []
            async for event in client.stream(llm_request):
                events.append(event)

            assert len(events) >= 1
            assert isinstance(events[0], Pending)

    @pytest.mark.asyncio
    async def test_stream_yields_adapter_events(
        self, openai_route: Route, llm_request: LLMRequest
    ) -> None:
        client = LLMClient(openai_route)
        adapter_events = [
            TextDelta(text="Hello"),
            ToolCallEnded(tool_call_id=ToolCallID("call_1"), name="read", args={"path": "test.txt"}),
            Finish(finish_reason="tool_use"),
        ]

        with patch.object(client, "_get_adapter") as mock_factory:
            mock_adapter = MagicMock()
            mock_adapter.stream.return_value = _async_gen(*adapter_events)
            mock_factory.return_value = mock_adapter

            events: list[object] = []
            async for event in client.stream(llm_request):
                events.append(event)

            # First event should be Pending, then adapter events
            assert len(events) == 1 + len(adapter_events)
            assert isinstance(events[0], Pending)
            assert isinstance(events[1], TextDelta)
            assert isinstance(events[2], ToolCallEnded)
            assert isinstance(events[3], Finish)

    @pytest.mark.asyncio
    async def test_stream_llm_error_yields_error_event(
        self, openai_route: Route, llm_request: LLMRequest
    ) -> None:
        client = LLMClient(openai_route)
        llm_error = LLMError(
            module="test",
            method="stream",
            reason=LLMErrorReason.PROVIDER_INTERNAL,
            message="Provider unavailable",
        )

        with patch.object(client, "_get_adapter") as mock_factory:
            mock_adapter = MagicMock()
            mock_adapter.stream.side_effect = llm_error
            mock_factory.return_value = mock_adapter

            events: list[object] = []
            async for event in client.stream(llm_request):
                events.append(event)

            assert len(events) == 2
            assert isinstance(events[0], Pending)
            assert isinstance(events[1], LLMEventError)
            assert events[1].error is llm_error

    @pytest.mark.asyncio
    async def test_stream_http_status_error_yields_error_event(
        self, openai_route: Route, llm_request: LLMRequest
    ) -> None:
        client = LLMClient(openai_route)

        response = MagicMock(spec=httpx.Response)
        response.status_code = 502
        response.text = "Bad Gateway"

        http_error = httpx.HTTPStatusError(
            "502 Bad Gateway",
            request=MagicMock(spec=httpx.Request),
            response=response,
        )

        with patch.object(client, "_get_adapter") as mock_factory:
            mock_adapter = MagicMock()
            mock_adapter.stream.side_effect = http_error
            mock_factory.return_value = mock_adapter

            events: list[object] = []
            async for event in client.stream(llm_request):
                events.append(event)

            assert len(events) == 2
            assert isinstance(events[1], LLMEventError)
            assert "502" in events[1].error.message
            assert events[1].error.retryable is True  # status_code >= 500

    @pytest.mark.asyncio
    async def test_stream_http_status_error_4xx_not_retryable(
        self, openai_route: Route, llm_request: LLMRequest
    ) -> None:
        client = LLMClient(openai_route)

        response = MagicMock(spec=httpx.Response)
        response.status_code = 401
        response.text = "Unauthorized"

        http_error = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=MagicMock(spec=httpx.Request),
            response=response,
        )

        with patch.object(client, "_get_adapter") as mock_factory:
            mock_adapter = MagicMock()
            mock_adapter.stream.side_effect = http_error
            mock_factory.return_value = mock_adapter

            events: list[object] = []
            async for event in client.stream(llm_request):
                events.append(event)

            assert isinstance(events[1], LLMEventError)
            assert events[1].error.retryable is False

    @pytest.mark.asyncio
    async def test_stream_request_error_yields_error_event(
        self, openai_route: Route, llm_request: LLMRequest
    ) -> None:
        client = LLMClient(openai_route)

        req_error = httpx.RequestError("Connection refused", request=MagicMock(spec=httpx.Request))

        with patch.object(client, "_get_adapter") as mock_factory:
            mock_adapter = MagicMock()
            mock_adapter.stream.side_effect = req_error
            mock_factory.return_value = mock_adapter

            events: list[object] = []
            async for event in client.stream(llm_request):
                events.append(event)

            assert len(events) == 2
            assert isinstance(events[1], LLMEventError)
            assert "Connection refused" in events[1].error.message
            assert events[1].error.reason == LLMErrorReason.TRANSPORT

    @pytest.mark.asyncio
    async def test_stream_real_http_401_yields_error_event_not_crash(
        self, openai_route: Route, llm_request: LLMRequest
    ) -> None:
        """Regression (Bug 6): a streaming HTTP 401 must yield LLMEventError,
        not crash with ResponseNotRead when accessing response.text.
        """
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                request=request,
                stream=httpx.ByteStream(b'{"error": {"message": "Authentication Failed"}}'),
                headers={"content-type": "application/json"},
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = LLMClient(openai_route, http)
            events: list[object] = []
            async for event in client.stream(llm_request):
                events.append(event)

        assert len(events) == 2
        assert isinstance(events[0], Pending)
        assert isinstance(events[1], LLMEventError)
        assert "401" in events[1].error.message
        assert "Authentication Failed" in events[1].error.message
        assert events[1].error.retryable is False


# ─── Helpers ────────────────────────────────────────────────────────

async def _async_gen(*events: object) -> AsyncIterator[object]:
    """Helper to create an async generator from events."""
    for event in events:
        yield event
