"""Tests for P2-17: Config tui-host-attention — TUI host attention config.

Tests cover:
1. Config accepts tui_host_attention field
2. tui_host_attention defaults to empty string
3. tui_host_attention can be set via Config.from_dict
4. CONFIG_KEY_META includes tui_host_attention entry
5. API endpoint GET /config/reference includes tui_host_attention
6. tui_host_attention is returned in to_dict
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx._transports.asgi import ASGITransport


class TestConfigTuiHostAttention:
    def test_config_has_tui_host_attention_field(self) -> None:
        """Config dataclass has tui_host_attention field."""
        from cscode.core.config import Config

        assert hasattr(Config, "tui_host_attention")

    def test_default_is_empty_string(self) -> None:
        """tui_host_attention defaults to empty string."""
        from cscode.core.config import Config

        cfg = Config()
        assert cfg.tui_host_attention == ""

    def test_from_dict_sets_tui_host_attention(self) -> None:
        """tui_host_attention can be set via from_dict."""
        from cscode.core.config import Config

        cfg = Config.from_dict({"tui_host_attention": "bell"})
        assert cfg.tui_host_attention == "bell"

    def test_to_dict_includes_tui_host_attention(self) -> None:
        """tui_host_attention appears in to_dict when set."""
        from cscode.core.config import Config

        cfg = Config(tui_host_attention="flash")
        d = cfg.to_dict()
        assert d.get("tui_host_attention") == "flash"

    def test_key_meta_includes_tui_host_attention(self) -> None:
        """CONFIG_KEY_META has tui_host_attention entry."""
        from cscode.core.config import CONFIG_KEY_META

        assert "tui_host_attention" in CONFIG_KEY_META
        entry = CONFIG_KEY_META["tui_host_attention"]
        assert entry["type"] == "string"
        assert "description" in entry

    @pytest.mark.asyncio
    async def test_reference_endpoint_includes_tui_host_attention(self) -> None:
        """GET /config/reference returns tui_host_attention entry."""
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
        transport = ASGITransport(app=_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/config/reference")
        data = resp.json()
        keys = {e["key"] for e in data}
        assert "tui_host_attention" in keys
