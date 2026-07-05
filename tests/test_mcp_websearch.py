"""Tests for P2-18: Tool mcp-websearch — web search via MCP tool integration.

Tests cover:
1. websearch is recognized as an application tool
2. WebSearchTool is properly configured for MCP
3. Name consistency between tool definition and application tools
"""

from __future__ import annotations

from cscode.core.application_tools import APPLICATION_TOOLS, is_application_tool
from cscode.tools.websearch import WebSearchTool as WebSearchToolV1
from cscode.tools2.websearch import WebSearchTool as WebSearchToolV2


class TestMCPWebSearchApplicationTools:
    def test_websearch_in_application_tools(self) -> None:
        """websearch is listed as an application tool."""
        assert "websearch" in APPLICATION_TOOLS

    def test_is_application_tool_websearch(self) -> None:
        """is_application_tool returns True for websearch."""
        assert is_application_tool("websearch") is True

    def test_v1_tool_name_matches(self) -> None:
        """WebSearchTool v1 name matches the application_tools entry."""
        assert WebSearchToolV1.name == "websearch"

    def test_v2_tool_name_matches(self) -> None:
        """WebSearchTool v2 name matches the application_tools entry."""
        assert WebSearchToolV2.name == "websearch"

    def test_v1_tool_has_query_param(self) -> None:
        """WebSearchTool v1 has query as required parameter."""
        tool = WebSearchToolV1()
        props = tool.parameters.get("properties", {})
        assert "query" in props
        assert "query" in tool.parameters.get("required", [])

    def test_v2_tool_has_query_input(self) -> None:
        """WebSearchTool v2 has query in input schema."""
        assert "query" in WebSearchToolV2.input_schema.model_fields

    def test_v1_to_llm_format(self) -> None:
        """WebSearchTool v1 produces valid LLM tool format."""
        tool = WebSearchToolV1()
        fmt = tool.to_llm_format()
        assert fmt["type"] == "function"
        assert fmt["function"]["name"] == "websearch"
        assert "parameters" in fmt["function"]

    def test_v2_to_definition(self) -> None:
        """WebSearchTool v2 produces valid ToolDefinition."""
        definition = WebSearchToolV2().to_definition()
        assert definition.name == "websearch"
        assert definition.description
        assert definition.input_schema


class TestMCPWebSearchExecution:
    def test_v1_execute_returns_result(self) -> None:
        """WebSearchTool v1 executes and returns a ToolResult."""
        import anyio

        tool = WebSearchToolV1()
        result = anyio.run(tool.execute, {"query": "test query"})
        assert result.success is True
        assert result.data

    def test_v2_execute_returns_result(self) -> None:
        """WebSearchTool v2 executes and returns a typed ToolResult."""
        import anyio

        tool = WebSearchToolV2()
        result = anyio.run(tool.execute, WebSearchToolV2.input_schema(query="test"))
        assert result.success is True
        assert result.data is not None
        assert result.data.results
