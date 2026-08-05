"""LLMClient — standardized generate/stream interface over any Route.

The LLMClient is the primary entry point for LLM interactions in the
new architecture. It uses a Route to determine the wire protocol, then
dispatches to the appropriate protocol adapter.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from cscode.llm.protocols.openai_chat import OpenAIProtocolAdapter
from cscode.llm.route import ProtocolID, Route
from cscode.llm.types import LLMRequest, LLMResponse, _ProtocolAdapter
from cscode.schema.errors import LLMError, LLMErrorReason
from cscode.schema.events import Error as LLMEventError
from cscode.schema.events import LLMEvent, Pending
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class LLMClient:
    """Standardized LLM client that dispatches to protocol-specific adapters.

    The client is stateless — it holds a Route (which defines HOW to
    communicate) and an optional httpx client. Each call to generate()
    or stream() creates a new request.
    """

    def __init__(
        self,
        route: Route,
        httpx_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._route = route
        self._client = httpx_client

    @property
    def route(self) -> Route:
        """The route this client is configured with."""
        return self._route

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Non-streaming generation.

        Sends a request to the provider and waits for the full response.
        """
        logger.info("LLM generate: model=%s messages=%d", request.model, len(request.messages))
        adapter = self._get_adapter()
        raw = await adapter.complete(self._route, request, self._http_client)
        logger.debug("LLM generate complete: finish_reason=%s", raw.get("finish_reason", "?"))
        return self._parse_complete(raw)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        """Streaming generation.

        Yields LLMEvents as they arrive from the provider.
        """
        logger.info("LLM stream: model=%s messages=%d", request.model, len(request.messages))
        adapter = self._get_adapter()
        yield Pending()

        try:
            async for event in adapter.stream(self._route, request, self._http_client):
                yield event
        except LLMError as e:
            logger.error("LLM stream error: %s", e)
            yield LLMEventError(error=e)
        except httpx.HTTPStatusError as e:
            try:
                err_text = e.response.text[:500]
            except Exception:
                err_text = f"HTTP {e.response.status_code}"
            logger.error("LLM stream HTTP %d: %s", e.response.status_code, err_text[:200])
            yield LLMEventError(
                error=LLMError(
                    module="LLMClient",
                    method="stream",
                    reason=LLMErrorReason.PROVIDER_INTERNAL,
                    message=f"HTTP {e.response.status_code}: {err_text}",
                    retryable=e.response.status_code >= 500,
                )
            )
        except httpx.RequestError as e:
            logger.error("LLM stream request failed: %s", e)
            yield LLMEventError(
                error=LLMError(
                    module="LLMClient",
                    method="stream",
                    reason=LLMErrorReason.TRANSPORT,
                    message=f"Request failed: {type(e).__name__}: {e!r}",
                )
            )

    @property
    def _http_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(600.0))
        return self._client

    def _get_adapter(self) -> _ProtocolAdapter:
        """Resolve the protocol adapter for the current route."""
        logger.debug("Protocol adapter resolve: %s for route=%s", self._route.protocol, self._route.id)
        match self._route.protocol:
            case ProtocolID.OPENAI_CHAT | ProtocolID.OPENAI_COMPATIBLE:
                return OpenAIProtocolAdapter()
            case ProtocolID.ANTHROPIC_MESSAGES:
                from cscode.llm.protocols.anthropic_messages import AnthropicProtocolAdapter
                return AnthropicProtocolAdapter()
            case ProtocolID.OPENAI_RESPONSES:
                from cscode.llm.protocols.openai_responses import OpenAIResponsesProtocolAdapter
                return OpenAIResponsesProtocolAdapter()
            case ProtocolID.GEMINI:
                msg = f"Gemini protocol not yet implemented: {self._route.protocol}"
                raise NotImplementedError(msg)
            case _:
                msg = f"Unsupported protocol: {self._route.protocol}"
                raise ValueError(msg)

    def _parse_complete(self, raw: dict[str, Any]) -> LLMResponse:
        """Parse a non-streaming response from the adapter."""
        return LLMResponse(
            content=raw.get("content", ""),
            finish_reason=raw.get("finish_reason", ""),
            usage=raw.get("usage"),
            model=raw.get("model", self._route.model),
        )
