# LLM Route System — Protocol/Endpoint/Auth/Framing Four-Axis Architecture
#
# ProtocolID: which wire protocol to use (e.g. openai-chat, anthropic-messages)
# AuthScheme: how to authenticate (bearer, header, none)
# Route:      complete routing config consumed by client.py and protocol adapters
# resolve_route(): factory that maps provider name → Route

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProtocolID(Enum):
    """Identifies the LLM wire protocol format.

    Used by LLMClient._get_adapter() to dispatch to the correct adapter.
    """

    OPENAI_CHAT = "openai-chat"
    """OpenAI /v1/chat/completions format (also used by most compatible APIs)."""

    OPENAI_COMPATIBLE = "openai-compatible"
    """Compatible with OpenAI Chat format but not necessarily OpenAI."""

    ANTHROPIC_MESSAGES = "anthropic-messages"
    """Anthropic /v1/messages format."""

    GEMINI = "gemini"
    """Google Gemini API format."""

    OPENAI_RESPONSES = "openai-responses"
    """OpenAI /v1/responses format (new Responses API)."""


class AuthScheme(Enum):
    """How the provider authenticates requests."""

    NONE = "none"
    """No authentication (e.g. local Ollama)."""

    BEARER = "bearer"
    """Authorization: Bearer <token> (most OpenAI-compatible APIs)."""

    HEADER = "header"
    """Custom header (e.g. Anthropic's x-api-key)."""


@dataclass
class EndpointInfo:
    """Where to send the request."""

    url: str
    """Full endpoint URL (e.g. https://api.openai.com/v1/chat/completions)."""


@dataclass
class AuthInfo:
    """How to authenticate the request."""

    scheme: AuthScheme
    """Authentication scheme."""

    value: str
    """Token, API key, or secret value."""

    header_name: str = "Authorization"
    """HTTP header name (for HEADER scheme; default is for BEARER)."""


@dataclass
class Route:
    """Complete routing configuration for an LLM provider.

    Combines all four axes:
    - Protocol: what wire format (openai-chat, anthropic-messages, …)
    - Endpoint: where to send the HTTP request
    - Auth:     how to authenticate
    - Framing:  (implicit — JSON/SSE per protocol)

    Consumers:
    - LLMClient reads .protocol, .model, .endpoint.url, .auth.*
    - Protocol adapters read .endpoint.url, .auth.scheme/.value/.header_name
    """

    id: str
    """Unique route identifier (for logging / debugging)."""

    provider: str
    """Provider name (openai, anthropic, ollama, …)."""

    model: str
    """Model identifier (gpt-4o, claude-3-5-sonnet, …)."""

    protocol: ProtocolID
    """Wire protocol to use for this provider."""

    endpoint: EndpointInfo
    """Where to send the request."""

    auth: AuthInfo
    """How to authenticate."""


# ─── Default endpoint URLs ────────────────────────────────────────

_DEFAULT_ENDPOINTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "ollama": "http://localhost:11434/api/chat",
    "azure": "https://{resource}.openai.azure.com/openai/deployments/{model}/chat/completions",
    "google": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
}

# Provider → ProtocolID mapping
_PROVIDER_PROTOCOLS: dict[str, ProtocolID] = {
    "openai": ProtocolID.OPENAI_CHAT,
    "azure": ProtocolID.OPENAI_CHAT,
    "ollama": ProtocolID.OPENAI_COMPATIBLE,
    "anthropic": ProtocolID.ANTHROPIC_MESSAGES,
    "google": ProtocolID.GEMINI,
    "gemini": ProtocolID.GEMINI,
    "openrouter": ProtocolID.OPENAI_CHAT,
    "groq": ProtocolID.OPENAI_CHAT,
    "together": ProtocolID.OPENAI_CHAT,
    "deepseek": ProtocolID.OPENAI_CHAT,
    "mistral": ProtocolID.OPENAI_CHAT,
    "perplexity": ProtocolID.OPENAI_CHAT,
    "xai": ProtocolID.OPENAI_CHAT,
    "cohere": ProtocolID.OPENAI_CHAT,
}


def resolve_route(
    provider: str,
    model: str,
    api_key: str,
    api_base: str = "",
) -> Route:
    """Create a Route from provider name + model + credentials.

    Args:
        provider: Provider name (openai, anthropic, ollama, …).
        model: Model identifier (gpt-4o, claude-3-5-sonnet, …).
        api_key: API key or token.
        api_base: Optional custom base URL. If empty, uses default.

    Returns:
        A fully configured Route.

    Raises:
        ValueError: If provider is unknown.
    """
    # Resolve protocol
    protocol = _PROVIDER_PROTOCOLS.get(provider)
    if protocol is None:
        msg = f"Unknown provider: {provider!r}"
        raise ValueError(msg)

    # Resolve endpoint URL
    if api_base:
        endpoint_url = _build_endpoint_url(provider, model, api_base)
    else:
        endpoint_url = _build_default_endpoint(provider, model)

    # Resolve auth
    auth = _build_auth(provider, api_key)

    # Generate a stable-ish route ID
    route_id = f"{provider}/{model}".replace(".", "-").replace(":", "-")

    return Route(
        id=route_id,
        provider=provider,
        model=model,
        protocol=protocol,
        endpoint=EndpointInfo(url=endpoint_url),
        auth=auth,
    )


def _build_endpoint_url(provider: str, model: str, api_base: str) -> str:
    """Build endpoint URL from custom api_base.

    If api_base already looks like a full path (contains /v1/ or /api/),
    use it as-is. Otherwise append the default path for the provider.
    """
    base = api_base.rstrip("/")

    # If the base already contains a path segment, use it directly
    if any(segment in base for segment in ("/v1/", "/v2/", "/api/")):
        return base

    # Append default path
    match provider:
        case "openai" | "openrouter" | "groq" | "together" | "deepseek" | "mistral" | "perplexity" | "xai":
            return f"{base}/v1/chat/completions"
        case "anthropic":
            return f"{base}/v1/messages"
        case "ollama":
            return f"{base}/api/chat"
        case "azure":
            return f"{base}/openai/deployments/{model}/chat/completions"
        case _:
            return base


def _build_default_endpoint(provider: str, model: str) -> str:
    """Get default endpoint URL for a provider."""
    default = _DEFAULT_ENDPOINTS.get(provider)
    if default is None:
        msg = f"No default endpoint for provider: {provider!r}"
        raise ValueError(msg)
    if "{model}" in default:
        return default.replace("{model}", model)
    return default


def _build_auth(provider: str, api_key: str) -> AuthInfo:
    """Build authentication config for a provider."""
    match provider:
        case "anthropic":
            return AuthInfo(
                scheme=AuthScheme.HEADER,
                value=api_key,
                header_name="x-api-key",
            )
        case "ollama" | "google" | "gemini":
            return AuthInfo(
                scheme=AuthScheme.NONE,
                value=api_key,
            )
        case _:
            return AuthInfo(
                scheme=AuthScheme.BEARER,
                value=api_key,
            )
