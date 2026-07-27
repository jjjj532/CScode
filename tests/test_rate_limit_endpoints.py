"""Endpoint tests for rate limiting middleware."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from cscode.server.rate_limiter import RateLimiter


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_"))
    return temp_dir / "test_cscode.db"


@pytest.fixture
def db_env() -> Generator[None, None, None]:
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        yield
    finally:
        if db_path.exists():
            db_path.unlink()


class TestRateLimitMiddleware:
    """Rate limiting middleware on /api/chat and /api/chat/stream."""

    def test_non_chat_endpoint_not_affected(self, db_env: None) -> None:
        """Non-chat endpoints pass through unaffected."""
        from cscode.server import app as app_module

        original = app_module.rate_limiter
        app_module.rate_limiter = RateLimiter(max_requests=1, window_seconds=60)
        try:
            from cscode.server.app import app

            with TestClient(app) as client:
                for _ in range(10):
                    resp = client.get("/api/config")
                    assert resp.status_code == 200
        finally:
            app_module.rate_limiter = original

    def test_chat_blocked_after_limit(self, db_env: None) -> None:
        """More than max requests to /api/chat return 429."""
        from cscode.server import app as app_module

        original = app_module.rate_limiter
        app_module.rate_limiter = RateLimiter(max_requests=2, window_seconds=60)
        try:
            from cscode.server.app import app

            with TestClient(app) as client:
                for _ in range(2):
                    resp = client.post("/api/chat", json={"message": "hi"})
                    assert resp.status_code != 429
                resp = client.post("/api/chat", json={"message": "hi"})
                assert resp.status_code == 429
                data = resp.json()
                assert "detail" in data
        finally:
            app_module.rate_limiter = original

    def test_chat_stream_also_rate_limited(self, db_env: None) -> None:
        """Same limit applies to /api/chat/stream."""
        from cscode.server import app as app_module

        original = app_module.rate_limiter
        app_module.rate_limiter = RateLimiter(max_requests=1, window_seconds=60)
        try:
            from cscode.server.app import app

            with TestClient(app) as client:
                resp = client.post("/api/chat/stream", json={"message": "hi"})
                assert resp.status_code != 429

                resp = client.post("/api/chat/stream", json={"message": "hi"})
                assert resp.status_code == 429
        finally:
            app_module.rate_limiter = original

    def test_rate_limit_429_has_correct_body(self, db_env: None) -> None:
        """429 response has expected JSON body."""
        from cscode.server import app as app_module

        original = app_module.rate_limiter
        app_module.rate_limiter = RateLimiter(max_requests=0, window_seconds=60)
        try:
            from cscode.server.app import app

            with TestClient(app) as client:
                resp = client.post("/api/chat", json={"message": "hi"})
                assert resp.status_code == 429
                assert resp.json() == {
                    "detail": "Too many requests. Try again later."
                }
        finally:
            app_module.rate_limiter = original
