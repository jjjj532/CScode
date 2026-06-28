from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ToolResult:
    success: bool
    data: str
    error: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    requires_permission: bool = True
    permission_default: str = "allow"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
    }

    @abstractmethod
    async def execute(self, args: dict[str, Any]) -> ToolResult: ...

    def to_llm_format(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._context_support: dict[str, bool | None] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            logger.warning("ToolRegistry.register: duplicate tool=%s", tool.name)
            msg = f"Tool '{tool.name}' is already registered"
            raise ValueError(msg)
        self._tools[tool.name] = tool
        logger.debug("ToolRegistry.register: tool=%s registered, total=%d", tool.name, len(self._tools))

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def to_llm_tools(self) -> list[dict[str, Any]]:
        return [tool.to_llm_format() for tool in self._tools.values()]

    async def execute_tool_call(self, tool_call: dict[str, Any], context: dict[str, Any] | None = None) -> ToolResult:
        fn_info = tool_call.get("function", {})
        name = fn_info.get("name", "")
        raw_args = fn_info.get("arguments", "{}")
        if isinstance(raw_args, str):
            import json
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError as e:
                logger.error("execute_tool_call: json parse error tool=%s error=%s", name, e)
                return ToolResult(
                    success=False,
                    data="",
                    error=f"Failed to parse arguments for tool '{name}': {e}",
                )
        else:
            args = raw_args

        tool = self.get(name)
        if tool is None:
            logger.error("execute_tool_call: unknown tool=%s", name)
            return ToolResult(
                success=False,
                data="",
                error=f"Unknown tool: {name}",
            )
        if name not in self._context_support:
            try:
                sig = inspect.signature(tool.execute)
                self._context_support[name] = "context" in sig.parameters
            except ValueError:
                self._context_support[name] = False
        logger.debug("execute_tool_call: name=%s has_context=%s", name, self._context_support.get(name))
        if self._context_support[name]:
            result = await tool.execute(args, context=context)  # type: ignore[call-arg]
        else:
            result = await tool.execute(args)
        logger.debug("execute_tool_call: done name=%s success=%s", name, result.success)
        return result
