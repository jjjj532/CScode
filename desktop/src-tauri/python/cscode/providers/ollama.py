from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from cscode.core.config import Config
from cscode.core.messages import Message
from cscode.providers.base import LLMProvider, LLMResult, ProviderError


class OllamaProvider(LLMProvider):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._api_base = (config.api_base or "http://localhost:11434").rstrip("/")
        self._model = config.model
        self._client = httpx.AsyncClient(
            base_url=self._api_base,
            timeout=httpx.Timeout(300.0),
        )

    @property
    def model(self) -> str:
        return self._model

    def build_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
            result.append(entry)
        return result

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self.build_messages(messages),
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
        return payload

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        payload = self._build_payload(messages, tools, stream=False)
        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"Ollama API error: {e.response.status_code} {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise ProviderError(f"Request failed: {e}") from e

        msg = data.get("message", {})
        return LLMResult(
            content=msg.get("content", ""),
            model=data.get("model", self._model),
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        payload = self._build_payload(messages, tools, stream=True)
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    import json

                    data = json.loads(line)
                    msg = data.get("message", {})
                    content = msg.get("content", "")
                    if content:
                        yield content
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"Ollama API error: {e.response.status_code} {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise ProviderError(f"Request failed: {e}") from e
