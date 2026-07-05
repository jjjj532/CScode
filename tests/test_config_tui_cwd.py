"""Tests for P2-15: Config tui-cwd — TUI working directory config.

Tests cover:
1. Config accepts tui_cwd field
2. tui_cwd defaults to empty string
3. tui_cwd can be set via Config.from_dict
4. CONFIG_KEY_META includes tui_cwd entry
5. API endpoint GET /config/reference includes tui_cwd
6. tui_cwd is returned in to_dict
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI


class TestConfigTuiCwd:
    def test_config_has_tui_cwd_field(self) -> None:
        """Config dataclass has tui_cwd field."""
        from cscode.core.config import Config

        assert hasattr(Config, "tui_cwd")

    def test_default_is_empty_string(self) -> None:
        """tui_cwd defaults to empty string."""
        from cscode.core.config import Config

        cfg = Config()
        assert cfg.tui_cwd == ""

    def test_from_dict_sets_tui_cwd(self) -> None:
        """tui_cwd can be set via from_dict."""
        from cscode.core.config import Config

        cfg = Config.from_dict({"tui_cwd": "/workspace/project"})
        assert cfg.tui_cwd == "/workspace/project"

    def test_to_dict_includes_tui_cwd(self) -> None:
        """tui_cwd appears in to_dict when set."""
        from cscode.core.config import Config

        cfg = Config(tui_cwd="/app")
        d = cfg.to_dict()
        assert d.get("tui_cwd") == "/app"

    def test_key_meta_includes_tui_cwd(self) -> None:
        """CONFIG_KEY_META has tui_cwd entry."""
        from cscode.core.config import CONFIG_KEY_META

        assert "tui_cwd" in CONFIG_KEY_META
        entry = CONFIG_KEY_META["tui_cwd"]
        assert entry["type"] == "string"
        assert "description" in entry

    @pytest.mark.asyncio
    async def test_reference_endpoint_includes_tui_cwd(self) -> None:
        """GET /config/reference returns tui_cwd entry."""
        from fastapi import APIRouter

        from cscode.core.config import CONFIG_KEY_META

        _app = FastAPI()
        router = APIRouter()

        @router.get("/api/config/reference")
        async def config_ref() -> list[dict[str, str]]:
            return [
                {"key": k, "type": v.get("type", ""), "default": v.get("default", ""), "description": v.get("description", "")}
                for k, v in sorted(CONFIG_KEY_META.items())
            ]

        _app.include_router(router)
        transport = httpx._transports.asgi.ASGITransport(app=_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/config/reference")
        data = resp.json()
        keys = {e["key"] for e in data}
        assert "tui_cwd" in keys
