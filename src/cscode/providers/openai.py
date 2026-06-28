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


class OpenAIProvider(LLMProvider):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._api_base = config.api_base or "https://api.openai.com/v1"
        self._model = config.model
        self._api_key = config.api_key or ""
        logger.info("OpenAIProvider initialized: api_base=%s model=%s", self._api_base, self._model)
        self._client = httpx.AsyncClient(
            base_url=self._api_base,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            } if config.api_key else {
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(600.0),
        )

    @property
    def model(self) -> str:
        return self._model

    def build_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        import json
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role.value}
            if msg.role == MessageRole.TOOL:
                entry["content"] = msg.content
                entry["tool_call_id"] = msg.tool_call_id
            elif msg.tool_calls:
                entry["content"] = msg.content or ""
                normalized_tool_calls = []
                for tc in msg.tool_calls:
                    tc_copy = dict(tc)
                    if "function" in tc_copy:
                        func = dict(tc_copy["function"])
                        if "arguments" in func:
                            args = func["arguments"]
                            if isinstance(args, dict):
                                func["arguments"] = json.dumps(args, ensure_ascii=False)
                            elif isinstance(args, str):
                                try:
                                    json.loads(args)
                                except json.JSONDecodeError:
                                    func["arguments"] = json.dumps({"_error": "invalid JSON in arguments", "_raw": args}, ensure_ascii=False)
                            else:
                                func["arguments"] = json.dumps(str(args), ensure_ascii=False)
                        tc_copy["function"] = func
                    normalized_tool_calls.append(tc_copy)
                entry["tool_calls"] = normalized_tool_calls
            elif msg.role == MessageRole.USER and msg.image_attachments:
                content_parts: list[dict[str, Any]] = []
                if msg.content:
                    content_parts.append({"type": "text", "text": msg.content})
                for img in msg.image_attachments:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": img.data_uri, "detail": "auto"},
                    })
                entry["content"] = content_parts
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
        logger.debug("Building payload: model=%s messages=%d tools=%d stream=%s", self._model, len(messages), len(tools) if tools else 0, stream)
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
        logger.info("OpenAI.complete: model=%s messages=%d", self._model, len(messages))
        payload = self._build_payload(messages, tools, stream=False)
        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error("OpenAI HTTP %d: %s", e.response.status_code, e.response.text[:200])
            raise ProviderError(
                f"OpenAI API error: {e.response.status_code} {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            logger.error("OpenAI request failed: %s", e)
            raise ProviderError(f"Request failed: {e}") from e

        choice = data["choices"][0]
        msg = choice["message"]
        tool_calls = msg.get("tool_calls")
        if tool_calls is not None and len(tool_calls) == 0:
            tool_calls = None
        finish_reason = choice.get("finish_reason", "")
        usage = data.get("usage")
        logger.debug("OpenAI response: finish_reason=%s usage=%s", finish_reason, usage)
        return LLMResult(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            usage=usage,
            model=data.get("model", self._model),
            finish_reason=finish_reason,
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        logger.info("OpenAI.stream: model=%s messages=%d", self._model, len(messages))
        payload = self._build_payload(messages, tools, stream=True)
        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                chunk_count = 0
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            logger.debug("OpenAI stream complete: %d chunks", chunk_count)
                            break
                        import json

                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                chunk_count += 1
                                yield content
        except httpx.HTTPStatusError as e:
            logger.error("OpenAI stream HTTP %d: %s", e.response.status_code, e.response.text[:200])
            raise ProviderError(
                f"OpenAI API error: {e.response.status_code} {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            logger.error("OpenAI stream request failed: %s", e)
            raise ProviderError(f"Request failed: {e}") from e
