"""TDD tests for ToolRegistryV2 — scope-aware registration + permission-filtered materialize.

Written FIRST (TDD): tests MUST fail before implementation exists.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from cscode.core.permission_v2 import Rule, RuleEffect, Ruleset
from cscode.tools2.base import Tool, ToolResult

# ─── Fixture tools ────────────────────────────────────────────────

class _ReadInput(BaseModel):
    path: str


class _ReadOutput(BaseModel):
    content: str


class _ReadTool(Tool[_ReadInput, _ReadOutput]):
    name = "read"
    description = "Read a file"
    input_schema = _ReadInput
    output_schema = _ReadOutput

    async def execute(self, input: _ReadInput) -> ToolResult[_ReadOutput]:
        return ToolResult(success=True, data=_ReadOutput(content="file content"))


class _BashInput(BaseModel):
    command: str


class _BashOutput(BaseModel):
    output: str


class _BashTool(Tool[_BashInput, _BashOutput]):
    name = "bash"
    description = "Run a shell command"
    input_schema = _BashInput
    output_schema = _BashOutput

    async def execute(self, input: _BashInput) -> ToolResult[_BashOutput]:
        return ToolResult(success=True, data=_BashOutput(output="ok"))


# ─── These imports MUST fail until ToolRegistryV2 exists ───────────

class TestToolRegistryV2:
    """TDD: will fail on import until ToolRegistryV2 is implemented."""

    def test_import(self) -> None:
        """Test will fail until ToolRegistryV2 exists in core."""
        from cscode.core.tool_registry import Scope, ToolRegistryV2  # noqa: F811
        assert Scope is not None
        assert ToolRegistryV2 is not None


class TestScopeRegistration:
    """Verify scope-aware registration."""

    def test_register_application_scope(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("read", _ReadTool(), Scope.APPLICATION)
        assert "read" in reg.list_tools(Scope.APPLICATION)
        assert "read" not in reg.list_tools(Scope.LOCATION)

    def test_register_location_scope(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("read", _ReadTool(), Scope.LOCATION)
        assert "read" in reg.list_tools(Scope.LOCATION)
        assert "read" not in reg.list_tools(Scope.APPLICATION)

    def test_duplicate_name_raises(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("read", _ReadTool(), Scope.APPLICATION)
        with pytest.raises(ValueError, match="already registered"):
            reg.register("read", _ReadTool(), Scope.LOCATION)

    def test_list_all(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("read", _ReadTool(), Scope.APPLICATION)
        reg.register("bash", _BashTool(), Scope.LOCATION)
        all_tools = reg.list_tools()  # no scope = all
        assert set(all_tools) == {"read", "bash"}


class TestMaterialize:
    """Verify permission-filtered materialize."""

    def test_definition_contains_tool_info(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("read", _ReadTool(), Scope.APPLICATION)
        mat = reg.materialize()
        names = [d.name for d in mat.definitions]
        assert "read" in names

    def test_definition_has_schema(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("read", _ReadTool(), Scope.APPLICATION)
        mat = reg.materialize()
        read_def = next(d for d in mat.definitions if d.name == "read")
        assert "path" in read_def.input_schema.get("properties", {})

    @pytest.mark.asyncio
    async def test_settle_executes_tool(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("read", _ReadTool(), Scope.APPLICATION)

        mat = reg.materialize()
        result = await mat.settle("read", {"path": "/tmp/x"})

        assert result.success is True
        assert result.data is not None
        assert result.data.content == "file content"

    @pytest.mark.asyncio
    async def test_settle_unknown_tool(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("read", _ReadTool(), Scope.APPLICATION)

        mat = reg.materialize()
        result = await mat.settle("nonexistent", {})

        assert result.success is False
        assert "Unknown tool" in (result.error or "")

    @pytest.mark.asyncio
    async def test_settle_validation_error(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("read", _ReadTool(), Scope.APPLICATION)

        mat = reg.materialize()
        result = await mat.settle("read", {"wrong_key": "x"})

        assert result.success is False
        assert "Invalid arguments" in (result.error or "")


class TestMaterializeWithPermissions:
    """Verify permission-filtered materialize."""

    def test_allow_all_returns_all_tools(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("read", _ReadTool(), Scope.APPLICATION)
        reg.register("bash", _BashTool(), Scope.LOCATION)

        ruleset = Ruleset(name="allow-all", rules=[
            Rule(action="*", resource="*", effect=RuleEffect.ALLOW),
        ])
        mat = reg.materialize(permissions=[ruleset])
        names = [d.name for d in mat.definitions]
        assert "read" in names
        assert "bash" in names

    def test_deny_all_excludes_all_tools(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("read", _ReadTool(), Scope.APPLICATION)

        ruleset = Ruleset(name="deny-all", rules=[
            Rule(action="*", resource="*", effect=RuleEffect.DENY),
        ])
        mat = reg.materialize(permissions=[ruleset])
        assert mat.definitions == []

    def test_selective_deny_filters_one_tool(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("read", _ReadTool(), Scope.APPLICATION)
        reg.register("bash", _BashTool(), Scope.LOCATION)

        ruleset = Ruleset(name="no-bash", rules=[
            Rule(action="*", resource="*", effect=RuleEffect.ALLOW),
            Rule(action="bash", resource="*", effect=RuleEffect.DENY),
        ])
        mat = reg.materialize(permissions=[ruleset])
        names = [d.name for d in mat.definitions]
        assert "read" in names
        assert "bash" not in names

    @pytest.mark.asyncio
    async def test_settle_denied_tool_returns_no_permission(self) -> None:
        from cscode.core.tool_registry import Scope, ToolRegistryV2
        reg = ToolRegistryV2()
        reg.register("bash", _BashTool(), Scope.APPLICATION)

        ruleset = Ruleset(name="deny-bash", rules=[
            Rule(action="bash", resource="*", effect=RuleEffect.DENY),
        ])
        mat = reg.materialize(permissions=[ruleset])
        result = await mat.settle("bash", {"command": "ls"})
        assert result.success is False
        assert "not permitted" in (result.error or "").lower()
