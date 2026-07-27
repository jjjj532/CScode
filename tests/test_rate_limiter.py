"""Tests for RateLimiter — sliding-window in-memory rate limiting."""

from __future__ import annotations

import pytest

from cscode.server.rate_limiter import RateLimiter


class TestRateLimiter:
    """Unit tests for RateLimiter with controllable time."""

    @pytest.fixture
    def fake_time(self) -> dict[str, float]:
        return {"now": 1000.0}

    @pytest.fixture
    def limiter(self, fake_time: dict[str, float]) -> RateLimiter:
        def _time() -> float:
            return fake_time["now"]

        return RateLimiter(max_requests=5, window_seconds=60, time_func=_time)

    def test_initial_request_allowed(self, limiter: RateLimiter) -> None:
        assert limiter.check("10.0.0.1") is True

    def test_under_limit_allowed(self, limiter: RateLimiter) -> None:
        for _ in range(4):
            limiter.check("10.0.0.1")
        assert limiter.check("10.0.0.1") is True

    def test_exact_limit_allowed(self, limiter: RateLimiter) -> None:
        for _ in range(5):
            limiter.check("10.0.0.1")
        # 5 requests within window — at max_requests=5, the next is blocked
        pass  # verified by test_blocked_at_limit

    def test_blocked_at_limit(self, limiter: RateLimiter, fake_time: dict[str, float]) -> None:
        for _ in range(5):
            assert limiter.check("10.0.0.1") is True
        # 6th request within window — blocked
        assert limiter.check("10.0.0.1") is False

    def test_different_ips_independent(self, limiter: RateLimiter) -> None:
        for _ in range(5):
            limiter.check("10.0.0.1")
        limiter.check("10.0.0.2")  # blocked for .1
        assert limiter.check("10.0.0.2") is True  # .2 should be allowed

    def test_window_expiry_allows_requests(self, limiter: RateLimiter, fake_time: dict[str, float]) -> None:
        for _ in range(5):
            assert limiter.check("10.0.0.1") is True
        # 6th blocked
        assert limiter.check("10.0.0.1") is False
        # Advance past window
        fake_time["now"] += 61.0
        # Should be allowed again
        assert limiter.check("10.0.0.1") is True

    def test_partial_window_slide(self, limiter: RateLimiter, fake_time: dict[str, float]) -> None:
        """Old requests outside window are evicted, allowing new ones."""
        for _ in range(5):
            limiter.check("10.0.0.1")
        # Advance 30s — only 2 requests are now outside window
        fake_time["now"] += 30.0
        # Still blocked: 3 remaining in window
        assert limiter.check("10.0.0.1") is False
        # Advance another 31s — now all 5 are outside window
        fake_time["now"] += 31.0
        assert limiter.check("10.0.0.1") is True

    def test_cleanup_removes_stale_entries(self, limiter: RateLimiter, fake_time: dict[str, float]) -> None:
        limiter.check("10.0.0.1")
        limiter.check("10.0.0.2")
        fake_time["now"] += 120.0
        limiter.cleanup()
        # After cleanup, internal dict should be empty
        assert limiter._windows == {}

    def test_no_cross_ip_interference(self, limiter: RateLimiter) -> None:
        for i in range(10):
            limiter.check(f"10.0.0.{i % 3}")
        # Each IP had 3 or 4 requests — under 5
        assert limiter.check("10.0.0.0") is True

    def test_zero_max_requests_blocks_everything(self) -> None:
        limiter = RateLimiter(max_requests=0, window_seconds=60)
        assert limiter.check("10.0.0.1") is False

    def test_default_limiter_60_per_minute(self) -> None:
        limiter = RateLimiter()
        for _ in range(60):
            assert limiter.check("10.0.0.1") is True
        assert limiter.check("10.0.0.1") is False
