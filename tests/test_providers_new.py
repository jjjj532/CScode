"""Tests for P1-2: 8 new provider integrations (Cohere, Grok, Mistral, Nvidia, Perplexity, XAI, Bedrock, Vertex).

Tests cover:
- Factory registration
- Default model/base URL settings
- complete() success via httpx mock
- Error handling (missing SDKs, network errors)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cscode.core.config import Config
from cscode.core.errors import ProviderError
from cscode.core.messages import Message, MessageRole
from cscode.providers.base import LLMProvider, LLMResult

# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def sample_messages() -> list[Message]:
    return [
        Message(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
        Message(role=MessageRole.USER, content="Hello!"),
    ]


# ─── Factory Registration ────────────────────────────────────────────


class TestNewProviderFactory:
    @pytest.mark.parametrize(
        "provider_name,expected_class_name",
        [
            ("cohere", "CohereProvider"),
            ("grok", "GrokProvider"),
            ("mistral", "MistralProvider"),
            ("nvidia", "NvidiaProvider"),
            ("perplexity", "PerplexityProvider"),
            ("xai", "XAIProvider"),
            ("bedrock", "BedrockProvider"),
            ("vertex", "VertexProvider"),
        ],
    )
    def test_create_provider(self, provider_name: str, expected_class_name: str) -> None:
        from cscode.providers import create_provider

        cfg = Config(provider=provider_name, api_key="test-key")
        provider = create_provider(cfg)
        assert provider.__class__.__name__ == expected_class_name


# ─── OpenAI-Compatible: Base Test Mixin ──────────────────────────


def _mock_openai_compatible_complete(provider: LLMProvider, api_base: str, expected_content: str) -> None:
    """Helper: mock the httpx client's post method to return a success response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": expected_content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        "model": provider.model,
    }
    provider._client.post = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
    import asyncio
    result = asyncio.run(provider.complete([
        Message(role=MessageRole.USER, content="Hello!"),
    ]))
    assert isinstance(result, LLMResult)
    assert expected_content in result.content


# ─── Cohere ─────────────────────────────────────────────────────


class TestCohereProvider:
    def test_init_sets_defaults(self) -> None:
        from cscode.providers.cohere import CohereProvider
        cfg = Config(provider="cohere", api_key="ck-123")
        p = CohereProvider(cfg)
        assert p._api_base == "https://api.cohere.com/v1"
        assert p._model == "command-r-plus"

    def test_model_property(self) -> None:
        from cscode.providers.cohere import CohereProvider
        cfg = Config(provider="cohere", model="command-r", api_key="ck-123")
        p = CohereProvider(cfg)
        assert p.model == "command-r"

    def test_complete_success(self) -> None:
        from cscode.providers.cohere import CohereProvider
        cfg = Config(provider="cohere", api_key="ck-123")
        p = CohereProvider(cfg)
        _mock_openai_compatible_complete(p, "https://api.cohere.com/v1", "Hello from Cohere")


# ─── Grok ───────────────────────────────────────────────────────


class TestGrokProvider:
    def test_init_sets_defaults(self) -> None:
        from cscode.providers.grok import GrokProvider
        cfg = Config(provider="grok", api_key="xk-123")
        p = GrokProvider(cfg)
        assert p._api_base == "https://api.x.ai/v1"
        assert p._model == "grok-2-latest"

    def test_complete_success(self) -> None:
        from cscode.providers.grok import GrokProvider
        cfg = Config(provider="grok", api_key="xk-123")
        p = GrokProvider(cfg)
        _mock_openai_compatible_complete(p, "https://api.x.ai/v1", "Hello from Grok")


# ─── Mistral ────────────────────────────────────────────────────


class TestMistralProvider:
    def test_init_sets_defaults(self) -> None:
        from cscode.providers.mistral import MistralProvider
        cfg = Config(provider="mistral", api_key="ms-123")
        p = MistralProvider(cfg)
        assert p._api_base == "https://api.mistral.ai/v1"
        assert p._model == "mistral-large-latest"

    def test_model_property(self) -> None:
        from cscode.providers.mistral import MistralProvider
        cfg = Config(provider="mistral", model="mistral-small-latest", api_key="ms-123")
        p = MistralProvider(cfg)
        assert p.model == "mistral-small-latest"

    def test_complete_success(self) -> None:
        from cscode.providers.mistral import MistralProvider
        cfg = Config(provider="mistral", api_key="ms-123")
        p = MistralProvider(cfg)
        _mock_openai_compatible_complete(p, "https://api.mistral.ai/v1", "Hello from Mistral")


# ─── Nvidia ─────────────────────────────────────────────────────


class TestNvidiaProvider:
    def test_init_sets_defaults(self) -> None:
        from cscode.providers.nvidia import NvidiaProvider
        cfg = Config(provider="nvidia", api_key="nv-123")
        p = NvidiaProvider(cfg)
        assert p._api_base == "https://integrate.api.nvidia.com/v1"
        assert p._model == "meta/llama-3.1-70b-instruct"

    def test_complete_success(self) -> None:
        from cscode.providers.nvidia import NvidiaProvider
        cfg = Config(provider="nvidia", api_key="nv-123")
        p = NvidiaProvider(cfg)
        _mock_openai_compatible_complete(p, "https://integrate.api.nvidia.com/v1", "Hello from Nvidia")


# ─── Perplexity ─────────────────────────────────────────────────


class TestPerplexityProvider:
    def test_init_sets_defaults(self) -> None:
        from cscode.providers.perplexity import PerplexityProvider
        cfg = Config(provider="perplexity", api_key="pp-123")
        p = PerplexityProvider(cfg)
        assert p._api_base == "https://api.perplexity.ai"
        assert p._model == "sonar-pro"

    def test_model_property(self) -> None:
        from cscode.providers.perplexity import PerplexityProvider
        cfg = Config(provider="perplexity", model="sonar-deep-research", api_key="pp-123")
        p = PerplexityProvider(cfg)
        assert p.model == "sonar-deep-research"

    def test_complete_success(self) -> None:
        from cscode.providers.perplexity import PerplexityProvider
        cfg = Config(provider="perplexity", api_key="pp-123")
        p = PerplexityProvider(cfg)
        _mock_openai_compatible_complete(p, "https://api.perplexity.ai", "Hello from Perplexity")


# ─── XAI ────────────────────────────────────────────────────────


class TestXAIProvider:
    def test_init_sets_defaults(self) -> None:
        from cscode.providers.xai import XAIProvider
        cfg = Config(provider="xai", api_key="xk-456")
        p = XAIProvider(cfg)
        assert p._api_base == "https://api.x.ai/v1"
        assert p._model == "grok-2-latest"

    def test_complete_success(self) -> None:
        from cscode.providers.xai import XAIProvider
        cfg = Config(provider="xai", api_key="xk-456")
        p = XAIProvider(cfg)
        _mock_openai_compatible_complete(p, "https://api.x.ai/v1", "Hello from XAI")


# ─── Bedrock ────────────────────────────────────────────────────


class TestBedrockProvider:
    def test_init_sets_defaults(self) -> None:
        from cscode.providers.bedrock import BedrockProvider
        cfg = Config(provider="bedrock", api_base="us-west-2")
        p = BedrockProvider(cfg)
        assert p._region == "us-west-2"
        assert "claude" in p._model

    def test_init_default_region(self) -> None:
        from cscode.providers.bedrock import BedrockProvider
        cfg = Config(provider="bedrock")
        p = BedrockProvider(cfg)
        assert p._region == "us-east-1"

    def test_model_property(self) -> None:
        from cscode.providers.bedrock import BedrockProvider
        cfg = Config(provider="bedrock", model="anthropic.claude-v2")
        p = BedrockProvider(cfg)
        assert p.model == "anthropic.claude-v2"

    def test_build_messages_skips_system(self) -> None:
        from cscode.providers.bedrock import BedrockProvider
        cfg = Config(provider="bedrock")
        p = BedrockProvider(cfg)
        msgs = [
            Message(role=MessageRole.SYSTEM, content="system prompt"),
            Message(role=MessageRole.USER, content="user msg"),
        ]
        result = p.build_messages(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"][0]["text"] == "user msg"

    def test_extract_system(self) -> None:
        from cscode.providers.bedrock import BedrockProvider
        cfg = Config(provider="bedrock")
        p = BedrockProvider(cfg)
        msgs = [
            Message(role=MessageRole.SYSTEM, content="system prompt"),
            Message(role=MessageRole.USER, content="user msg"),
        ]
        systems = p._extract_system(msgs)
        assert len(systems) == 1
        assert systems[0]["text"] == "system prompt"

    def test_complete_missing_boto3(self) -> None:
        from cscode.providers.bedrock import BedrockProvider
        cfg = Config(provider="bedrock")
        p = BedrockProvider(cfg)
        import sys
        saved_boto3 = sys.modules.get("boto3")
        try:
            sys.modules.pop("boto3", None)
            import asyncio
            with pytest.raises(ProviderError, match="requires boto3"):
                asyncio.run(p._ensure_client())
        finally:
            if saved_boto3:
                sys.modules["boto3"] = saved_boto3

    @pytest.mark.asyncio
    async def test_stream_not_implemented(self) -> None:
        from cscode.providers.bedrock import BedrockProvider
        cfg = Config(provider="bedrock")
        p = BedrockProvider(cfg)
        with pytest.raises(NotImplementedError):
            async for _ in p.stream([Message(role=MessageRole.USER, content="hi")]):
                pass


# ─── Vertex ─────────────────────────────────────────────────────


class TestVertexProvider:
    def test_init_sets_defaults(self) -> None:
        from cscode.providers.vertex import VertexProvider
        cfg = Config(provider="vertex", api_base="my-project-123")
        p = VertexProvider(cfg)
        assert p._project == "my-project-123"
        assert "gemini" in p._model

    def test_model_property(self) -> None:
        from cscode.providers.vertex import VertexProvider
        cfg = Config(provider="vertex", model="gemini-2.0-pro-001")
        p = VertexProvider(cfg)
        assert p.model == "gemini-2.0-pro-001"

    def test_build_messages_with_system(self) -> None:
        from cscode.providers.vertex import VertexProvider
        cfg = Config(provider="vertex")
        p = VertexProvider(cfg)
        msgs = [
            Message(role=MessageRole.SYSTEM, content="You are a helpful AI."),
            Message(role=MessageRole.USER, content="Hello!"),
        ]
        result = p.build_messages(msgs)
        assert "system_instruction" in result
        assert result["system_instruction"]["parts"][0]["text"] == "You are a helpful AI."
        assert len(result["contents"]) == 1
        assert result["contents"][0]["role"] == "user"

    def test_build_messages_assistant_role(self) -> None:
        from cscode.providers.vertex import VertexProvider
        cfg = Config(provider="vertex")
        p = VertexProvider(cfg)
        msgs = [
            Message(role=MessageRole.ASSISTANT, content="Sure, I can help!"),
        ]
        result = p.build_messages(msgs)
        assert result["contents"][0]["role"] == "model"

    def test_build_url_with_project(self) -> None:
        from cscode.providers.vertex import VertexProvider
        cfg = Config(provider="vertex", api_base="my-project", api_key="key")
        p = VertexProvider(cfg)
        url = p._build_url()
        assert "my-project" in url
        assert "us-central1" in url

    def test_build_url_without_project(self) -> None:
        from cscode.providers.vertex import VertexProvider
        cfg = Config(provider="vertex", api_key="key")
        p = VertexProvider(cfg)
        url = p._build_url()
        assert "generativelanguage" in url
        assert "v1beta" in url

    def test_get_headers_with_api_key(self) -> None:
        from cscode.providers.vertex import VertexProvider
        cfg = Config(provider="vertex", api_key="test-key-123")
        p = VertexProvider(cfg)
        import asyncio
        headers = asyncio.run(p._get_headers())
        assert headers["x-goog-api-key"] == "test-key-123"

    def test_get_headers_no_api_key_missing_google_auth(self) -> None:
        from cscode.providers.vertex import VertexProvider
        cfg = Config(provider="vertex")
        p = VertexProvider(cfg)
        # Simulate missing google.auth by removing it from sys.modules
        saved_auth = __import__("sys").modules.get("google.auth")
        try:
            import sys
            # Only pop if it exists
            if "google.auth" in sys.modules:
                del sys.modules["google.auth"]
            if "google" in sys.modules:
                del sys.modules["google"]
            with pytest.raises(ProviderError, match="google-auth"):
                import asyncio
                asyncio.run(p._get_headers())
        finally:
            if saved_auth:
                __import__("sys").modules["google.auth"] = saved_auth

    @pytest.mark.asyncio
    async def test_stream_not_implemented(self) -> None:
        from cscode.providers.vertex import VertexProvider
        cfg = Config(provider="vertex", api_key="key")
        p = VertexProvider(cfg)
        with pytest.raises(NotImplementedError):
            async for _ in p.stream([Message(role=MessageRole.USER, content="hi")]):
                pass
