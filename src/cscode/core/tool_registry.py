"""ToolRegistryV2 — scope-aware registration with permission-filtered materialize.

Architecture (from cscode-rearchitecture.md):
  ToolRegistryV2:
    application_tools: dict[str, Tool]   # 进程级
    location_tools: dict[str, Tool]      # 项目级

    def register(name, tool, scope):
    def materialize(permissions) -> Materialization:
        # 按权限过滤 → definitions(给LLM) + settle(执行)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from cscode.core.permission_v2 import PermissionV2, Ruleset
from cscode.schema.tool import ToolDefinition
from cscode.tools2.base import Tool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class Scope(StrEnum):
    APPLICATION = "application"
    LOCATION = "location"


@dataclass
class Materialization:
    """Result of materialize(): definitions for the LLM + settle for execution."""

    definitions: list[ToolDefinition]
    settle: Any  # async (name: str, args: dict) -> ToolResult


class ToolRegistryV2:
    """Scope-aware tool registry with permission-filtered materialize.

    Two scopes:
        APPLICATION — process-level tools (always available)
        LOCATION — project-level tools (per-repo config)

    Materialize consumes a PermissionV2 ruleset to include/exclude tools.
    """

    def __init__(self) -> None:
        self._application_tools: dict[str, Tool[Any, Any]] = {}
        self._location_tools: dict[str, Tool[Any, Any]] = {}

    # ─── Registration ──────────────────────────────────────────────

    def register_tool(
        self,
        tool: Tool[Any, Any],
        scope: Scope = Scope.APPLICATION,
    ) -> None:
        """Register a tool by its .name attribute (convenience wrapper)."""
        self.register(tool.name, tool, scope)

    def register(self, name: str, tool: Tool[Any, Any], scope: Scope) -> None:
        """Register a tool under the given scope.

        Raises ValueError if the name is already registered in any scope.
        """
        if name in self._application_tools or name in self._location_tools:
            logger.warning("ToolRegistryV2.register: duplicate tool=%s", name)
            msg = f"Tool '{name}' is already registered"
            raise ValueError(msg)

        if scope == Scope.APPLICATION:
            self._application_tools[name] = tool
        else:
            self._location_tools[name] = tool

        logger.debug("ToolRegistryV2.register: tool=%s scope=%s", name, scope)

    # ─── Listing ───────────────────────────────────────────────────

    def list_tools(self, scope: Scope | None = None) -> list[str]:
        """List tool names, optionally filtered by scope."""
        if scope == Scope.APPLICATION:
            return list(self._application_tools.keys())
        if scope == Scope.LOCATION:
            return list(self._location_tools.keys())
        return list(self._application_tools.keys()) + list(self._location_tools.keys())

    # ─── Materialize ───────────────────────────────────────────────

    def materialize(
        self,
        permissions: list[Ruleset] | None = None,
    ) -> Materialization:
        """Materialize tools for LLM consumption.

        Args:
            permissions: Optional list of Rulesets. When provided, only tools
                         whose action is ALLOWED by the rulesets are included.

        Returns:
            Materialization with:
                definitions — ToolDefinition list to send to the LLM
                settle — async (name, args) -> ToolResult callable
        """
        tools = dict(self._application_tools)
        tools.update(self._location_tools)

        # Filter by permissions — keep denied names for better error messages
        denied: set[str] = set()
        if permissions:
            filtered: dict[str, Tool[Any, Any]] = {}
            for name, tool in tools.items():
                if PermissionV2.is_allowed(name, "*", permissions):
                    filtered[name] = tool
                else:
                    denied.add(name)
            tools = filtered

        definitions = [tool.to_definition() for tool in tools.values()]
        logger.debug(
            "ToolRegistryV2.materialize: total=%d permitted=%d denied=%d",
            len(self._application_tools) + len(self._location_tools),
            len(tools),
            len(denied),
        )

        async def settle(name: str, raw_args: dict[str, object]) -> ToolResult[Any]:
            """Execute a tool call with Pydantic validation."""
            if name in denied:
                logger.warning("settle: denied tool=%s", name)
                return ToolResult(
                    success=False,
                    error=f"Tool '{name}' is not permitted by current rules",
                )
            tool = tools.get(name)
            if tool is None:
                logger.error("settle: unknown tool=%s", name)
                return ToolResult(
                    success=False,
                    error=f"Unknown tool: {name}",
                )

            logger.debug("settle: tool=%s args_keys=%s", name, list(raw_args.keys()))

            # Validate input via Pydantic
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

        return Materialization(definitions=definitions, settle=settle)
