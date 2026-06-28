"""Route system — maps provider+model to a concrete protocol endpoint.

Architecture:
  Route = Protocol + Endpoint + Auth + Framing

  A Route fully describes how to communicate with a specific LLM provider's API:
  - Which wire protocol (OpenAI Chat, Anthropic Messages, Gemini)
  - Which URL to send requests to
  - How to authenticate (Bearer token, API key header, none)
  - How to frame requests (SSE streaming vs JSON)

Usage:
    route = resolve_route("openai", "gpt-4o")
    client = route.create_client()
    async for event in client.stream(request):
        ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from cscode.schema.ids import ModelID, ProviderID
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

# ─── Auth ────────────────────────────────────────────────────────────


class AuthScheme(StrEnum):
    """Authentication schemes supported by the Route system."""

    BEARER = "bearer"
    """HTTP Authorization: Bearer <token>. Used by OpenAI, OpenRouter, etc."""

    HEADER = "header"
    """Custom header authentication. Used by Anthropic (x-api-key)."""

    NONE = "none"
    """No authentication (e.g. local Ollama)."""


@dataclass(frozen=True, slots=True)
class Auth:
    """Authentication configuration for a Route."""

    scheme: AuthScheme
    """Which authentication scheme to use."""

    value: str = ""
    """The credential value (API key, token, etc.). Empty if scheme=NONE."""

    header_name: str = ""
    """Custom header name for HEADER scheme (e.g. 'x-api-key')."""

    @classmethod
    def bearer(cls, token: str) -> Auth:
        """Create a Bearer token auth."""
        return cls(scheme=AuthScheme.BEARER, value=token)

    @classmethod
    def header(cls, name: str, value: str) -> Auth:
        """Create a custom header auth."""
        return cls(scheme=AuthScheme.HEADER, value=value, header_name=name)

    @classmethod
    def none(cls) -> Auth:
        """Create a no-auth configuration."""
        return cls(scheme=AuthScheme.NONE)


# ─── Framing ─────────────────────────────────────────────────────────


class FramingMode(StrEnum):
    """How the provider frames streaming responses."""

    SSE = "sse"
    """Server-Sent Events (OpenAI, Anthropic, etc.). Lines prefixed with 'data:'."""

    JSON = "json"
    """Single JSON response (non-streaming)."""


@dataclass(frozen=True, slots=True)
class Framing:
    """Framing configuration for how responses are parsed."""

    mode: FramingMode = FramingMode.SSE
    """Response framing mode."""

    done_token: str = "[DONE]"
    """Token that signals the end of a stream (SSE only)."""

    @classmethod
    def sse(cls, done_token: str = "[DONE]") -> Framing:
        """Server-Sent Events framing."""
        return cls(mode=FramingMode.SSE, done_token=done_token)

    @classmethod
    def json(cls) -> Framing:
        """Single JSON response framing."""
        return cls(mode=FramingMode.JSON, done_token="")


# ─── Protocol ────────────────────────────────────────────────────────


class ProtocolID(StrEnum):
    """Supported wire protocols for LLM communication."""

    OPENAI_CHAT = "openai-chat"
    """OpenAI Chat Completions API (/v1/chat/completions)."""

    OPENAI_RESPONSES = "openai-responses"
    """OpenAI Responses API (/v1/responses)."""

    ANTHROPIC_MESSAGES = "anthropic-messages"
    """Anthropic Messages API (/v1/messages)."""

    GEMINI = "gemini"
    """Google Gemini API."""

    OPENAI_COMPATIBLE = "openai-compatible"
    """Any OpenAI-compatible API (Ollama, vLLM, etc.)."""


# ─── Endpoint ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Endpoint:
    """URL endpoint for a Route."""

    base_url: str
    """Base URL of the API (e.g. 'https://api.openai.com/v1')."""

    path: str = ""
    """Path relative to base URL (e.g. '/chat/completions'). If empty, the
    protocol's default path is used."""

    @property
    def url(self) -> str:
        """Full URL: base_url + path."""
        if self.path:
            return f"{self.base_url.rstrip('/')}/{self.path.lstrip('/')}"
        return self.base_url

    @classmethod
    def from_base(cls, base_url: str) -> Endpoint:
        """Create an endpoint from a base URL (protocol determines the path)."""
        return cls(base_url=base_url)

    @classmethod
    def from_full(cls, base_url: str, path: str) -> Endpoint:
        """Create an endpoint with an explicit path override."""
        return cls(base_url=base_url, path=path)


# ─── Route ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Route:
    """A complete route definition for communicating with an LLM provider.

    A Route fully describes:
    - Which wire protocol to use (e.g. openai-chat)
    - Where to send requests (endpoint URL)
    - How to authenticate
    - How to frame streaming responses
    """

    id: str
    """Unique route identifier (e.g. 'openai/gpt-4o', 'anthropic/claude-sonnet-4')."""

    protocol: ProtocolID
    """Wire protocol for this route."""

    endpoint: Endpoint
    """API endpoint URL."""

    auth: Auth
    """Authentication configuration."""

    framing: Framing = field(default_factory=Framing.sse)
    """Response framing configuration (default: SSE)."""

    model: ModelID = ModelID("")
    """The model identifier sent in API requests. When empty, the caller
    must provide it at request time."""


# ─── Route Resolution ───────────────────────────────────────────────


def resolve_route(
    provider: ProviderID,
    model: ModelID,
    api_key: str = "",
    api_base: str = "",
) -> Route:
    """Resolve a provider+model pair to a Route configuration.

    This is the main entry point for route resolution. Given a provider
    identifier and model, it returns the Route that describes how to
    communicate with that provider's API.

    Args:
        provider: Provider identifier (e.g. 'openai', 'anthropic').
        model: Model identifier (e.g. 'gpt-4o', 'claude-sonnet-4').
        api_key: API key for authentication.
        api_base: Custom API base URL override.

    Returns:
        A fully configured Route.

    Raises:
        ValueError: If the provider is not recognized.
    """
    provider_lower = provider.lower()
    logger.info("Resolving route: provider=%s model=%s api_base=%s", provider_lower, model, api_base or "default")

    match provider_lower:
        case "openai":
            base = api_base or "https://api.openai.com/v1"
            return Route(
                id=f"openai/{model}",
                protocol=ProtocolID.OPENAI_CHAT,
                endpoint=Endpoint.from_base(base),
                auth=Auth.bearer(api_key),
                model=model,
            )

        case "anthropic":
            base = api_base or "https://api.anthropic.com/v1"
            return Route(
                id=f"anthropic/{model}",
                protocol=ProtocolID.ANTHROPIC_MESSAGES,
                endpoint=Endpoint.from_base(base),
                auth=Auth.header("x-api-key", api_key),
                model=model,
            )

        case "ollama":
            base = api_base or "http://localhost:11434"
            return Route(
                id=f"ollama/{model}",
                protocol=ProtocolID.OPENAI_COMPATIBLE,
                endpoint=Endpoint.from_base(base),
                auth=Auth.none(),
                framing=Framing.sse(),
                model=model,
            )

        case "gemini":
            base = api_base or "https://generativelanguage.googleapis.com/v1beta"
            return Route(
                id=f"gemini/{model}",
                protocol=ProtocolID.GEMINI,
                endpoint=Endpoint.from_base(base),
                auth=Auth.bearer(api_key),
                model=model,
            )

        case "azure":
            base = api_base or "https://{resource}.openai.azure.com"
            return Route(
                id=f"azure/{model}",
                protocol=ProtocolID.OPENAI_CHAT,
                endpoint=Endpoint.from_base(base),
                auth=Auth.header("api-key", api_key),
                model=model,
            )

        case "openrouter":
            base = api_base or "https://openrouter.ai/api/v1"
            return Route(
                id=f"openrouter/{model}",
                protocol=ProtocolID.OPENAI_CHAT,
                endpoint=Endpoint.from_base(base),
                auth=Auth.bearer(api_key),
                model=model,
            )

        case "custom" | "scnet":
            base = api_base or "https://api.openai.com/v1"
            return Route(
                id=f"custom/{model}",
                protocol=ProtocolID.OPENAI_COMPATIBLE,
                endpoint=Endpoint.from_base(base),
                auth=Auth.bearer(api_key),
                model=model,
            )

        case _:
            logger.error("Unknown provider: %s", provider)
            msg = f"Unknown provider: {provider}"
            raise ValueError(msg)
