"""Tool-related types for LLM tool definition and invocation control.

Mirrors OpenCode's ToolDefinition and ToolChoice types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """A tool advertised to the LLM via the provider API.

    The LLM uses the name and description to decide when to call the tool,
    and uses the input_schema to construct valid arguments.
    """

    name: str
    """Unique tool name (alphanumeric + underscores + hyphens)."""

    description: str
    """Description of what the tool does. The LLM uses this to decide
    whether to call the tool."""

    input_schema: dict[str, object]
    """JSON Schema describing the expected input parameters."""


@dataclass
class ToolResult:
    """Result from executing a tool."""
    success: bool
    data: str
    error: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


ToolChoice = Literal["auto", "required", "none"] | str
"""Controls how the LLM selects which tool to call.

  - "auto":    LLM decides whether to call a tool (default)
  - "required":LLM MUST call a tool (may still return text)
  - "none":    No tool calls allowed
  - "<name>":  Force a specific tool by name (provider support varies)
"""
