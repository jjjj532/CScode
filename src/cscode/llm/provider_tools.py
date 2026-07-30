# Provider-defined Tools
# Task 3.3: P1.2 - Provider-defined Tools

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

# Provider tool definitions
ANTHROPIC_TOOLS = {
    "web_search": {
        "name": "web_search",
        "description": "Search the web for information",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}
    },
    "code_execution": {
        "name": "code_execution",
        "description": "Execute code in a sandboxed environment",
        "input_schema": {"type": "object", "properties": {"code": {"type": "string"}, "language": {"type": "string"}}}
    },
}

OPENAI_TOOLS = {
    "web_search": {
        "name": "web_search",
        "description": "Search the web for current information",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    },
    "file_search": {
        "name": "file_search",
        "description": "Search through files for information",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    },
    "code_interpreter": {
        "name": "code_interpreter",
        "description": "Execute Python code and return results",
        "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}
    },
}

@dataclass
class ProviderTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    executor: Callable[..., Awaitable[Any]] | None = None

@dataclass
class ProviderToolExecutor:
    provider_name: str
    tools: dict[str, ProviderTool] = field(default_factory=dict)
    _client: httpx.AsyncClient | None = None

    @classmethod
    def for_anthropic(cls) -> ProviderToolExecutor:
        executor = cls(provider_name="anthropic")
        for name, spec in ANTHROPIC_TOOLS.items():
            executor.tools[name] = ProviderTool(
                name=spec["name"],
                description=spec["description"],
                input_schema=spec["input_schema"],
            )
        return executor

    @classmethod
    def for_openai(cls) -> ProviderToolExecutor:
        executor = cls(provider_name="openai")
        for name, spec in OPENAI_TOOLS.items():
            executor.tools[name] = ProviderTool(
                name=spec["name"],
                description=spec["description"],
                input_schema=spec["parameters"],
            )
        return executor

    def add_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        executor: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        """Register a tool with this executor."""
        self.tools[name] = ProviderTool(
            name=name,
            description=description,
            input_schema=input_schema,
            executor=executor,
        )

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}}
            for t in self.tools.values()
        ]

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        tool = self.tools[tool_name]
        if tool.executor:
            return await tool.executor(**arguments)
        return {"status": "not_implemented", "tool": tool_name}

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
