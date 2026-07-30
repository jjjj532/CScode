"""Tests for LLM Route system (llm/route.py).

Tests verify:
- ProtocolID enum values match what client.py uses
- AuthScheme enum values match what protocol adapters use
- Route dataclass provides all properties consumers need
- resolve_route() correctly maps providers to protocols
- Route endpoint/auth configuration is correct for each provider
"""

from __future__ import annotations

from typing import Any

import pytest

from cscode.llm.route import AuthInfo, AuthScheme, EndpointInfo, ProtocolID, Route, resolve_route
from cscode.llm.client import LLMClient


# ─── ProtocolID enum ──────────────────────────────────────────────


class TestProtocolID:
    """ProtocolID must be an enum with values used by client.py."""

    def test_openai_chat_exists(self) -> None:
        assert ProtocolID.OPENAI_CHAT is not None
        assert ProtocolID.OPENAI_CHAT.value == "openai-chat"

    def test_openai_compatible_exists(self) -> None:
        assert ProtocolID.OPENAI_COMPATIBLE is not None
        assert ProtocolID.OPENAI_COMPATIBLE.value == "openai-compatible"

    def test_anthropic_messages_exists(self) -> None:
        assert ProtocolID.ANTHROPIC_MESSAGES is not None
        assert ProtocolID.ANTHROPIC_MESSAGES.value == "anthropic-messages"

    def test_gemini_exists(self) -> None:
        assert ProtocolID.GEMINI is not None
        assert ProtocolID.GEMINI.value == "gemini"

    def test_openai_responses_exists(self) -> None:
        """Test the new OPENAI_RESPONSES protocol ID."""
        assert ProtocolID.OPENAI_RESPONSES is not None
        assert ProtocolID.OPENAI_RESPONSES.value == "openai-responses"

    def test_all_values_are_unique(self) -> None:
        values = [p.value for p in ProtocolID]
        assert len(values) == len(set(values))


# ─── AuthScheme enum ──────────────────────────────────────────────


class TestAuthScheme:
    """AuthScheme must have the values used by protocol adapters."""

    def test_bearer_exists(self) -> None:
        assert AuthScheme.BEARER is not None
        assert AuthScheme.BEARER.value == "bearer"

    def test_header_exists(self) -> None:
        """Used by anthropic_messages.py for x-api-key."""
        assert AuthScheme.HEADER is not None
        assert AuthScheme.HEADER.value == "header"


# ─── Route dataclass ──────────────────────────────────────────────


class TestRouteBasic:
    """Route must provide all properties that consumers need."""

    def test_minimal_route(self) -> None:
        """Create a Route with all required fields."""
        route = Route(
            id="test-route",
            provider="openai",
            model="gpt-4o",
            protocol=ProtocolID.OPENAI_CHAT,
            endpoint=EndpointInfo(url="https://api.openai.com/v1/chat/completions"),
            auth=AuthInfo(scheme=AuthScheme.BEARER, value="sk-test-123"),
        )
        assert route.id == "test-route"
        assert route.provider == "openai"
        assert route.model == "gpt-4o"
        assert route.protocol == ProtocolID.OPENAI_CHAT
        assert route.endpoint.url == "https://api.openai.com/v1/chat/completions"
        assert route.auth.scheme == AuthScheme.BEARER
        assert route.auth.value == "sk-test-123"

    def test_route_auth_header_name(self) -> None:
        """HEADER auth must allow custom header name (e.g. x-api-key)."""
        route = Route(
            id="anthropic-test",
            provider="anthropic",
            model="claude-3-5-sonnet",
            protocol=ProtocolID.ANTHROPIC_MESSAGES,
            endpoint=EndpointInfo(url="https://api.anthropic.com/v1/messages"),
            auth=AuthInfo(scheme=AuthScheme.HEADER, value="sk-ant-test", header_name="x-api-key"),
        )
        assert route.auth.scheme == AuthScheme.HEADER
        assert route.auth.value == "sk-ant-test"
        assert route.auth.header_name == "x-api-key"

    def test_route_default_auth_header_name(self) -> None:
        """Default auth header_name should be 'Authorization'."""
        route = Route(
            id="default-header",
            provider="openai",
            model="gpt-4",
            protocol=ProtocolID.OPENAI_CHAT,
            endpoint=EndpointInfo(url="https://api.openai.com/v1/chat/completions"),
            auth=AuthInfo(scheme=AuthScheme.BEARER, value="sk-test"),
        )
        assert route.auth.header_name == "Authorization"

    def test_route_protocol_used_in_client(self) -> None:
        """Route.protocol must be usable in match/case (like client.py does)."""
        route = Route(
            id="test",
            provider="openai",
            model="gpt-4o",
            protocol=ProtocolID.OPENAI_CHAT,
            endpoint=EndpointInfo(url="https://api.openai.com/v1/chat/completions"),
            auth=AuthInfo(scheme=AuthScheme.BEARER, value="sk-test"),
        )
        # This matches the pattern in client.py _get_adapter()
        match route.protocol:
            case ProtocolID.OPENAI_CHAT | ProtocolID.OPENAI_COMPATIBLE:
                assert True
            case _:
                pytest.fail("ProtocolID.OPENAI_CHAT should match OPENAI_CHAT | OPENAI_COMPATIBLE")


# ─── resolve_route() ──────────────────────────────────────────────


class TestResolveRoute:
    """resolve_route() must map providers to routes correctly."""

    def test_openai_default(self) -> None:
        route = resolve_route(
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
        )
        assert route.provider == "openai"
        assert route.model == "gpt-4o"
        assert route.protocol == ProtocolID.OPENAI_CHAT
        assert "api.openai.com" in route.endpoint.url
        assert route.auth.scheme == AuthScheme.BEARER
        assert route.auth.value == "sk-test"

    def test_openai_custom_base(self) -> None:
        route = resolve_route(
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            api_base="https://custom-proxy.example.com/v1",
        )
        assert route.endpoint.url.startswith("https://custom-proxy.example.com")

    def test_anthropic_default(self) -> None:
        route = resolve_route(
            provider="anthropic",
            model="claude-3-5-sonnet",
            api_key="sk-ant-test",
        )
        assert route.provider == "anthropic"
        assert route.protocol == ProtocolID.ANTHROPIC_MESSAGES
        assert "api.anthropic.com" in route.endpoint.url
        assert route.auth.scheme == AuthScheme.HEADER
        assert route.auth.value == "sk-ant-test"
        assert route.auth.header_name == "x-api-key"

    def test_anthropic_custom_base(self) -> None:
        route = resolve_route(
            provider="anthropic",
            model="claude-3-5-sonnet",
            api_key="sk-ant-test",
            api_base="https://custom-proxy.example.com",
        )
        assert route.endpoint.url.startswith("https://custom-proxy.example.com")

    def test_ollama_default(self) -> None:
        route = resolve_route(
            provider="ollama",
            model="llama3",
            api_key="",
        )
        assert route.provider == "ollama"
        assert "localhost:11434" in route.endpoint.url
        assert route.auth.scheme == AuthScheme.NONE

    def test_azure(self) -> None:
        route = resolve_route(
            provider="azure",
            model="gpt-4",
            api_key="azure-key",
            api_base="https://my-resource.openai.azure.com",
        )
        assert route.provider == "azure"
        assert route.protocol == ProtocolID.OPENAI_CHAT
        assert "azure.com" in route.endpoint.url
        assert route.auth.scheme == AuthScheme.BEARER
        assert route.auth.value == "azure-key"

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            resolve_route(
                provider="nonexistent-provider",
                model="test",
                api_key="test",
            )

    def test_empty_api_key_openai_does_not_raise(self) -> None:
        """OpenAI allows empty key (for local proxies that don't need auth)."""
        route = resolve_route(
            provider="openai",
            model="gpt-4o",
            api_key="",
        )
        assert route.auth.value == ""

    def test_route_id_is_generated(self) -> None:
        route = resolve_route(
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
        )
        assert isinstance(route.id, str)
        assert len(route.id) > 0


# ─── Auth helper used by protocol adapters ────────────────────────


class TestAuthHeaders:
    """Protocol adapters build headers from Route.auth."""

    def test_bearer_auth_headers(self) -> None:
        route = Route(
            id="test",
            provider="openai",
            model="gpt-4",
            protocol=ProtocolID.OPENAI_CHAT,
            endpoint=EndpointInfo(url="https://api.openai.com/v1/chat/completions"),
            auth=AuthInfo(scheme=AuthScheme.BEARER, value="sk-test"),
        )
        headers = {
            "Content-Type": "application/json",
        }
        if route.auth.scheme == AuthScheme.BEARER and route.auth.value:
            headers["Authorization"] = f"Bearer {route.auth.value}"
        assert headers["Authorization"] == "Bearer sk-test"

    def test_header_auth_headers(self) -> None:
        """Anthropic uses x-api-key header via HEADER scheme."""
        route = Route(
            id="test",
            provider="anthropic",
            model="claude-3-5-sonnet",
            protocol=ProtocolID.ANTHROPIC_MESSAGES,
            endpoint=EndpointInfo(url="https://api.anthropic.com/v1/messages"),
            auth=AuthInfo(scheme=AuthScheme.HEADER, value="sk-ant-test", header_name="x-api-key"),
        )
        headers = {
            "Content-Type": "application/json",
        }
        if route.auth.scheme == AuthScheme.HEADER:
            headers[route.auth.header_name] = route.auth.value
        elif route.auth.scheme == AuthScheme.BEARER and route.auth.value:
            headers["Authorization"] = f"Bearer {route.auth.value}"
        assert headers["x-api-key"] == "sk-ant-test"
        assert "Authorization" not in headers

    def test_no_auth(self) -> None:
        """Ollama typically uses no auth."""
        route = Route(
            id="test",
            provider="ollama",
            model="llama3",
            protocol=ProtocolID.OPENAI_COMPATIBLE,
            endpoint=EndpointInfo(url="http://localhost:11434/api/chat"),
            auth=AuthInfo(scheme=AuthScheme.NONE, value=""),
        )
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if route.auth.scheme == AuthScheme.BEARER and route.auth.value:
            headers["Authorization"] = f"Bearer {route.auth.value}"
        elif route.auth.scheme == AuthScheme.HEADER:
            headers[route.auth.header_name] = route.auth.value
        # NONE scheme should not add auth headers
        assert "Authorization" not in headers
        assert len(headers) == 1  # only Content-Type
