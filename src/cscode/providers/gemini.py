from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from cscode.core.config import Config
from cscode.core.errors import ProviderError
from cscode.core.messages import Message, MessageRole
from cscode.providers.base import LLMProvider, LLMResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class GeminiProvider(LLMProvider):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._api_key = config.api_key or ""
        self._model = config.model or "gemini-2.0-flash"
        logger.info("GeminiProvider initialized: model=%s", self._model)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(600.0),
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
        logger.info("Gemini.complete: model=%s messages=%d", self._model, len(messages))
        body = self.build_messages(messages)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent?key={self._api_key}"

        try:
            response = await self._client.post(url, json=body)
            response.raise_for_status()
            data = response.json()

            candidate = data.get("candidates", [{}])[0]
            content_parts = candidate.get("content", {}).get("parts", [{}])
            text = content_parts[0].get("text", "") if content_parts else ""

            finish_reason = candidate.get("finishReason", "")
            usage = data.get("usageMetadata", {})
            logger.debug("Gemini response: finish_reason=%s usage=%s", finish_reason, usage)
            return LLMResult(
                content=text,
                model=self._model,
                usage=usage,
                finish_reason=finish_reason,
            )
        except httpx.HTTPStatusError as e:
            logger.error("Gemini HTTP %d: %s", e.response.status_code, e.response.text[:200])
            raise ProviderError(f"Gemini API error: {e.response.status_code} - {e.response.text}") from e
        except httpx.RequestError as e:
            logger.error("Gemini request failed: %s", e)
            raise ProviderError(f"Gemini request failed: {e}") from e

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        logger.info("Gemini.stream: model=%s messages=%d", self._model, len(messages))
        body = self.build_messages(messages)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:streamGenerateContent?alt=sse&key={self._api_key}"

        try:
            async with self._client.stream("POST", url, json=body) as response:
                response.raise_for_status()
                chunk_count = 0
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if not data_str.strip():
                            continue
                        import json
                        data = json.loads(data_str)
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                text = parts[0].get("text", "")
                                if text:
                                    chunk_count += 1
                                    yield text
                logger.debug("Gemini stream complete: %d chunks", chunk_count)
        except httpx.HTTPStatusError as e:
            logger.error("Gemini stream HTTP %d: %s", e.response.status_code, e.response.text[:200])
            raise ProviderError(
                f"Gemini API error: {e.response.status_code} {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            logger.error("Gemini stream request failed: %s", e)
            raise ProviderError(f"Request failed: {e}") from e
