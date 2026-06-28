"""ToolRuntime — dispatches tool calls to registered tool handlers.

The ToolRuntime is responsible for taking a completed ToolCallEnded event
and executing the corresponding tool handler. It decouples tool execution
from the LLM streaming layer.

Usage:
    runtime = ToolRuntime(tools={"read": read_handler, "write": write_handler})
    async for event in runtime.dispatch(tool_call_event):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from cscode.schema.events import LLMEvent, ToolResult
from cscode.schema.events import ToolFailure as EventToolFailure
from cscode.schema.ids import ToolCallID
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class ToolRuntime:
    """Dispatches tool calls to registered handlers.

    Each tool is registered as a callable that accepts the tool arguments
    and returns a string result. The runtime handles errors by producing
    ToolFailure events instead of raising exceptions.
    """

    def __init__(self, tools: dict[str, Callable[..., Any]] | None = None) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        if tools:
            self._tools.update(tools)

    def register(self, name: str, handler: Callable[..., Any]) -> None:
        """Register a tool handler by name.

        Args:
            name: Tool name (must match ToolDefinition.name).
            handler: Async or sync callable that accepts **kwargs and returns str.
        """
        logger.debug("Tool registered: %s", name)
        self._tools[name] = handler

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    async def dispatch(
        self,
        tool_call_id: ToolCallID,
        name: str,
        args: dict[str, object],
    ) -> AsyncIterator[LLMEvent]:
        """Execute a tool call and yield result events.

        Yields:
            ToolResult on success, ToolFailure on error.
        """
        handler = self._tools.get(name)
        if handler is None:
            logger.warning("Unknown tool: %s", name)
            yield EventToolFailure(
                tool_call_id=tool_call_id,
                error=f"Unknown tool: {name}",
            )
            return

        logger.debug("Dispatching tool: %s args_keys=%s", name, list(args.keys()))
        try:
            result = await self._execute(handler, args)
            logger.debug("Tool %s completed: %d chars", name, len(str(result)))
            yield ToolResult(tool_call_id=tool_call_id, result=str(result))
        except Exception as e:
            logger.error("Tool %s failed: %s", name, e)
            yield EventToolFailure(
                tool_call_id=tool_call_id,
                error=f"Tool {name} failed: {e}",
            )

    async def _execute(self, handler: Callable[..., Any], args: dict[str, object]) -> str:
        result = handler(**args)
        if hasattr(result, "__await__"):
            result = await result
        return str(result)
