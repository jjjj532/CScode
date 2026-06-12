from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from cscode.core.config import Config
from cscode.core.messages import Message, MessageRole
from cscode.providers.base import LLMProvider, LLMResult, ProviderError


class AnthropicProvider(LLMProvider):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._api_base = config.api_base or "https://api.anthropic.com/v1"
        self._model = config.model
        self._client = httpx.AsyncClient(
            base_url=self._api_base,
            headers={
                "x-api-key": config.api_key or "",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(120.0),
        )

    @property
    def model(self) -> str:
        return self._model

    def build_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                continue
            entry: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
            result.append(entry)
        return result

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        system_prompt = next((m.content for m in messages if m.role == MessageRole.SYSTEM), None)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self.build_messages(messages),
            "max_tokens": self.config.max_tokens,
            "stream": stream,
        }
        if system_prompt:
            payload["system"] = system_prompt
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
            response = await self._client.post("/messages", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"Anthropic API error: {e.response.status_code} {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise ProviderError(f"Request failed: {e}") from e

        content_text = ""
        content_blocks = data.get("content", [])
        for block in content_blocks:
            if block.get("type") == "text":
                content_text += block.get("text", "")

        usage = data.get("usage", {})
        if "input_tokens" in usage:
            usage["prompt_tokens"] = usage.pop("input_tokens")
        if "output_tokens" in usage:
            usage["completion_tokens"] = usage.pop("output_tokens")

        return LLMResult(
            content=content_text,
            usage=usage,
            model=data.get("model", self._model),
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        payload = self._build_payload(messages, tools, stream=True)
        try:
            async with self._client.stream("POST", "/messages", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if not data_str.strip():
                        continue
                    import json

                    data = json.loads(data_str)
                    if data.get("type") == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield text
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"Anthropic API error: {e.response.status_code} {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise ProviderError(f"Request failed: {e}") from e
