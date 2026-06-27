"""Generation options and provider configuration.

These types control how the LLM generates responses.
They are passed through to the Route system and ultimately
to the provider API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class GenerationOptions:
    """Parameters controlling LLM generation behavior.

    All fields are optional — the provider uses defaults when omitted.
    """

    temperature: float | None = None
    """Sampling temperature (0.0-2.0). Higher = more random."""

    top_p: float | None = None
    """Nucleus sampling threshold (0.0-1.0)."""

    top_k: int | None = None
    """Top-K sampling — only sample from the K most likely tokens."""

    max_tokens: int | None = None
    """Maximum tokens to generate in the response."""

    stop: tuple[str, ...] = ()
    """Sequences that stop generation. Empty tuple = no custom stops."""

    seed: int | None = None
    """Deterministic seed for reproducible generation (when supported)."""


@dataclass(frozen=True, slots=True)
class ProviderOptions:
    """Provider-specific options passed alongside generation parameters.

    These are passed through verbatim to the corresponding provider
    adapter. Keys follow the provider's API field names.
    """

    reasoning_effort: Literal["low", "medium", "high"] | None = None
    """Anthropic/OpenAI reasoning effort level."""

    store: bool | None = None
    """Whether to store the conversation on the provider side."""

    metadata: dict[str, str] = field(default_factory=dict)
    """Arbitrary metadata attached to the request."""

    extra: dict[str, object] = field(default_factory=dict)
    """Any other provider-specific options (forwarded verbatim)."""


@dataclass(frozen=True, slots=True)
class CachePolicy:
    """Control how provider-side prompt caching is used.

    Provider-side caching reduces latency and cost by reusing
    cached prefixes across requests.
    """

    enabled: bool = True
    """Enable caching (default: True)."""

    breakpoints: tuple[int, ...] = ()
    """Message indices at which to insert cache breakpoints.

    For Anthropic: insert cache_control after messages at these indices.
    Empty tuple = automatic (let the provider decide).
    """
