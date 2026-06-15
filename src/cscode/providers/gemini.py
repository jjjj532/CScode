from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from cscode.core.config import Config
from cscode.core.errors import ProviderError
from cscode.core.messages import Message, MessageRole
from cscode.providers.base import LLMProvider, LLMResult


class GeminiProvider(LLMProvider):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._api_key = config.api_key or ""
        self._model = config.model or "gemini-2.0-flash"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
        )

    @property
    def model(self) -> str:
        return self._model

    def build_messages(self, messages: list[Message]) -> dict[str, Any]:  # type: ignore[override]
        contents = []
        system_prompt = None

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content
                continue
            role = "model" if msg.role in (MessageRole.ASSISTANT,) else "user"
            parts = [{"text": msg.content or ""}]
            contents.append({"role": role, "parts": parts})

        result: dict[str, Any] = {"contents": contents}
        if system_prompt:
            result["system_instruction"] = {"parts": [{"text": system_prompt}]}
        return result

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        body = self.build_messages(messages)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent?key={self._api_key}"

        try:
            response = await self._client.post(url, json=body)
            response.raise_for_status()
            data = response.json()

            candidate = data.get("candidates", [{}])[0]
            content_parts = candidate.get("content", {}).get("parts", [{}])
            text = content_parts[0].get("text", "") if content_parts else ""

            usage = data.get("usageMetadata", {})
            return LLMResult(
                content=text,
                model=self._model,
                usage=usage,
                finish_reason=candidate.get("finishReason", ""),
            )
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"Gemini API error: {e.response.status_code} - {e.response.text}") from e
        except httpx.RequestError as e:
            raise ProviderError(f"Gemini request failed: {e}") from e

    def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        raise NotImplementedError("Gemini streaming not yet implemented")
