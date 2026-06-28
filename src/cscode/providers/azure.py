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


class AzureProvider(OpenAIProvider):
    def __init__(self, config: Config) -> None:
        if not config.api_base:
            raise ProviderError("Azure OpenAI requires api_base (e.g. https://your-resource.openai.azure.com)")
        LLMProvider.__init__(self, config)
        self._api_base = config.api_base.rstrip("/")
        self._model = config.model
        self._api_key = config.api_key or ""
        deployment = config.model
        self._url = f"{self._api_base}/openai/deployments/{deployment}/chat/completions?api-version=2024-02-15-preview"
        logger.info("AzureProvider initialized: endpoint=%s model=%s", self._api_base, self._model)
        self._client = httpx.AsyncClient(
            headers={
                "api-key": f"{config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(600.0),
        )

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        logger.info("Azure.complete: model=%s messages=%d", self._model, len(messages))
        body: dict[str, Any] = {
            "model": self._model,
            "messages": self.build_messages(messages),
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
        }
        if tools:
            body["tools"] = tools

        try:
            response = await self._client.post(self._url, json=body)
            response.raise_for_status()
            data = response.json()
            return self._parse_response(data)
        except httpx.HTTPStatusError as e:
            logger.error("Azure HTTP %d: %s", e.response.status_code, e.response.text[:200])
            raise ProviderError(f"Azure API error: {e.response.status_code} - {e.response.text}") from e
        except httpx.RequestError as e:
            logger.error("Azure request failed: %s", e)
            raise ProviderError(f"Azure request failed: {e}") from e

    def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        raise NotImplementedError("Azure streaming not yet implemented")

    def _parse_response(self, data: dict[str, Any]) -> LLMResult:
        choice = data["choices"][0]
        msg = choice["message"]
        tool_calls = msg.get("tool_calls")
        if tool_calls is not None and len(tool_calls) == 0:
            tool_calls = None
        return LLMResult(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            usage=data.get("usage"),
            model=data.get("model", self._model),
            finish_reason=choice.get("finish_reason", ""),
        )

    def build_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        return OpenAIProvider.build_messages(self, messages)
