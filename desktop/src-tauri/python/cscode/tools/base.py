from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    success: bool
    data: str
    error: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class BaseTool(ABC):
    name: str = ""
    description: str = ""
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

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            msg = f"Tool '{tool.name}' is already registered"
            raise ValueError(msg)
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def to_llm_tools(self) -> list[dict[str, Any]]:
        return [tool.to_llm_format() for tool in self._tools.values()]

    async def execute_tool_call(self, tool_call: dict[str, Any]) -> ToolResult:
        fn_info = tool_call.get("function", {})
        name = fn_info.get("name", "")
        raw_args = fn_info.get("arguments", "{}")
        if isinstance(raw_args, str):
            import json

            args = json.loads(raw_args)
        else:
            args = raw_args

        tool = self.get(name)
        if tool is None:
            return ToolResult(
                success=False,
                data="",
                error=f"Unknown tool: {name}",
            )
        return await tool.execute(args)
