"""LLM Event types — standardized event stream emitted by LLM providers.

Mirrors OpenCode's 16-type LLMEvent union. Every event is a frozen dataclass
with a 'type' discriminator for exhaustive match/case.

Event lifecycle for a typical provider call with one tool:

    Pending
    → ReasoningStarted → ReasoningDelta* → ReasoningEnded
    → TextStarted → TextDelta* → TextEnded
    → ToolCallStarted → ToolCallDelta* → ToolCallEnded
    → ToolResult | ToolFailure
    → Finish | Error

Events marked with * may produce zero or more deltas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from cscode.schema.errors import LLMError
from cscode.schema.ids import ToolCallID

# ─── Text Events ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TextStarted:
    """Text generation has started.

    Emitted exactly once per text segment before the first delta.
    """

    type: Literal["text-started"] = field(default="text-started", init=False)


@dataclass(frozen=True, slots=True)
class TextDelta:
    """A chunk of generated text."""

    type: Literal["text-delta"] = field(default="text-delta", init=False)
    text: str


@dataclass(frozen=True, slots=True)
class TextEnded:
    """Text generation has completed.

    The full_text is the complete concatenation of all deltas.
    """

    type: Literal["text-ended"] = field(default="text-ended", init=False)
    full_text: str


# ─── Tool Call Events ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ToolCallStarted:
    """A tool call has been initiated by the model.

    Emitted before the first delta. The name and partial ID are known
    immediately; arguments arrive incrementally via ToolCallDelta.
    """

    type: Literal["tool-call-started"] = field(default="tool-call-started", init=False)
    tool_call_id: ToolCallID
    name: str


@dataclass(frozen=True, slots=True)
class ToolCallDelta:
    """An incremental chunk of tool call arguments (JSON string)."""

    type: Literal["tool-call-delta"] = field(default="tool-call-delta", init=False)
    tool_call_id: ToolCallID
    args_text: str


@dataclass(frozen=True, slots=True)
class ToolCallEnded:
    """A tool call's arguments are complete.

    The args field is the fully parsed argument dict.
    """

    type: Literal["tool-call-ended"] = field(default="tool-call-ended", init=False)
    tool_call_id: ToolCallID
    name: str
    args: dict[str, object]


# ─── Tool Result Events ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ToolResult:
    """A tool executed successfully and produced output."""

    type: Literal["tool-result"] = field(default="tool-result", init=False)
    tool_call_id: ToolCallID
    result: str


@dataclass(frozen=True, slots=True)
class ToolFailure:
    """A tool failed during execution (error inside the tool handler)."""

    type: Literal["tool-failure"] = field(default="tool-failure", init=False)
    tool_call_id: ToolCallID
    error: str


# ─── Reasoning Events ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ReasoningStarted:
    """Model has started its internal reasoning trace."""

    type: Literal["reasoning-started"] = field(default="reasoning-started", init=False)
    signature: str | None = None


@dataclass(frozen=True, slots=True)
class ReasoningDelta:
    """A chunk of reasoning text."""

    type: Literal["reasoning-delta"] = field(default="reasoning-delta", init=False)
    text: str
    signature: str | None = None


@dataclass(frozen=True, slots=True)
class ReasoningEnded:
    """Model's reasoning trace is complete."""

    type: Literal["reasoning-ended"] = field(default="reasoning-ended", init=False)
    text: str
    signature: str | None = None


# ─── Terminal Events ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Finish:
    """Normal end of the LLM response stream.

    Contains the finish reason and token usage when available.
    """

    type: Literal["finish"] = field(default="finish", init=False)
    finish_reason: str  # "stop" | "tool_use" | "length" | "content_filter"
    usage: dict[str, int] | None = None  # {"prompt_tokens": ..., "completion_tokens": ...}


@dataclass(frozen=True, slots=True)
class Error:
    """An unrecoverable error occurred during generation.

    The associated LLMError carries structured details.
    """

    type: Literal["error"] = field(default="error", init=False)
    error: LLMError


@dataclass(frozen=True, slots=True)
class Pending:
    """Provider has not yet started generating (UI hint).

    Useful for showing a "waiting for model..." indicator before the
    first substantive event arrives.
    """

    type: Literal["pending"] = field(default="pending", init=False)


# ─── LLMEvent Union ────────────────────────────────────────────────

LLMEvent = (
    TextStarted
    | TextDelta
    | TextEnded
    | ToolCallStarted
    | ToolCallDelta
    | ToolCallEnded
    | ToolResult
    | ToolFailure
    | ReasoningStarted
    | ReasoningDelta
    | ReasoningEnded
    | Finish
    | Error
    | Pending
)
"""Union of all LLM event types. Exactly 15 members."""


def assert_never(value: object) -> None:
    """Exhaustiveness check for match/case blocks.

    Call at the end of every match block that handles an LLMEvent variant.
    If a new variant is added to LLMEvent and this match block is not updated,
    the type checker will flag the call because the new variant's type is
    not compatible with Never.
    """
    msg = f"Unhandled variant: {type(value).__name__} ({value!r})"
    raise RuntimeError(msg)
