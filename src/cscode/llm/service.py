"""LLM Service — typed interface for LLM generation with automatic tool loop.

This module defines the public API of the LLM layer.
Implementations live in adapters/ (legacy adapter) or directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from cscode.schema.events import LLMEvent
from cscode.schema.ids import ModelID
from cscode.schema.messages import Message
from cscode.schema.options import GenerationOptions
from cscode.schema.tool import ToolChoice


@dataclass(frozen=True, slots=True)
class ToolExecution:
    """Record of a single tool execution within a generation cycle.

    Captures the input, output, and timing of one tool call
    so callers can inspect what happened after generate() returns.
    """

    name: str
    """Tool name (e.g. 'Read', 'Bash')."""

    tool_call_id: str
    """Unique ID for this invocation within the session."""

    input: dict[str, object]
    """The validated argument dict sent to the tool."""

    output: str
    """Tool output text (success result or error message, empty string if None)."""

    success: bool
    """True if the tool completed without error."""

    duration_ms: float
    """Wall-clock execution time in milliseconds."""


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Result of a complete generation cycle.

    A cycle may include multiple tool rounds — the LLM calls tools,
    results are fed back, and the LLM generates more text.
    The final 'content' is the last assistant message after all tool rounds.
    """

    content: str
    """Final response text (after all tool rounds)."""

    tool_executions: tuple[ToolExecution, ...] = ()
    """All tool executions that occurred during this generation cycle,
    in chronological order."""

    usage: dict[str, int] | None = None
    """Token usage aggregated across all rounds.
    Keys: prompt_tokens, completion_tokens (provider-dependent)."""

    model: str = ""
    """Model identifier that generated the response."""

    finish_reason: str = ""
    """Why generation stopped: 'stop' | 'tool_use' | 'length' | 'max_rounds' | 'error'."""


class LLMService(ABC):
    """LLM generation service with automatic tool loop.

    Implementations handle:
    1. Converting Tool objects → ToolDefinitions for the provider
    2. Calling the LLM provider (complete or stream)
    3. Detecting tool_calls in the response
    4. Settling tool calls via ToolRegistry
    5. Feeding results back to the LLM
    6. Looping until the LLM stops calling tools
    """

    @abstractmethod
    async def generate(
        self,
        model: ModelID,
        messages: list[Message],
        *,
        tools: list[Any] | None = None,
        tool_choice: ToolChoice | None = None,
        system: str | None = None,
        options: GenerationOptions | None = None,
        max_tool_rounds: int | None = 50,
    ) -> LLMResponse:
        """Run a complete generation cycle (possibly multiple tool rounds).

        Args:
            model: Model identifier (e.g. 'gpt-4o', 'claude-3-5-sonnet').
            messages: Conversation history in schema.Message format.
            tools: Optional list of Tool objects available to the LLM.
            tool_choice: Control how the LLM selects tools.
            system: Optional system prompt override.
            options: Generation parameters (temperature, max_tokens, etc.).
            max_tool_rounds: Maximum tool call rounds before force-stopping.

        Returns:
            LLMResponse with final text and all tool execution records.

        Raises:
            LLMError: On provider errors (auth, rate limit, etc.).
        """
        ...

    @abstractmethod
    def stream(
        self,
        model: ModelID,
        messages: list[Message],
        *,
        tools: list[Any] | None = None,
        tool_choice: ToolChoice | None = None,
        system: str | None = None,
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[LLMEvent]:
        """Stream a single LLM request as structured events.

        Unlike generate(), stream() does NOT perform automatic tool
        loop. Each call corresponds to exactly one LLM API request.
        The caller is responsible for feeding ToolResult events back
        in subsequent stream() calls.

        Event sequence (see schema/events.py):
            Pending
            → ReasoningStarted → ReasoningDelta* → ReasoningEnded
            → TextStarted → TextDelta* → TextEnded
            → ToolCallStarted → ToolCallDelta* → ToolCallEnded
            → ToolResult | ToolFailure
            → Finish | Error

        Args:
            model: Model identifier.
            messages: Conversation history.
            tools: Optional tools for the LLM.
            tool_choice: Tool selection control.
            system: Optional system prompt override.
            options: Generation parameters.

        Yields:
            LLMEvent variants in the order they occur.
        """
        ...
