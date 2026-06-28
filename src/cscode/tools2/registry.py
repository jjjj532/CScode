"""ToolRegistry v2 — 类型安全的工具注册和调度。

对比旧 ToolRegistry:
  - 旧: register(tool) + execute_tool_call(dict) → ToolResult（JSON 手动解析）
  - 新: register(tool) + settle(name, args_dict) → ToolResult（Pydantic 校验）

支持 OpenCode 的 materialize 模式:
  - materialize(permissions?) → definitions + settle
  - settle 负责 decode → execute → encode 全流程
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from cscode.schema.tool import ToolDefinition
from cscode.tools2.base import Tool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class ToolRegistry:
    """Typed tool registry with materialization support.

    Usage:
        registry = ToolRegistry()
        registry.register(ReadTool())
        registry.register(BashTool())

        # Materialize for a specific context (e.g. with permissions)
        definitions, settle = registry.materialize()
        result = await settle("read", {"path": "/tmp/x"})
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool[Any, Any]] = {}

    def register(self, tool: Tool[Any, Any]) -> None:
        """Register a tool. Raises ValueError on name collision."""
        if tool.name in self._tools:
            logger.warning("ToolRegistry.register: duplicate tool=%s", tool.name)
            msg = f"Tool '{tool.name}' is already registered"
            raise ValueError(msg)
        self._tools[tool.name] = tool
        logger.debug("ToolRegistry.register: tool=%s registered, total=%d", tool.name, len(self._tools))

    def get(self, name: str) -> Tool[Any, Any] | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def to_definitions(self) -> list[ToolDefinition]:
        """All registered tools as ToolDefinition list (for LLM consumption)."""
        return [tool.to_definition() for tool in self._tools.values()]

    def materialize(
        self,
        tool_names: list[str] | None = None,
    ) -> tuple[list[ToolDefinition], Any]:
        """Materialize tools for execution.

        Args:
            tool_names: Optional subset of tool names to include.
                        None means all registered tools.

        Returns:
            (definitions, settle)
            - definitions: list of ToolDefinition for LLM
            - settle: async function(name, args_dict) → ToolResult
        """
        if tool_names is not None:
            tools = {name: self._tools[name] for name in tool_names if name in self._tools}
        else:
            tools = dict(self._tools)

        definitions = [tool.to_definition() for tool in tools.values()]
        logger.debug("ToolRegistry.materialize: tools=%d definitions=%d", len(tools), len(definitions))

        async def settle(name: str, raw_args: dict[str, object]) -> ToolResult[Any]:
            """Decode → execute → encode for a single tool call."""
            tool = tools.get(name)
            if tool is None:
                logger.error("settle: unknown tool=%s", name)
                return ToolResult(
                    success=False,
                    error=f"Unknown tool: {name}",
                )

            logger.debug("settle: tool=%s args_keys=%s", name, list(raw_args.keys()))

            # Decode: validate input via Pydantic
            try:
                validated = tool.input_schema.model_validate(raw_args)
            except ValidationError as e:
                logger.warning("settle: validation error tool=%s error=%s", name, e)
                return ToolResult(
                    success=False,
                    error=f"Invalid arguments for {name}: {e}",
                )

            # Execute
            try:
                result = await tool.execute(validated)
                logger.debug("settle: done tool=%s success=%s", name, result.success)
                return result
            except Exception as e:
                logger.exception("settle: execution error tool=%s", name)
                return ToolResult(
                    success=False,
                    error=tool.format_error(e),
                )

        return definitions, settle

    @staticmethod
    def parse_tool_call(
        raw: str | dict[str, object],
    ) -> tuple[str, dict[str, object] | None, str | None]:
        """Parse an LLM tool call into (name, args, error).

        Accepts:
          - dict with function.name + function.arguments
          - JSON string of the above
          - Old format: dict with name + arguments

        Static method so it can be used without a registry instance.
        Replaces old execute_tool_call's inline parsing.
        """
        parsed: dict[str, object] | None = None

        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                return "", None, f"Failed to parse tool call JSON: {e}"
        elif isinstance(raw, dict):
            parsed = raw

        if not isinstance(parsed, dict):
            return "", None, "Tool call must be a dict or JSON string"

        # Try modern format: {function: {name, arguments}}
        fn_info = parsed.get("function")
        if isinstance(fn_info, dict):
            name_obj = fn_info.get("name", "")
            args_raw = fn_info.get("arguments", "{}")
        else:
            # Fallback: flat {name, arguments}
            name_obj = parsed.get("name", "")
            args_raw = parsed.get("arguments", "{}")

        name = str(name_obj) if name_obj else ""
        if not name:
            return "", None, "Tool call missing 'name'"

        # Parse arguments
        if isinstance(args_raw, str):
            if not args_raw.strip():
                return name, {}, None
            try:
                args_data = json.loads(args_raw)
            except json.JSONDecodeError as e:
                return name, None, f"Failed to parse arguments for '{name}': {e}"
        elif isinstance(args_raw, dict):
            args_data = args_raw
        else:
            return name, None, f"Arguments for '{name}' must be a dict or JSON string"

        if not isinstance(args_data, dict):
            return name, None, f"Parsed arguments for '{name}' must be a dict"

        return name, args_data, None
