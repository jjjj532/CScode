from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from cscode.core.config import Config
from cscode.core.messages import Message, MessageRole
from cscode.providers.base import LLMProvider, LLMResult, ProviderError


class OpenAIProvider(LLMProvider):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._api_base = config.api_base or "https://api.openai.com/v1"
        self._model = config.model
        self._api_key = config.api_key
        print(f"DEBUG OpenAIProvider: api_base={self._api_base}, api_key={self._api_key[:20] if self._api_key else 'None'}...")
        self._client = httpx.AsyncClient(
            base_url=self._api_base,
            headers={
                "Authorization": f"Bearer {config.api_key}",
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
            entry: dict[str, Any] = {"role": msg.role.value}
            if msg.role == MessageRole.TOOL:
                entry["content"] = msg.content
                entry["tool_call_id"] = msg.tool_call_id
            elif msg.tool_calls:
                entry["content"] = msg.content or ""
                entry["tool_calls"] = msg.tool_calls
            else:
                entry["content"] = msg.content
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
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
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
        print(f"DEBUG: Sending request to {self._api_base}/chat/completions with model {self._model}")
        print(f"DEBUG: Payload: {payload}")
        try:
            response = await self._client.post("/chat/completions", json=payload)
            print(f"DEBUG: Response status: {response.status_code}")
            print(f"DEBUG: Response body: {response.text[:500]}")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            print(f"DEBUG HTTPStatusError: {e.response.status_code} {e.response.text}")
            raise ProviderError(
                f"OpenAI API error: {e.response.status_code} {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            print(f"DEBUG RequestError: {e}")
            raise ProviderError(f"Request failed: {e}") from e

        choice = data["choices"][0]
        msg = choice["message"]
        return LLMResult(
            content=msg.get("content") or "",
            tool_calls=msg.get("tool_calls"),
            usage=data.get("usage"),
            model=data.get("model", self._model),
            finish_reason=choice.get("finish_reason", ""),
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        payload = self._build_payload(messages, tools, stream=True)
        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        import json

                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"OpenAI API error: {e.response.status_code} {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise ProviderError(f"Request failed: {e}") from e
