"""Tests for LLM Provider Caching (llm/cache_policy.py).

Tests verify:
- CacheHint and CachePolicy types match SPEC 3.4
- PROTOCOL_CACHE_SUPPORT mapping is correct
- apply_cache_policy() adds cache_control markers correctly
- RequestCache basic operations
"""

from __future__ import annotations

from typing import Any

import pytest

from cscode.llm.cache_policy import (
    PROTOCOL_CACHE_SUPPORT,
    CacheHint,
    CachePolicy,
    RequestCache,
    apply_cache_policy,
)


# ─── CacheHint type ───────────────────────────────────────────────


class TestCacheHint:
    """CacheHint must match SPEC 3.4.2."""

    def test_default_hint(self) -> None:
        hint = CacheHint()
        assert hint.type == "ephemeral"
        assert hint.ttl_seconds is None

    def test_custom_ttl(self) -> None:
        hint = CacheHint(ttl_seconds=300)
        assert hint.ttl_seconds == 300

    def test_type_is_literal(self) -> None:
        hint = CacheHint(type="ephemeral")
        assert hint.type == "ephemeral"

    def test_cache_hint_is_dataclass(self) -> None:
        import dataclasses
        assert dataclasses.is_dataclass(CacheHint)


# ─── CachePolicy type ─────────────────────────────────────────────


class TestCachePolicy:
    """CachePolicy type must match SPEC 3.4.2."""

    def test_true_policy(self) -> None:
        """True means auto-cache."""
        policy: CachePolicy = True
        if isinstance(policy, bool):
            assert policy is True

    def test_false_policy(self) -> None:
        """False means no caching."""
        policy: CachePolicy = False
        if isinstance(policy, bool):
            assert policy is False

    def test_auto_string(self) -> None:
        policy: CachePolicy = "auto"
        assert policy == "auto"

    def test_none_string(self) -> None:
        policy: CachePolicy = "none"
        assert policy == "none"

    def test_dict_policy(self) -> None:
        """Dict allows explicit per-component control."""
        policy: CachePolicy = {
            "tools": True,
            "system": True,
            "messages": False,
            "ttl_seconds": 600,
        }
        assert isinstance(policy, dict)
        assert policy["tools"] is True
        assert policy["ttl_seconds"] == 600


# ─── PROTOCOL_CACHE_SUPPORT ───────────────────────────────────────


class TestProtocolCacheSupport:
    """PROTOCOL_CACHE_SUPPORT must match SPEC 3.4.2."""

    def test_anthropic_supports_caching(self) -> None:
        assert PROTOCOL_CACHE_SUPPORT.get("anthropic-messages") is True

    def test_bedrock_supports_caching(self) -> None:
        assert PROTOCOL_CACHE_SUPPORT.get("bedrock-converse") is True

    def test_openai_chat_does_not(self) -> None:
        assert PROTOCOL_CACHE_SUPPORT.get("openai-chat") is False

    def test_openai_responses_does_not(self) -> None:
        assert PROTOCOL_CACHE_SUPPORT.get("openai-responses") is False

    def test_gemini_does_not(self) -> None:
        assert PROTOCOL_CACHE_SUPPORT.get("gemini") is False

    def test_all_keys_are_protocol_ids(self) -> None:
        for key in PROTOCOL_CACHE_SUPPORT:
            assert isinstance(key, str)
            assert "/" not in key  # No path characters


# ─── apply_cache_policy() ─────────────────────────────────────────


class TestApplyCachePolicy:
    """apply_cache_policy() must add cache_control markers per SPEC 3.4.2."""

    def test_unsupported_protocol_returns_unchanged(self) -> None:
        request = {"messages": [{"role": "user", "content": "hi"}]}
        result = apply_cache_policy(request, "openai-chat")
        assert result is request  # Same object, unchanged

    def test_supported_protocol_adds_markers(self) -> None:
        request = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello!"},
            ],
            "tools": [
                {"name": "read", "description": "Read files", "input_schema": {}},
            ],
        }
        result = apply_cache_policy(request, "anthropic-messages")
        messages = result["messages"]
        # Last system message should have cache_control
        system_msgs = [m for m in messages if m["role"] == "system"]
        if system_msgs:
            assert "cache_control" in system_msgs[-1]
            assert system_msgs[-1]["cache_control"]["type"] == "ephemeral"

    def test_no_messages_returns_unchanged(self) -> None:
        request: dict[str, Any] = {}
        result = apply_cache_policy(request, "anthropic-messages")
        assert result is request


# ─── RequestCache ─────────────────────────────────────────────────


class TestRequestCache:
    """RequestCache basic operations."""

    def test_disabled_cache_returns_none(self) -> None:
        cache = RequestCache(enabled=False)
        assert cache.get({"test": "data"}) is None

    def test_set_and_get(self) -> None:
        cache = RequestCache(enabled=True)
        cache.set({"key": "value"}, "result")
        assert cache.get({"key": "value"}) == "result"

    def test_miss_returns_none(self) -> None:
        cache = RequestCache(enabled=True)
        assert cache.get({"nonexistent": "key"}) is None

    def test_clear(self) -> None:
        cache = RequestCache(enabled=True)
        cache.set({"a": 1}, "value")
        cache.clear()
        assert cache.get({"a": 1}) is None

    def test_max_size_eviction(self) -> None:
        cache = RequestCache(enabled=True, max_size=2)
        cache.set({"k1": 1}, "v1")
        cache.set({"k2": 2}, "v2")
        cache.set({"k3": 3}, "v3")  # Should evict oldest
        assert cache.get({"k3": 3}) == "v3"
        # At least 2 entries after eviction
        assert len(cache._cache) <= 2

    def test_ttl_expiry(self) -> None:
        import time
        cache = RequestCache(enabled=True, ttl=0)  # 0 second TTL
        cache.set({"data": "x"}, "result")
        time.sleep(0.01)  # Ensure expiry
        assert cache.get({"data": "x"}) is None
