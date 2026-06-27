"""Tool v2 — 类型安全的 Tool 接口。

对比旧 BaseTool:
  - 旧: execute(args: dict[str, Any]) -> ToolResult(success, data: str, error)
  - 新: execute(input: I) -> ToolResult[O]，输入输出通过 Pydantic model 校验

对比 OpenCode Tool.make:
  - Tool.make({input Schema, output Schema, execute, toModelOutput})
  - 本接口等同: Tool[I, O] + to_definition() + format_error()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from pydantic import BaseModel

from cscode.schema.tool import ToolDefinition

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass
class ToolResult(Generic[OutputT]):
    """Typed result from a Tool execution.

    Generic over OutputT (output type), so callers know the shape of data on success.
    """

    success: bool
    data: OutputT | None = None
    error: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class Tool(ABC, Generic[InputT, OutputT]):
    """Type-safe Tool with Pydantic-validated input/output.

    Usage:
        class ReadInput(BaseModel):
            path: str

        class ReadOutput(BaseModel):
            content: str
            size: int

        class ReadTool(Tool[ReadInput, ReadOutput]):
            name = "read"
            description = "Read a file"
            input_schema = ReadInput
            output_schema = ReadOutput

            async def execute(self, input: ReadInput) -> ToolResult[ReadOutput]:
                ...
    """

    name: str = ""
    description: str = ""
    input_schema: type[InputT] = None  # type: ignore[assignment]  # subclasses MUST override
    output_schema: type[OutputT] = None  # type: ignore[assignment]  # subclasses MUST override

    @abstractmethod
    async def execute(self, input: InputT) -> ToolResult[OutputT]:
        """Execute the tool with validated input.

        Returns ToolResult on success/failure. Raises ToolFailure for
        unrecoverable errors that should abort the current step.
        """
        ...

    def to_definition(self) -> ToolDefinition:
        """Produce an LLM-facing ToolDefinition from this tool's schema.

        Replaces old to_llm_format() with a schema-driven approach.
        """
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema.model_json_schema(),
        )

    def format_error(self, error: Exception) -> str:
        """Format an execution error for user display.

        Override to customize error messages per tool (matching OpenCode's
        formatError pattern).
        """
        return f"{self.name} failed: {error}"
