"""Contract tests for Tool v2 interface.

Every Tool implementation MUST pass these tests.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from cscode.tools2 import Tool, ToolResult
from cscode.tools2.registry import ToolRegistry
from cscode.schema.tool import ToolDefinition


class TestToolContract:
    """Interface contract: every Tool must conform to these."""

    def test_tool_has_name(self, tool: Tool[Any, Any]) -> None:
        assert tool.name, f"Tool {type(tool).__name__} must have a non-empty name"

    def test_tool_has_description(self, tool: Tool[Any, Any]) -> None:
        assert tool.description, f"Tool {tool.name} must have a description"

    def test_tool_has_input_schema(self, tool: Tool[Any, Any]) -> None:
        schema = tool.input_schema
        assert issubclass(schema, BaseModel), f"{tool.name}.input_schema must be a Pydantic BaseModel"

    def test_tool_has_output_schema(self, tool: Tool[Any, Any]) -> None:
        schema = tool.output_schema
        assert issubclass(schema, BaseModel), f"{tool.name}.output_schema must be a Pydantic BaseModel"

    def test_to_definition_returns_tool_definition(self, tool: Tool[Any, Any]) -> None:
        definition = tool.to_definition()
        assert isinstance(definition, ToolDefinition)
        assert definition.name == tool.name
        assert definition.description == tool.description
        assert "type" in definition.input_schema  # JSON Schema must have "type": "object"

    def test_execute_returns_tool_result(self, tool: Tool[Any, Any]) -> None:
        """All tools must at least handle an empty/minimal input gracefully
        (return ToolResult, not raise). Specific valid/invalid input
        behavior is tested per-tool."""
        # Create minimal valid input
        minimal = _minimal_input(tool.input_schema)
        result = _safe_execute(tool, minimal)
        assert isinstance(result, ToolResult)

    def test_registry_register_and_get(self, registry_with_tools: ToolRegistry) -> None:
        """Registry contract: register + get + list."""
        tools = registry_with_tools.list_tools()
        assert len(tools) > 0
        for name in tools:
            t = registry_with_tools.get(name)
            assert t is not None
            assert t.name == name

    def test_registry_to_definitions(self, registry_with_tools: ToolRegistry) -> None:
        definitions = registry_with_tools.to_definitions()
        assert len(definitions) == len(registry_with_tools.list_tools())
        for d in definitions:
            assert isinstance(d, ToolDefinition)

    def test_registry_materialize(self, registry_with_tools: ToolRegistry) -> None:
        definitions, settle = registry_with_tools.materialize()
        assert len(definitions) > 0
        assert callable(settle)

    def test_registry_duplicate_name_raises(self, registry_with_tools: ToolRegistry) -> None:
        """Registering a tool with a duplicate name must raise ValueError."""
        from cscode.tools2.base import Tool
        from pydantic import BaseModel

        class _DupInput(BaseModel):
            pass

        class _DupOutput(BaseModel):
            pass

        class _DupTool(Tool[_DupInput, _DupOutput]):
            name = registry_with_tools.list_tools()[0]
            description = "duplicate"
            input_schema = _DupInput
            output_schema = _DupOutput

            async def execute(self, input: _DupInput) -> ToolResult[_DupOutput]:
                return ToolResult(success=True, data=_DupOutput())

        with pytest.raises(ValueError, match="already registered"):
            registry_with_tools.register(_DupTool())

    def test_parse_tool_call_function_format(self) -> None:
        """Standard format: {function: {name, arguments}}"""
        name, args, error = ToolRegistry.parse_tool_call(
            {"function": {"name": "read", "arguments": {"path": "/tmp/x"}}}
        )
        assert name == "read"
        assert args == {"path": "/tmp/x"}
        assert error is None

    def test_parse_tool_call_flat_format(self) -> None:
        """Fallback format: {name, arguments}"""
        name, args, error = ToolRegistry.parse_tool_call(
            {"name": "bash", "arguments": "ls -la"}
        )
        assert name == "bash"

    def test_parse_tool_call_json_string(self) -> None:
        name, args, error = ToolRegistry.parse_tool_call(
            '{"function": {"name": "grep", "arguments": {"pattern": "foo"}}}'
        )
        assert name == "grep"
        assert args == {"pattern": "foo"}
        assert error is None

    def test_parse_tool_call_missing_name(self) -> None:
        name, args, error = ToolRegistry.parse_tool_call({"function": {}})
        assert name == ""
        assert error is not None

    def test_parse_tool_call_invalid_json(self) -> None:
        name, args, error = ToolRegistry.parse_tool_call("not json")
        assert name == ""
        assert error is not None


def _minimal_input(model: type[BaseModel]) -> BaseModel:
    """Create a minimal valid instance of a Pydantic model."""
    fields = model.model_fields
    kwargs: dict[str, Any] = {}
    for field_name, field_info in fields.items():
        # Try to provide sensible defaults based on type
        type_hint = str(field_info.annotation)
        if "bool" in type_hint:
            kwargs[field_name] = False
        elif "int" in type_hint:
            kwargs[field_name] = 0
        elif "float" in type_hint:
            kwargs[field_name] = 0.0
        elif "list" in type_hint:
            kwargs[field_name] = []
        elif "dict" in type_hint:
            kwargs[field_name] = {}
        elif field_info.default is not None and field_info.default != ...:
            # Field has a default, skip it
            continue
        else:
            # String or other — use "test" if the field doesn't have a default
            kwargs[field_name] = "test"
    return model(**kwargs)


def _safe_execute(tool: Tool[Any, Any], input: BaseModel) -> ToolResult[Any]:
    """Execute tool safely using asyncio.run()."""
    import asyncio

    return asyncio.run(tool.execute(input))
