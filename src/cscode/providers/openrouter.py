from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from cscode.core.config import Config
from cscode.core.errors import ProviderError
from cscode.core.messages import Message
from cscode.providers.base import LLMProvider, LLMResult
from cscode.providers.openai import OpenAIProvider
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class OpenRouterProvider(LLMProvider):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._api_key = config.api_key or ""
        self._model = config.model or "openai/gpt-4o"
        logger.info("OpenRouterProvider initialized: model=%s", self._model)
        self._openai = OpenAIProvider(config)

    @property
    def model(self) -> str:
        return self._model

    def build_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        return self._openai.build_messages(messages)

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        logger.info("OpenRouter.complete: model=%s messages=%d", self._model, len(messages))
        body = {"model": self._model, "messages": self.build_messages(messages)}
        if tools:
            body["tools"] = tools

        async with httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://cscode.dev",
                "X-Title": "CScode",
            },
            timeout=httpx.Timeout(600.0),
        ) as client:
            try:
                response = await client.post("/chat/completions", json=body)
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                msg = choice["message"]
                tool_calls = msg.get("tool_calls")
                if tool_calls is not None and len(tool_calls) == 0:
                    tool_calls = None
                finish_reason = choice.get("finish_reason", "")
                logger.debug("OpenRouter response: finish_reason=%s", finish_reason)
                return LLMResult(
                    content=msg.get("content", ""),
                    tool_calls=tool_calls,
                    usage=data.get("usage"),
                    model=data.get("model", self._model),
                    finish_reason=finish_reason,
                )
            except httpx.HTTPStatusError as e:
                logger.error("OpenRouter HTTP %d: %s", e.response.status_code, e.response.text[:200])
                raise ProviderError(f"OpenRouter API error: {e.response.status_code} - {e.response.text}") from e
            except httpx.RequestError as e:
                logger.error("OpenRouter request failed: %s", e)
                raise ProviderError(f"OpenRouter request failed: {e}") from e

    def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        raise NotImplementedError("OpenRouter streaming not yet implemented")
