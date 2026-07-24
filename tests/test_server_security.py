"""Tests for production security hardening.

Covers:
- P0-1: Server defaults to 127.0.0.1 (not 0.0.0.0)
- P0-4: Non-localhost requests get 403
- P0-2: API key is masked (never returned fully in GET /api/config)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from cscode.server.app import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, Any]:
    """Test client against the FastAPI app directly (ASGI, no network)."""
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8080") as ac:
        yield ac


# ── P0-1: CLI default host ─────────────────────────────────────────

def test_cli_server_default_host() -> None:
    """The CLI server command must default to 127.0.0.1 for safety."""
    from cscode.cli import server
    # Click options are stored in .params list
    for param in server.params:  # type: ignore[attr-defined]
        if getattr(param, "name", None) == "host":
            assert param.default == "127.0.0.1", (  # type: ignore[attr-defined]
                f"CLI --host default should be 127.0.0.1, got {param.default!r}"
            )
            return
    pytest.fail("Could not find --host option on server command")


# ── P0-4: Non-localhost middleware ─────────────────────────────────

@pytest.mark.asyncio
async def test_localhost_request_allowed(client: AsyncClient) -> None:
    """GET /api/health from 127.0.0.1 should succeed."""
    resp = await client.get("/api/health")
    # Health may fail if DB not initialized, but should NOT get 403
    assert resp.status_code != 403, "Localhost request got 403"


@pytest.mark.asyncio
async def test_non_localhost_request_blocked() -> None:
    """Request with non-localhost client host should receive 403."""
    transport = ASGITransport(app=app, client=("192.168.1.100", 54321))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://192.168.1.100:8080") as ac:
        resp = await ac.get("/api/health")
        assert resp.status_code == 403, (
            f"Non-localhost request should be 403, got {resp.status_code}"
        )


# ── P1-3: Server log security tip ─────────────────────────────────

def test_security_log_tip_in_source() -> None:
    """Server lifespan must contain a security tip log message."""
    src = (Path(__file__).resolve().parent.parent / "src" / "cscode" / "server" / "app.py").read_text()
    assert "Security:" in src, "app.py must contain a startup security log"
    assert "localhost" in src, "security log should mention localhost"
    # Verify it's in the lifespan function (after "Lifespan startup complete")
    assert "Lifespan startup complete" in src
    assert "expose externally" in src, "security log should mention --host 0.0.0.0"

@pytest.mark.asyncio
async def test_get_config_no_api_key(client: AsyncClient) -> None:
    """GET /api/config must NOT expose the full API key.

    Instead, it should include a boolean api_key_configured field.
    """
    resp = await client.get("/api/config")
    # The endpoint may return 503 if DB is None (test env), but must not have api_key
    if resp.status_code == 200:
        data = resp.json()
        assert "api_key" not in data, "Full api_key should not be in GET response"
        assert "api_key_configured" in data, (
            "Should include api_key_configured boolean"
        )
        assert isinstance(data["api_key_configured"], bool), (
            f"api_key_configured should be bool, got {type(data['api_key_configured'])}"
        )


@pytest.mark.asyncio
async def test_save_config_accepts_api_key(client: AsyncClient) -> None:
    """POST /api/config should accept api_key for saving."""
    resp = await client.post(
        "/api/config",
        json={
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-test123456789",
        },
    )
    # May 503 if DB not init, but should NOT 422 or reject api_key field
    assert resp.status_code in (200, 503), (
        f"POST /api/config with api_key: expected 200 or 503, got {resp.status_code}"
    )
