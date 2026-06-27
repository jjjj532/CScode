"""Shared types for the LLM layer — LLMRequest, LLMResponse, _ProtocolAdapter.

These types are imported by both client.py and protocol adapters, so they
live in their own module to avoid circular imports.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from cscode.llm.route import Route
from cscode.schema.events import LLMEvent
from cscode.schema.ids import ModelID
from cscode.schema.messages import Message
from cscode.schema.options import GenerationOptions, ProviderOptions
from cscode.schema.tool import ToolDefinition


@dataclass
class LLMRequest:
    """A request to an LLM, with all parameters needed for generation."""

    model: ModelID
    """Model identifier to use for generation."""

    messages: tuple[Message, ...]
    """Conversation messages (role + parts)."""

    tools: tuple[ToolDefinition, ...] = ()
    """Tool definitions the LLM may use."""

    options: GenerationOptions = field(default_factory=GenerationOptions)
    """Generation parameters (temperature, max_tokens, etc.)."""

    provider_options: ProviderOptions = field(default_factory=ProviderOptions)
    """Provider-specific options."""


@dataclass
class LLMResponse:
    """A non-streaming response from an LLM."""

    content: str
    """Generated text content."""

    finish_reason: str = ""
    """Why generation finished ('stop', 'tool_use', 'length')."""

    usage: dict[str, int] | None = None
    """Token usage if reported by the provider."""

    model: str = ""
    """Model that generated this response."""


class _ProtocolAdapter:
    """Internal interface for protocol-specific adapters.

    Each protocol adapter knows how to:
    1. Build the HTTP request payload from an LLMRequest
    2. Parse the HTTP response into LLMEvents (streaming)
    3. Parse the HTTP response into a dict (non-streaming)
    """

    async def complete(
        self,
        route: Route,
        request: LLMRequest,
        client: httpx.AsyncClient,
    ) -> dict[str, Any]:
        """Non-streaming completion.

        Returns a raw dict with keys: content, finish_reason, usage, model.
        """
        raise NotImplementedError

    async def stream(
        self,
        route: Route,
        request: LLMRequest,
        client: httpx.AsyncClient,
    ) -> AsyncIterator[LLMEvent]:
        """Streaming completion.

        Yields LLMEvents as they arrive.
        """
        raise NotImplementedError
        # pragma: no cover
        yield  # pylint: disable=unreachable
