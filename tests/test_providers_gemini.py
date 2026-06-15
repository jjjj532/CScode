from __future__ import annotations

import pytest
import respx

from cscode.core.config import Config
from cscode.core.errors import ProviderError
from cscode.core.messages import Message, MessageRole
from cscode.providers.gemini import GeminiProvider


class TestGeminiProvider:
    @pytest.fixture
    def provider(self) -> GeminiProvider:
        return GeminiProvider(
            Config(
                api_key="test-key",
                model="gemini-2.0-flash",
            )
        )

    def test_initialization(self, provider: GeminiProvider) -> None:
        assert provider.model == "gemini-2.0-flash"

    def test_build_messages_simple(self, provider: GeminiProvider) -> None:
        msgs = [
            Message(role=MessageRole.USER, content="Hello"),
        ]
        result = provider.build_messages(msgs)
        assert "contents" in result
        assert len(result["contents"]) == 1
        assert result["contents"][0]["role"] == "user"
        assert result["contents"][0]["parts"][0]["text"] == "Hello"

    def test_build_messages_with_system(self, provider: GeminiProvider) -> None:
        msgs = [
            Message(role=MessageRole.SYSTEM, content="You are helpful."),
            Message(role=MessageRole.USER, content="Hi"),
        ]
        result = provider.build_messages(msgs)
        assert "system_instruction" in result
        assert result["system_instruction"]["parts"][0]["text"] == "You are helpful."
        assert len(result["contents"]) == 1
        assert result["contents"][0]["parts"][0]["text"] == "Hi"

    def test_build_messages_assistant(self, provider: GeminiProvider) -> None:
        msgs = [
            Message(role=MessageRole.ASSISTANT, content="Sure!"),
        ]
        result = provider.build_messages(msgs)
        assert result["contents"][0]["role"] == "model"

    @pytest.mark.asyncio
    async def test_complete(self, provider: GeminiProvider) -> None:
        router = respx.mock(using="httpx")
        router.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=test-key"
        ).respond(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Hello from Gemini!"}],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 5,
                    "totalTokenCount": 15,
                },
            },
        )
        with router:
            result = await provider.complete([
                Message(role=MessageRole.USER, content="Hi"),
            ])
        assert result.content == "Hello from Gemini!"
        assert result.model == "gemini-2.0-flash"
        assert result.usage is not None
        assert result.usage["totalTokenCount"] == 15

    @pytest.mark.asyncio
    async def test_api_error(self, provider: GeminiProvider) -> None:
        router = respx.mock(using="httpx")
        router.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=test-key"
        ).respond(400, json={"error": {"message": "Bad request"}})
        with router:
            with pytest.raises(ProviderError, match="400"):
                await provider.complete([
                    Message(role=MessageRole.USER, content="Hi"),
                ])
