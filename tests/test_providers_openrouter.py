from __future__ import annotations

import pytest
import respx

from cscode.core.config import Config
from cscode.core.errors import ProviderError
from cscode.core.messages import Message, MessageRole
from cscode.providers.openrouter import OpenRouterProvider


class TestOpenRouterProvider:
    @pytest.fixture
    def provider(self) -> OpenRouterProvider:
        return OpenRouterProvider(
            Config(
                api_key="test-key",
                model="openai/gpt-4o",
            )
        )

    def test_initialization(self, provider: OpenRouterProvider) -> None:
        assert provider.model == "openai/gpt-4o"

    def test_build_messages(self, provider: OpenRouterProvider) -> None:
        msgs = provider.build_messages([
            Message(role=MessageRole.SYSTEM, content="You are helpful."),
            Message(role=MessageRole.USER, content="Hi"),
        ])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "Hi"

    @pytest.mark.asyncio
    async def test_complete(self, provider: OpenRouterProvider) -> None:
        router = respx.mock(using="httpx")
        router.post("https://openrouter.ai/api/v1/chat/completions").respond(
            200,
            json={
                "id": "chatcmpl-123",
                "object": "chat.completion",
                "model": "openai/gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Hello from OpenRouter!",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )
        with router:
            result = await provider.complete([
                Message(role=MessageRole.USER, content="Hi"),
            ])
        assert result.content == "Hello from OpenRouter!"
        assert result.usage is not None
        assert result.usage["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_complete_with_tool_call(self, provider: OpenRouterProvider) -> None:
        router = respx.mock(using="httpx")
        router.post("https://openrouter.ai/api/v1/chat/completions").respond(
            200,
            json={
                "id": "chatcmpl-456",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path": "test.txt"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"total_tokens": 25},
            },
        )
        with router:
            result = await provider.complete([
                Message(role=MessageRole.USER, content="Read file"),
            ])
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["function"]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_api_error(self, provider: OpenRouterProvider) -> None:
        router = respx.mock(using="httpx")
        router.post("https://openrouter.ai/api/v1/chat/completions").respond(
            401,
            json={"error": {"message": "Invalid API key"}},
        )
        with router:
            with pytest.raises(ProviderError, match="401"):
                await provider.complete([
                    Message(role=MessageRole.USER, content="Hi"),
                ])
