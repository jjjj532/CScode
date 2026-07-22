"""Tests for LegacyToolAdapter — v1 BaseTool → v2 Tool adapter.

RED phase: all tests should fail because adapter.py doesn't exist yet.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from cscode.schema.tool import ToolResult as V1ToolResult
from cscode.tools.base import BaseTool


# ── Helper v1 tools for testing ────────────────────────────────────────


class _NoParamTool(BaseTool):
    """v1 tool with no parameters."""
    name = "no_params"
    description = "Tool with no parameters"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, args: dict[str, Any]) -> V1ToolResult:
        return V1ToolResult(success=True, data="done")


class _GreetingTool(BaseTool):
    """v1 tool with string parameters."""
    name = "greet"
    description = "Greet someone"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name to greet",
            },
            "greeting": {
                "type": "string",
                "description": "Greeting message",
            },
        },
        "required": ["name"],
    }

    async def execute(self, args: dict[str, Any]) -> V1ToolResult:
        return V1ToolResult(
            success=True,
            data=f"{args.get('greeting', 'Hello')}, {args['name']}!",
        )


class _CalcTool(BaseTool):
    """v1 tool with mixed parameter types."""
    name = "calc"
    description = "Do a calculation"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "a": {"type": "integer", "description": "First number"},
            "b": {"type": "number", "description": "Second number"},
            "verbose": {"type": "boolean", "description": "Verbose output"},
        },
        "required": ["a", "b"],
    }

    async def execute(self, args: dict[str, Any]) -> V1ToolResult:
        total = args["a"] + args["b"]
        if args.get("verbose"):
            return V1ToolResult(success=True, data=f"Result: {total}")
        return V1ToolResult(success=True, data=str(total))


class _FailingTool(BaseTool):
    """v1 tool that fails."""
    name = "failer"
    description = "Always fails"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "msg": {"type": "string", "description": "Error message"},
        },
    }

    async def execute(self, args: dict[str, Any]) -> V1ToolResult:
        return V1ToolResult(
            success=False,
            data="",
            error=args.get("msg", "generic error"),
        )


# ── Tests ──────────────────────────────────────────────────────────────


class TestLegacyToolAdapter:
    """Tests for LegacyToolAdapter."""

    def test_wraps_tool_name_and_description(self) -> None:
        """Adapter preserves name and description from v1 tool."""
        from cscode.tools2.adapter import LegacyToolAdapter

        adapted = LegacyToolAdapter(_GreetingTool)
        assert adapted.name == "greet"
        assert adapted.description == "Greet someone"

    def test_input_schema_is_pydantic_base_model(self) -> None:
        """Adapter generates a Pydantic BaseModel for input_schema."""
        from cscode.tools2.adapter import LegacyToolAdapter

        adapted = LegacyToolAdapter(_GreetingTool)
        assert issubclass(adapted.input_schema, BaseModel)

    def test_input_schema_has_correct_fields(self) -> None:
        """Generated schema has fields matching v1 parameters."""
        from cscode.tools2.adapter import LegacyToolAdapter

        adapted = LegacyToolAdapter(_GreetingTool)
        schema = adapted.input_schema.model_fields
        assert "name" in schema
        assert "greeting" in schema
        assert schema["name"].is_required() is True  # required
        assert schema["greeting"].is_required() is False  # optional

    def test_input_schema_with_no_params(self) -> None:
        """Tool with no parameters still gets valid empty schema."""
        from cscode.tools2.adapter import LegacyToolAdapter

        adapted = LegacyToolAdapter(_NoParamTool)
        assert issubclass(adapted.input_schema, BaseModel)
        # Should still work — empty model is valid
        instance = adapted.input_schema()
        assert instance.model_dump() == {}

    def test_input_schema_mixed_types(self) -> None:
        """Integer, number, boolean fields are typed correctly."""
        from cscode.tools2.adapter import LegacyToolAdapter

        adapted = LegacyToolAdapter(_CalcTool)
        hints = adapted.input_schema.model_fields
        assert hints["a"].annotation is int
        assert hints["b"].annotation is float
        verbose_ann = hints["verbose"].annotation
        from typing import get_origin, get_args
        assert get_origin(verbose_ann) is type(None) or bool in get_args(verbose_ann)

    async def test_execute_with_valid_args(self) -> None:
        """Adapter delegates to v1 tool and returns v2 ToolResult."""
        from cscode.tools2.adapter import LegacyToolAdapter

        adapted = LegacyToolAdapter(_GreetingTool)
        result = await adapted.execute(
            adapted.input_schema(name="World", greeting="Hi")
        )
        assert result.success
        assert result.data is not None
        assert result.data.result == "Hi, World!"

    async def test_execute_no_params(self) -> None:
        """Tool with no parameters executes successfully."""
        from cscode.tools2.adapter import LegacyToolAdapter

        adapted = LegacyToolAdapter(_NoParamTool)
        result = await adapted.execute(adapted.input_schema())
        assert result.success
        assert result.data is not None

    async def test_execute_returns_error_on_failure(self) -> None:
        """Adapter propagates v1 tool errors."""
        from cscode.tools2.adapter import LegacyToolAdapter

        adapted = LegacyToolAdapter(_FailingTool)
        result = await adapted.execute(
            adapted.input_schema(msg="something went wrong")
        )
        assert not result.success
        assert result.data is None
        assert "something went wrong" in (result.error or "")

    async def test_execute_with_optional_args(self) -> None:
        """Optional params default to None / missing."""
        from cscode.tools2.adapter import LegacyToolAdapter

        adapted = LegacyToolAdapter(_GreetingTool)
        result = await adapted.execute(adapted.input_schema(name="World"))
        assert result.success
        assert result.data is not None
        assert result.data.result == "Hello, World!"

    def test_to_definition_returns_valid_tool_definition(self) -> None:
        """Adapter produces valid ToolDefinition for the LLM."""
        from cscode.tools2.adapter import LegacyToolAdapter

        adapted = LegacyToolAdapter(_CalcTool)
        defn = adapted.to_definition()
        assert defn.name == "calc"
        assert defn.description == "Do a calculation"
        assert "type" in defn.input_schema
        assert "properties" in defn.input_schema
        props = defn.input_schema["properties"]
        assert isinstance(props, dict)
        assert "a" in props
        assert "b" in props

    async def test_adapter_is_compatible_with_tool_registry_v2(self) -> None:
        """Adapter can be registered and settle() works through registry."""
        from cscode.core.tool_registry import ToolRegistryV2
        from cscode.tools2.adapter import LegacyToolAdapter

        registry = ToolRegistryV2()
        adapted = LegacyToolAdapter(_GreetingTool)
        registry.register_tool(adapted)

        materialization = registry.materialize()
        assert len(materialization.definitions) == 1

        result = await materialization.settle("greet", {"name": "Tester"})
        assert result.success
        assert result.data is not None
        assert "Tester" in str(result.data)
