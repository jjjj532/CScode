"""Provider Caching System — SPEC §3.4

Manages LLM request caching at the provider level. Supports automatic
cache_control marker insertion for protocols that support it (Anthropic,
Bedrock) and a simple TTL-based request cache for manual use.

Cache policy types:
    True/"auto"  → default automatic placement
    False/"none" → no caching
    dict         → explicit per-component policy

Reference: OpenCode packages/llm/src/cache-policy.ts
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Literal

# ─── Cache hint types (SPEC 3.4.2) ───────────────────────────────

CacheHintType = Literal["ephemeral"]
"""Allowed cache hint types — currently only 'ephemeral'."""


@dataclass
class CacheHint:
    """A cache hint to attach to a message or tool definition.

    Attributes:
        type: Hint type ('ephemeral' = reset on each generation).
        ttl_seconds: Optional TTL in seconds (provider-dependent).
    """

    type: CacheHintType = "ephemeral"
    ttl_seconds: int | None = None


# ─── Cache policy type (SPEC 3.4.2) ──────────────────────────────

# True/"auto"  → automatic placement
# False/"none" → no caching
# dict         → explicit per-component policy
CachePolicy = bool | str | dict[
    Literal["tools", "system", "messages", "ttl_seconds"],
    bool | str | int,
]


# ─── Protocol cache support matrix (SPEC 3.4.2) ──────────────────

PROTOCOL_CACHE_SUPPORT: dict[str, bool] = {
    "anthropic-messages": True,   # cache_control markers
    "bedrock-converse": True,     # cachePoint blocks
    "openai-chat": False,         # server-side implicit
    "openai-responses": False,    # server-side implicit
    "gemini": False,              # implicit + out-of-band
}
"""Maps protocol ID → whether client-side cache markers are supported."""


# ─── apply_cache_policy (SPEC 3.4.2) ─────────────────────────────


def apply_cache_policy(request: dict[str, Any], protocol_id: str) -> dict[str, Any]:
    """Apply automatic cache policy to a request.

    Strategy (matches OpenCode behaviour):
    1. Last tool definition  → cache_control { type: "ephemeral" }
    2. Last system message   → cache_control { type: "ephemeral" }
    3. Latest user message   → cache_control { type: "ephemeral" }

    Args:
        request: The request dict (will be modified in-place).
        protocol_id: Protocol identifier (e.g. 'anthropic-messages').

    Returns:
        The same request dict with cache_control markers added
        (or unchanged if protocol doesn't support caching).
    """
    if not PROTOCOL_CACHE_SUPPORT.get(protocol_id, False):
        return request

    messages = request.get("messages", [])
    if not messages:
        return request

    # 1. Cache last tool definition
    tools = request.get("tools", [])
    if tools:
        tools[-1]["cache_control"] = {"type": "ephemeral"}

    # 2. Cache last system message
    system_indices = [i for i, m in enumerate(messages) if m.get("role") == "system"]
    if system_indices:
        messages[system_indices[-1]]["cache_control"] = {"type": "ephemeral"}

    # 3. Cache latest user message
    user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if user_indices:
        messages[user_indices[-1]]["cache_control"] = {"type": "ephemeral"}

    return request


# ─── Request-level cache ─────────────────────────────────────────


@dataclass
class _CacheEntry:
    """Internal cache entry with TTL tracking."""

    value: Any
    expires_at: float

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class RequestCache:
    """Simple TTL-based request cache for LLM responses.

    Uses a dict-based store with LRU-style eviction when max_size is reached.
    Cache keys are SHA-256 hashes of the serialized request data.
    """

    def __init__(
        self,
        enabled: bool = False,
        ttl: int = 300,
        max_size: int = 100,
    ) -> None:
        """Initialize the cache.

        Args:
            enabled: Whether caching is active.
            ttl: Default TTL in seconds for new entries.
            max_size: Maximum number of entries before eviction.
        """
        self.enabled = enabled
        self.ttl = ttl
        self.max_size = max_size
        self._cache: dict[str, _CacheEntry] = {}

    def _make_key(self, data: dict[str, Any]) -> str:
        """Generate a cache key from request data."""
        content = json.dumps(data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(self, data: dict[str, Any]) -> Any | None:
        """Get cached response for a request.

        Returns None if disabled, cache miss, or entry expired.
        """
        if not self.enabled:
            return None
        key = self._make_key(data)
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._cache[key]
            return None
        return entry.value

    def set(self, data: dict[str, Any], value: Any) -> None:
        """Cache a response for a request."""
        if not self.enabled:
            return
        # Evict oldest if at capacity
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k].expires_at)
            del self._cache[oldest_key]
        key = self._make_key(data)
        self._cache[key] = _CacheEntry(value, time.time() + self.ttl)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
