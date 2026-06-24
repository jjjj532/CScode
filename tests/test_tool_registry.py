from __future__ import annotations

from typing import Any

import pytest
from cscode.tools.base import BaseTool, ToolRegistry, ToolResult


class ContextAwareTool(BaseTool):
    name = "context_aware"
    description = "Tool that accepts context"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, args: dict[str, Any], context: dict | None = None) -> ToolResult:
        session_id = context.get("session_id", "") if context else ""
        return ToolResult(success=True, data=f"session:{session_id}")


class SimpleTool(BaseTool):
    name = "simple"
    description = "Tool without context"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data="simple_tool")


@pytest.mark.asyncio
async def test_context_aware_tool_receives_context():
    registry = ToolRegistry()
    registry.register(ContextAwareTool())

    result = await registry.execute_tool_call(
        {"function": {"name": "context_aware", "arguments": "{}"}},
        context={"session_id": "test-session"},
    )
    assert result.success
    assert "session:test-session" in result.data


@pytest.mark.asyncio
async def test_simple_tool_ignores_context():
    registry = ToolRegistry()
    registry.register(SimpleTool())

    result = await registry.execute_tool_call(
        {"function": {"name": "simple", "arguments": "{}"}},
        context={"session_id": "test-session"},
    )
    assert result.success
    assert result.data == "simple_tool"


@pytest.mark.asyncio
async def test_context_none_fallback():
    registry = ToolRegistry()
    registry.register(ContextAwareTool())

    result = await registry.execute_tool_call(
        {"function": {"name": "context_aware", "arguments": "{}"}},
        context=None,
    )
    assert result.success
    assert "session:" in result.data


@pytest.mark.asyncio
async def test_no_context_param_still_works():
    registry = ToolRegistry()
    registry.register(SimpleTool())

    result = await registry.execute_tool_call(
        {"function": {"name": "simple", "arguments": "{}"}},
    )
    assert result.success
    assert result.data == "simple_tool"
