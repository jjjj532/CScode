"""LegacyToolAdapter — wraps v1 BaseTool as v2 Tool.

Bridge between the old tool system (``cscode.tools.base.BaseTool``) and
the new typed tool system (``cscode.tools2.base.Tool``).

Usage:
    from cscode.tools.base import BaseTool
    from cscode.tools2.adapter import LegacyToolAdapter

    class MyTool(BaseTool):
        name = "my_tool"
        ...

    adapter = LegacyToolAdapter(MyTool)
    registry = ToolRegistryV2()
    registry.register_tool(adapter)
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, Field, create_model

from cscode.schema.tool import ToolDefinition
from cscode.tools.base import BaseTool
from cscode.tools.base import ToolResult as V1ToolResult
from cscode.tools2.base import Tool, ToolResult

# Mapping from JSON Schema types to Python type annotations
_JSON_TYPE_MAP: dict[str, type[Any]] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _json_schema_to_pydantic(
    name: str,
    parameters: dict[str, Any],
) -> type[BaseModel]:
    """Convert a JSON Schema ``parameters`` dict to a Pydantic ``BaseModel``.

    Args:
        name: Name hint for the generated model class.
        parameters: JSON Schema dict with ``properties`` and optional ``required``.
            Expected shape::

                {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "..."},
                        ...
                    },
                    "required": ["key1"],
                }

    Returns:
        A dynamically created Pydantic ``BaseModel`` subclass.
    """
    properties: dict[str, Any] = parameters.get("properties", {})
    required_fields: list[str] = parameters.get("required", [])

    fields: dict[str, Any] = {}
    for field_name, meta in properties.items():
        json_type = meta.get("type", "string")
        py_type = _JSON_TYPE_MAP.get(json_type, str)
        description = meta.get("description", "")

        if field_name in required_fields:
            fields[field_name] = (py_type, Field(description=description))
        else:
            fields[field_name] = (
                py_type | None,
                Field(default=None, description=description),
            )

    return cast(type[BaseModel], create_model(f"{name}_input", **fields))


class _SimpleOutput(BaseModel):
    """Generic output model wrapping a string result."""
    result: str = ""


class LegacyToolAdapter(Tool[BaseModel, _SimpleOutput]):
    """Adapter that wraps a v1 ``BaseTool`` class as a v2 ``Tool[I, O]``.

    The adapter:
      - Reads ``name``, ``description``, ``parameters`` from the v1 tool class
      - Dynamically generates a Pydantic input model from the JSON Schema
      - Delegates ``execute()`` to the v1 tool's ``execute(args: dict)``
      - Converts the v1 ``ToolResult(data: str)`` to v2 ``ToolResult[_SimpleOutput]``

    Example::

        adapted = LegacyToolAdapter(MyV1Tool)
        registry.register_tool(adapted)
    """

    def __init__(self, v1_tool_cls: type[BaseTool]) -> None:
        self._v1_cls = v1_tool_cls
        self.name = v1_tool_cls.name
        self.description = v1_tool_cls.description
        self.input_schema = _json_schema_to_pydantic(
            v1_tool_cls.name,
            v1_tool_cls.parameters,
        )
        self.output_schema = _SimpleOutput

    async def execute(self, input: BaseModel) -> ToolResult[_SimpleOutput]:
        """Execute the v1 tool with validated Pydantic input."""
        # Convert Pydantic model → dict (dropping None values for optional fields)
        args: dict[str, Any] = {}
        for k, v in input.model_dump().items():
            if v is not None:
                args[k] = v

        # Instantiate v1 tool and execute
        tool_instance = self._v1_cls()
        v1_result: V1ToolResult = await tool_instance.execute(args)

        if v1_result.success:
            return ToolResult(
                success=True,
                data=_SimpleOutput(result=v1_result.data),
                metadata=v1_result.metadata,
            )
        return ToolResult(
            success=False,
            error=v1_result.error or "Unknown error",
            metadata=v1_result.metadata,
        )

    def to_definition(self) -> ToolDefinition:
        """Produce an LLM-facing ToolDefinition.

        Override base to use explicit input_schema for type safety with
        dynamically generated models.
        """
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema.model_json_schema(),
        )
