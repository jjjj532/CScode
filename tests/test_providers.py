from __future__ import annotations

import json

import pytest
import respx

from cscode.core.config import Config
from cscode.core.errors import ProviderError  # noqa: F401
from cscode.core.messages import Message, MessageRole
from cscode.providers.base import LLMProvider
from cscode.providers.openai import OpenAIProvider


def test_provider_factory():
    from cscode.providers import create_provider
    from cscode.providers.anthropic import AnthropicProvider
    from cscode.providers.ollama import OllamaProvider

    openai = create_provider(Config(api_key="k", provider="openai"))
    assert isinstance(openai, OpenAIProvider)

    anth = create_provider(Config(api_key="k", provider="anthropic"))
    assert isinstance(anth, AnthropicProvider)

    olla = create_provider(Config(provider="ollama"))
    assert isinstance(olla, OllamaProvider)

    # Unknown provider raises error
    with pytest.raises(ProviderError):
        create_provider(Config(provider="unknown"))


class TestProviderBase:
    def test_provider_is_abstract(self):
        """不能直接实例化 LLMProvider"""
        with pytest.raises(TypeError):
            LLMProvider(Config())  # type: ignore


class TestOpenAIProvider:
    @pytest.fixture
    def provider(self) -> OpenAIProvider:
        return OpenAIProvider(
            Config(
                api_key="test-key",
                model="gpt-4o-mini",
            )
        )

    def test_initialization(self, provider: OpenAIProvider):
        assert provider.model == "gpt-4o-mini"
        assert "test-key" in provider._client.headers["Authorization"]

    def test_build_messages_roundtrip_dict_arguments(self, provider: OpenAIProvider):
        """
        模拟 get_messages 后的数据（arguments 被 normalize 成了 dict）。
        build_messages 必须把 dict arguments 还原为 JSON string，否则 API 会报 400。
        """
        msgs = provider.build_messages([
            Message(role=MessageRole.USER, content="Read the file"),
            Message(
                role=MessageRole.ASSISTANT,
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "read",
                            # 模拟 get_messages 后的 dict 格式
                            "arguments": {"filepath": "test.py"},
                        },
                    }
                ],
            ),
        ])
        assert len(msgs) == 2
        assert msgs[1]["role"] == "assistant"
        tc = msgs[1]["tool_calls"][0]
        assert tc["function"]["name"] == "read"
        # arguments 必须是 JSON string，不能是 dict
        args = tc["function"]["arguments"]
        assert isinstance(args, str), f"Expected string, got {type(args)}: {args}"
        import json
        parsed = json.loads(args)
        assert parsed == {"filepath": "test.py"}

    def test_build_messages_handles_string_arguments(self, provider: OpenAIProvider):
        """String arguments (从 API 直接返回) 保持不变"""
        msgs = provider.build_messages([
            Message(role=MessageRole.ASSISTANT, content="",
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "read",
                        "arguments": '{"filepath": "test.py"}',
                    },
                }]
            ),
        ])
        tc = msgs[0]["tool_calls"][0]
        assert tc["function"]["arguments"] == '{"filepath": "test.py"}'

    def test_build_messages_handles_malformed_string(self, provider: OpenAIProvider):
        """Malformed string arguments 被包装为错误对象"""
        msgs = provider.build_messages([
            Message(role=MessageRole.ASSISTANT, content="",
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "read",
                        "arguments": "{not-json}",
                    },
                }]
            ),
        ])
        tc = msgs[0]["tool_calls"][0]
        args = tc["function"]["arguments"]
        assert isinstance(args, str)
        parsed = json.loads(args)
        assert "_error" in parsed

    @pytest.mark.asyncio
    async def test_complete(self, provider: OpenAIProvider):
        """使用 respx mock 测试 complete"""
        router = respx.mock(using="httpx")
        router.post("https://api.openai.com/v1/chat/completions").respond(
            200,
            json={
                "id": "chatcmpl-123",
                "object": "chat.completion",
                "created": 1677652288,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Hello! How can I help you?",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 8,
                    "total_tokens": 18,
                },
            },
        )
        with router:
            result = await provider.complete([
                Message(role=MessageRole.USER, content="Hi"),
            ])
        assert result.content == "Hello! How can I help you?"
        assert result.usage is not None
        assert result.usage["total_tokens"] == 18

    @pytest.mark.asyncio
    async def test_stream(self, provider: OpenAIProvider):
        """使用 respx mock 测试流式响应"""
        chunks = [
            'data: {"id":"1","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}\n\n',
            'data: {"id":"2","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}\n\n',
            'data: {"id":"3","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}\n\n',
            "data: [DONE]\n\n",
        ]

        router = respx.mock(using="httpx")
        router.post("https://api.openai.com/v1/chat/completions").respond(
            200,
            content="".join(chunks),
            headers={"Content-Type": "text/event-stream"},
        )
        with router:
            collected = []
            async for chunk in provider.stream([
                Message(role=MessageRole.USER, content="Hi"),
            ]):
                collected.append(chunk)

        assert len(collected) == 2
        assert collected[0] == "Hello"
        assert collected[1] == "!"

    @pytest.mark.asyncio
    async def test_complete_with_tool_call(self, provider: OpenAIProvider):
        """测试 LLM 返回工具调用"""
        router = respx.mock(using="httpx")
        router.post("https://api.openai.com/v1/chat/completions").respond(
            200,
            json={
                "id": "chatcmpl-456",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_read",
                                    "type": "function",
                                    "function": {
                                        "name": "read",
                                        "arguments": '{"path": "/tmp/test.txt"}',
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
                Message(role=MessageRole.USER, content="Read the file"),
            ])
        assert result.content == ""
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["function"]["name"] == "read"
        assert (
            result.tool_calls[0]["function"]["arguments"]
            == '{"path": "/tmp/test.txt"}'
        )

    @pytest.mark.asyncio
    async def test_api_error(self, provider: OpenAIProvider):
        """测试 API 错误处理"""
        router = respx.mock(using="httpx")
        router.post("https://api.openai.com/v1/chat/completions").respond(
            401,
            json={"error": {"message": "Invalid API key"}},
        )
        with router:
            with pytest.raises(ProviderError, match="401"):
                await provider.complete([
                    Message(role=MessageRole.USER, content="Hi"),
                ])


class TestAnthropicProvider:
    @pytest.fixture
    def provider(self):
        from cscode.providers.anthropic import AnthropicProvider

        return AnthropicProvider(
            Config(
                api_key="test-key",
                model="claude-sonnet-4-5",
            )
        )

    def test_initialization(self, provider):
        assert provider.model == "claude-sonnet-4-5"
        assert "test-key" in provider._client.headers["x-api-key"]

    @pytest.mark.asyncio
    async def test_complete(self, provider):
        """使用 respx mock 测试 complete"""
        router = respx.mock(using="httpx")
        router.post("https://api.anthropic.com/v1/messages").respond(
            200,
            json={
                "id": "msg_123",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello from Claude!"}],
                "model": "claude-sonnet-4-5",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )
        with router:
            result = await provider.complete([
                Message(role=MessageRole.USER, content="Hi"),
            ])
        assert result.content == "Hello from Claude!"
        assert result.usage is not None

    @pytest.mark.asyncio
    async def test_stream(self, provider):
        """使用 respx mock 测试流式响应"""
        chunks = [
            '{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}\n',
            '{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"!"}}\n',
        ]
        body = (
            "data: "
            + '\n\ndata: '.join(chunks)
            + '\n\ndata: {"type":"message_stop"}\n\n'
        )
        router = respx.mock(using="httpx")
        router.post("https://api.anthropic.com/v1/messages").respond(
            200,
            content=body,
            headers={
                "Content-Type": "text/event-stream",
            },
        )
        with router:
            collected = []
            async for chunk in provider.stream([
                Message(role=MessageRole.USER, content="Hi"),
            ]):
                collected.append(chunk)
        assert len(collected) == 2
        assert collected[0] == "Hello"
        assert collected[1] == "!"


class TestOllamaProvider:
    @pytest.fixture
    def provider(self):
        from cscode.providers.ollama import OllamaProvider

        return OllamaProvider(
            Config(
                model="qwen2.5-coder:7b",
                api_base="http://localhost:11434",
            )
        )

    def test_initialization(self, provider):
        assert provider.model == "qwen2.5-coder:7b"
        assert "localhost:11434" in provider._api_base

    @pytest.mark.asyncio
    async def test_complete(self, provider):
        router = respx.mock(using="httpx")
        router.post("http://localhost:11434/api/chat").respond(
            200,
            json={
                "model": "qwen2.5-coder:7b",
                "message": {"role": "assistant", "content": "Hello from Ollama!"},
            },
        )
        with router:
            result = await provider.complete([
                Message(role=MessageRole.USER, content="Hi"),
            ])
        assert result.content == "Hello from Ollama!"

    @pytest.mark.asyncio
    async def test_stream(self, provider):
        """Ollama 流式响应，每行一个 JSON"""
        lines = [
            '{"message":{"content":"Hello"}}',
            '{"message":{"content":"!"}}',
        ]
        router = respx.mock(using="httpx")
        router.post("http://localhost:11434/api/chat").respond(
            200,
            content="\n".join(lines),
        )
        with router:
            collected = []
            async for chunk in provider.stream([
                Message(role=MessageRole.USER, content="Hi"),
            ]):
                collected.append(chunk)
        assert len(collected) == 2
        assert collected[0] == "Hello"
