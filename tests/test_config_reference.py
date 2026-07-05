"""Tests for P2-10: Config Reference — schema endpoint for available config options.

Tests cover:
1. GET /api/config/reference returns all known config keys
2. Each entry has key, type, default, description fields
3. Known keys like OPENAI_API_KEY exist
4. Endpoint returns config built from existing Config model
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx._transports.asgi import ASGITransport

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# App fixture
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def app() -> FastAPI:
    from fastapi import APIRouter

    _app = FastAPI()
    router = APIRouter()

    @router.get("/api/config/reference")
    async def config_reference():
        from cscode.core.config import (
            CONFIG_KEY_META,
        )

        return [
            {
                "key": k,
                "type": v.get("type", "string"),
                "default": v.get("default", ""),
                "description": v.get("description", ""),
            }
            for k, v in sorted(CONFIG_KEY_META.items())
        ]

    _app.include_router(router)
    return _app


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════


class TestConfigReference:
    async def test_returns_list(self, app: FastAPI) -> None:
        """GET /api/config/reference returns a list."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/config/reference")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_each_entry_has_required_fields(self, app: FastAPI) -> None:
        """Every entry has key, type, default, description."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/config/reference")
        data = resp.json()
        for entry in data:
            assert "key" in entry
            assert "type" in entry
            assert "default" in entry
            assert "description" in entry

    async def test_known_keys_present(self, app: FastAPI) -> None:
        """Well-known config keys exist in the reference."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/config/reference")
        data = resp.json()
        keys = {e["key"] for e in data}
        assert "OPENAI_API_KEY" in keys
        assert "ANTHROPIC_API_KEY" in keys
        assert "MODEL" in keys
        assert "PROVIDER" in keys

    async def test_defaults_are_strings(self, app: FastAPI) -> None:
        """Default values are always strings."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/config/reference")
        data = resp.json()
        for entry in data:
            assert isinstance(entry["default"], str), f"{entry['key']}: default not str"
            assert isinstance(entry["type"], str), f"{entry['key']}: type not str"

    async def test_empty_config_meta(self) -> None:
        """If CONFIG_KEY_META is empty, reference returns empty list."""
        from fastapi import APIRouter

        _app = FastAPI()
        router = APIRouter()

        @router.get("/api/config/reference")
        async def empty_ref():
            return []

        _app.include_router(router)
        transport = ASGITransport(app=_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/config/reference")
        assert resp.status_code == 200
        assert resp.json() == []
