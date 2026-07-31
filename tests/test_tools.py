from __future__ import annotations

from dataclasses import dataclass

import pytest

from cscode.tools.base import BaseTool, ToolRegistry, ToolResult


class TestToolResult:
    def test_success_result(self):
        r = ToolResult(success=True, data="hello")
        assert r.success is True
        assert r.data == "hello"
        assert r.error is None

    def test_error_result(self):
        r = ToolResult(success=False, data="", error="Something went wrong")
        assert r.success is False
        assert r.error == "Something went wrong"


class TestBaseTool:
    def test_tool_is_abstract(self):
        with pytest.raises(TypeError):
            BaseTool()  # type: ignore

    def test_concrete_tool(self):
        class EchoTool(BaseTool):
            name = "echo"
            description = "Echo back the input"

            async def execute(self, args: dict) -> ToolResult:
                return ToolResult(success=True, data=args.get("text", ""))

        tool = EchoTool()
        assert tool.name == "echo"
        assert tool.description == "Echo back the input"

    def test_to_llm_format(self):
        class AddTool(BaseTool):
            name = "add"
            description = "Add two numbers"
            parameters: dict = {
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["a", "b"],
            }

            async def execute(self, args: dict) -> ToolResult:
                return ToolResult(
                    success=True,
                    data=str(args.get("a", 0) + args.get("b", 0)),
                )

        tool = AddTool()
        fmt = tool.to_llm_format()
        assert fmt["type"] == "function"
        assert fmt["function"]["name"] == "add"
        assert "a" in fmt["function"]["parameters"]["properties"]


class TestToolRegistry:
    def test_register_and_get(self):
        class TestTool(BaseTool):
            name = "test"
            description = "A test tool"

            async def execute(self, args: dict) -> ToolResult:
                return ToolResult(success=True, data="ok")

        registry = ToolRegistry()
        registry.register(TestTool())
        assert registry.get("test") is not None
        assert registry.get("nonexistent") is None

    def test_list_tools(self):
        class ToolA(BaseTool):
            name = "a"
            description = "Tool A"
            async def execute(self, args: dict) -> ToolResult:
                return ToolResult(success=True, data="a")

        class ToolB(BaseTool):
            name = "b"
            description = "Tool B"
            async def execute(self, args: dict) -> ToolResult:
                return ToolResult(success=True, data="b")

        registry = ToolRegistry()
        registry.register(ToolA())
        registry.register(ToolB())
        names = registry.list_tools()
        assert "a" in names
        assert "b" in names

    def test_to_llm_tools(self):
        class ToolA(BaseTool):
            name = "a"
            description = "Tool A"
            async def execute(self, args: dict) -> ToolResult:
                return ToolResult(success=True, data="a")

        registry = ToolRegistry()
        registry.register(ToolA())
        tools = registry.to_llm_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "a"

    def test_duplicate_name_raises(self):
        class ToolA(BaseTool):
            name = "dup"
            description = "First"
            async def execute(self, args: dict) -> ToolResult:
                return ToolResult(success=True, data="")

        registry = ToolRegistry()
        registry.register(ToolA())

        class ToolB(BaseTool):
            name = "dup"
            description = "Second"
            async def execute(self, args: dict) -> ToolResult:
                return ToolResult(success=True, data="")

        with pytest.raises(ValueError, match="already registered"):
            registry.register(ToolB())


class TestToolsApiEndpoint:
    """Regression (P1-2): GET /api/tools must list the full tool registry.

    Previously /api/tools was an alias for /tools/application which only
    returns safe read-only tools — so execution tools (bash, write, edit)
    never appeared and the LLM never learned they existed.
    """

    def test_tools_endpoint_lists_execution_tools(self):
        import os
        import tempfile
        from pathlib import Path

        from fastapi.testclient import TestClient

        db_path = Path(tempfile.mkdtemp(prefix="cscode_test_tools_")) / "test.db"
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app

            with TestClient(app) as client:
                resp = client.get("/api/tools")
                assert resp.status_code == 200
                data = resp.json()
                assert "tools" in data
                names = set(data["tools"])
                assert "read" in names
                assert "bash" in names, "bash missing from /api/tools"
                assert "write" in names, "write missing from /api/tools"
                assert "edit" in names, "edit missing from /api/tools"
                assert "grep" in names
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_application_tools_endpoint_still_readonly(self):
        """GET /api/tools/application keeps returning only safe tools."""
        from fastapi.testclient import TestClient

        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.get("/api/tools/application")
            assert resp.status_code == 200
            names = set(resp.json()["tools"])
            assert "read" in names
            assert "bash" not in names
