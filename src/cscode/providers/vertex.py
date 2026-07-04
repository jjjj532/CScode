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


class VertexProvider(LLMProvider):
    """Google Vertex AI provider via REST API.

    Uses the ``google-auth`` library for authentication or an API key
    set in ``config.api_key`` for the lightweight endpoint.

    API docs: https://cloud.google.com/vertex-ai/generative-ai/docs
    """

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._project = config.api_base or ""
        self._location = "us-central1"
        if config.model and config.model != "gpt-4o":
            self._model = config.model
        else:
            self._model = "gemini-2.0-flash-001"
        self._api_key = config.api_key or ""
        logger.info(
            "VertexProvider initialized: project=%s model=%s",
            self._project,
            self._model,
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

    async def _get_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["x-goog-api-key"] = self._api_key
        else:
            try:
                import google.auth  # type: ignore[import-not-found]
                from google.auth.transport.requests import Request  # type: ignore[import-not-found]

                credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                credentials.refresh(Request())
                headers["Authorization"] = f"Bearer {credentials.token}"
            except ImportError:
                raise ProviderError(
                    "Vertex provider requires google-auth: pip install google-auth"
                ) from None
        return headers

    def _build_url(self) -> str:
        if self._project:
            return (
                f"https://{self._location}-aiplatform.googleapis.com/v1/"
                f"projects/{self._project}/locations/{self._location}/"
                f"publishers/google/models/{self._model}:generateContent"
            )
        # API key only endpoint
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent"
        )

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        logger.info("Vertex.complete: model=%s messages=%d", self._model, len(messages))
        body = self.build_messages(messages)
        url = self._build_url()
        if self._api_key and not self._project:
            url = f"{url}?key={self._api_key}"

        headers = await self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
                response = await client.post(url, json=body, headers=headers)
                response.raise_for_status()
                data = response.json()

            candidate = data.get("candidates", [{}])[0]
            content_parts = candidate.get("content", {}).get("parts", [{}])
            text = content_parts[0].get("text", "") if content_parts else ""
            finish_reason = candidate.get("finishReason", "")
            usage = data.get("usageMetadata", {})

            logger.debug("Vertex response: finish_reason=%s", finish_reason)
            return LLMResult(
                content=text,
                model=self._model,
                usage=usage,
                finish_reason=finish_reason,
            )
        except httpx.HTTPStatusError as e:
            logger.error("Vertex HTTP %d: %s", e.response.status_code, e.response.text[:200])
            raise ProviderError(f"Vertex API error: {e.response.status_code} - {e.response.text}") from e
        except httpx.RequestError as e:
            logger.error("Vertex request failed: %s", e)
            raise ProviderError(f"Vertex request failed: {e}") from e

    def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        raise NotImplementedError("Vertex streaming not yet implemented")


