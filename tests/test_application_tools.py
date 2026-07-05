"""Tests for P2-11: Application Tools — tools that bypass permission prompts.

Tests cover:
1. Default application tools include read, grep, glob, ls
2. is_application_tool returns True for registered tools
3. is_application_tool returns False for unknown tools
4. register_application_tool adds a new tool
5. get_application_tools returns all registered tool names
6. API endpoint GET /api/tools/application returns the list
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx._transports.asgi import ASGITransport


# ═══════════════════════════════════════════════════════════════════
# App fixture for API tests
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def app() -> FastAPI:
    from fastapi import APIRouter

    from cscode.core.application_tools import get_application_tools

    _app = FastAPI()
    router = APIRouter()

    @router.get("/api/tools/application")
    async def list_application_tools():
        return {"tools": get_application_tools()}

    _app.include_router(router)
    return _app


# ═══════════════════════════════════════════════════════════════════
# Tests: is_application_tool
# ═══════════════════════════════════════════════════════════════════


class TestIsApplicationTool:
    def test_read_is_application_tool(self) -> None:
        from cscode.core.application_tools import is_application_tool

        assert is_application_tool("read")

    def test_grep_is_application_tool(self) -> None:
        from cscode.core.application_tools import is_application_tool

        assert is_application_tool("grep")

    def test_glob_is_application_tool(self) -> None:
        from cscode.core.application_tools import is_application_tool

        assert is_application_tool("glob")

    def test_ls_is_application_tool(self) -> None:
        from cscode.core.application_tools import is_application_tool

        assert is_application_tool("ls")

    def test_write_is_not_application_tool(self) -> None:
        from cscode.core.application_tools import is_application_tool

        assert not is_application_tool("write")

    def test_bash_is_not_application_tool(self) -> None:
        from cscode.core.application_tools import is_application_tool

        assert not is_application_tool("bash")

    def test_random_tool_is_not_application_tool(self) -> None:
        from cscode.core.application_tools import is_application_tool

        assert not is_application_tool("nonexistent_tool")


# ═══════════════════════════════════════════════════════════════════
# Tests: register_application_tool
# ═══════════════════════════════════════════════════════════════════


class TestRegisterApplicationTool:
    def test_register_new_tool(self) -> None:
        from cscode.core.application_tools import (
            _APPLICATION_TOOLS,
            is_application_tool,
            register_application_tool,
        )

        # Save state, add, verify, restore
        saved = set(_APPLICATION_TOOLS)
        try:
            _APPLICATION_TOOLS.clear()
            _APPLICATION_TOOLS.update(saved)

            register_application_tool("my_custom_tool")
            assert is_application_tool("my_custom_tool")
        finally:
            _APPLICATION_TOOLS.clear()
            _APPLICATION_TOOLS.update(saved)

    def test_register_duplicate(self) -> None:
        from cscode.core.application_tools import is_application_tool, register_application_tool

        assert is_application_tool("read")
        register_application_tool("read")  # Should not raise
        assert is_application_tool("read")


# ═══════════════════════════════════════════════════════════════════
# Tests: get_application_tools
# ═══════════════════════════════════════════════════════════════════


class TestGetApplicationTools:
    def test_returns_list(self) -> None:
        from cscode.core.application_tools import get_application_tools

        tools = get_application_tools()
        assert isinstance(tools, list)

    def test_contains_core_tools(self) -> None:
        from cscode.core.application_tools import get_application_tools

        tools = set(get_application_tools())
        assert "read" in tools
        assert "grep" in tools
        assert "glob" in tools
        assert "ls" in tools

    def test_excludes_mutation_tools(self) -> None:
        from cscode.core.application_tools import get_application_tools

        tools = set(get_application_tools())
        assert "write" not in tools
        assert "bash" not in tools
        assert "edit" not in tools


# ═══════════════════════════════════════════════════════════════════
# Tests: API endpoint
# ═══════════════════════════════════════════════════════════════════


class TestApplicationToolsAPI:
    async def test_get_application_tools(self, app: FastAPI) -> None:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/tools/application")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert isinstance(data["tools"], list)
        assert "read" in data["tools"]
