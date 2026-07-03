"""TDD tests for Provider Model Status (P0-8).

RED phase: these tests MUST fail initially.
GREEN phase: implementation makes them pass.
"""

from __future__ import annotations

import pytest

from cscode.providers.status import (
    ProviderStatus,
    ProviderStatusChecker,
    StatusInfo,
)


class TestStatusInfo:
    def test_online_status(self) -> None:
        s = StatusInfo(ProviderStatus.ONLINE, "Available")
        assert s.status is ProviderStatus.ONLINE
        assert s.message == "Available"

    def test_offline_status(self) -> None:
        s = StatusInfo(ProviderStatus.OFFLINE, "No API key configured")
        assert s.status is ProviderStatus.OFFLINE

    def test_error_status(self) -> None:
        s = StatusInfo(ProviderStatus.ERROR, "Connection refused")
        assert s.status is ProviderStatus.ERROR

    def test_default_message(self) -> None:
        s = StatusInfo(ProviderStatus.ONLINE)
        assert s.message == ""


class TestProviderStatusChecker:
    def test_missing_api_key_returns_offline(self) -> None:
        checker = ProviderStatusChecker()
        result = checker.check("openai", api_key="")
        assert result.status is ProviderStatus.OFFLINE
        assert "API key" in result.message

    def test_unknown_provider_returns_error(self) -> None:
        checker = ProviderStatusChecker()
        result = checker.check("nonexistent_provider", api_key="sk-test")
        assert result.status is ProviderStatus.ERROR
        assert "Unknown provider" in result.message


class TestProviderStatusCheckerCache:
    def test_cache_returns_cached_result(self) -> None:
        checker = ProviderStatusChecker(cache_ttl=300)
        # First check returns a result
        result1 = checker.check("openai", api_key="sk-test")
        # Second check with same params should return cached
        result2 = checker.check("openai", api_key="sk-test")
        assert result1.status == result2.status
        assert result1.message == result2.message

    def test_different_providers_not_cached(self) -> None:
        checker = ProviderStatusChecker()
        result_a = checker.check("openai", api_key="sk-a")
        result_b = checker.check("anthropic", api_key="sk-b")
        # Different providers → different cache keys
        assert (result_a.status, result_a.message) != (result_b.status, result_b.message)

    def test_cache_expiry(self) -> None:
        checker = ProviderStatusChecker(cache_ttl=0)  # No cache
        result1 = checker.check("openai", api_key="sk-test")
        result2 = checker.check("openai", api_key="sk-test")
        # Both succeed but are separate checks
        assert result1.status == result2.status


class TestProviderStatusCheckerKnownProviders:
    def test_openai_requires_key(self) -> None:
        checker = ProviderStatusChecker()
        result = checker.check("openai", api_key="")
        assert result.status is ProviderStatus.OFFLINE

    def test_anthropic_requires_key(self) -> None:
        checker = ProviderStatusChecker()
        result = checker.check("anthropic", api_key="")
        assert result.status is ProviderStatus.OFFLINE

    def test_ollama_no_key_needed(self) -> None:
        checker = ProviderStatusChecker()
        result = checker.check("ollama")
        # Ollama doesn't need an API key - may or may not be online
        # but should not return OFFLINE for missing key
        assert result.status is not ProviderStatus.OFFLINE

    def test_gemini_requires_key(self) -> None:
        checker = ProviderStatusChecker()
        result = checker.check("gemini", api_key="")
        assert result.status is ProviderStatus.OFFLINE


class TestProviderStatusCheckerEndpoint:
    def test_custom_base_url(self) -> None:
        checker = ProviderStatusChecker()
        result = checker.check("openai", api_key="sk-test", base_url="http://localhost:8080/v1")
        # Should try to connect to custom base URL
        # Without a running server, should return ERROR (not OFFLINE)
        assert result.status is ProviderStatus.ERROR

    def test_invalid_key(self) -> None:
        checker = ProviderStatusChecker()
        # Without mocking, we can only test that the check doesn't crash
        result = checker.check("openai", api_key="sk-invalid-test-key")
        assert result.status in (ProviderStatus.ERROR, ProviderStatus.OFFLINE)
