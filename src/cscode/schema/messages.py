"""Message and Content Part types.

Mirrors OpenCode's schema where a Message contains a list of Parts
rather than a single content string. Each Part is a frozen dataclass
with a 'type' discriminator for exhaustive match/case.

Part types:
  - SystemPart:    system-level instructions (role=system only)
  - TextPart:      plain text content
  - MediaPart:     inline media (images, PDFs, etc.)
  - ToolCallPart:  LLM requesting a tool invocation
  - ToolResultPart:tool execution result fed back to the LLM
  - ReasoningPart: model's internal reasoning trace
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from cscode.schema.ids import AssistantMessageID, MessageID, ToolCallID

if TYPE_CHECKING:
    from cscode.llm.cache_policy import CacheHint

# ─── Content Parts ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SystemPart:
    """System-level instruction (role=system only, never appears in user/assistant)."""

    type: Literal["system"] = field(default="system", init=False)
    text: str


@dataclass(frozen=True, slots=True)
class TextPart:
    """Plain text content."""

    type: Literal["text"] = field(default="text", init=False)
    text: str


@dataclass(frozen=True, slots=True)
class MediaPart:
    """Inline media content.

    media_type is a MIME type (e.g. 'image/png', 'application/pdf').
    data is base64-encoded when serialized over the wire.
    """

    type: Literal["media"] = field(default="media", init=False)
    media_type: str
    data: str  # base64-encoded


@dataclass(frozen=True, slots=True)
class ToolCallPart:
    """LLM requesting a tool invocation.

    args is the parsed argument dict (not a JSON string).
    """

    type: Literal["tool-call"] = field(default="tool-call", init=False)
    tool_call_id: ToolCallID
    name: str
    args: dict[str, object]


@dataclass(frozen=True, slots=True)
class ToolResultPart:
    """Tool execution result fed back to the LLM.

    When is_error is True, 'result' contains the error message.

    G-3 (spec §4.3.3): 增补 ``provider_executed``（provider 预执行标记，
    如 Anthropic computer use）、``cache``（CacheHint）与 ``metadata``。
    """

    type: Literal["tool-result"] = field(default="tool-result", init=False)
    tool_call_id: ToolCallID
    name: str
    result: str
    is_error: bool = False
    provider_executed: bool = False
    cache: CacheHint | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReasoningPart:
    """Model's internal reasoning trace.

    signature, when present, is a cryptographic signature of the
    reasoning content (Anthropic extended thinking).
    """

    type: Literal["reasoning"] = field(default="reasoning", init=False)
    text: str
    signature: str | None = None


# ─── Part Union ────────────────────────────────────────────────────

Part = (
    SystemPart
    | TextPart
    | MediaPart
    | ToolCallPart
    | ToolResultPart
    | ReasoningPart
)
"""Union of all content part types. Use match/case + assert_never to discriminate."""


# ─── Message ────────────────────────────────────────────────────────


class MessageRole:
    """Role constants matching OpenAI/Anthropic conventions.

    Constants:
        SYSTEM: system-level instructions
        USER: human input
        ASSISTANT: model output (text + tool calls)
        TOOL: tool execution results
    """

    SYSTEM: str = "system"
    USER: str = "user"
    ASSISTANT: str = "assistant"
    TOOL: str = "tool"

    ALL: tuple[str, ...] = (SYSTEM, USER, ASSISTANT, TOOL)


@dataclass(frozen=True, slots=True)
class Message:
    """A single message in a conversation.

    Unlike the legacy CScode Message which had a single 'content' string,
    this version uses a list of Part objects for structured multi-modal content.

    The 'id' field enables idempotent retry and session recovery.
    """

    role: str  # One of MessageRole.*
    parts: tuple[Part, ...]  # Immutable list of content parts

    id: MessageID | None = None
    """Optional message identifier for idempotency and session tracking."""

    assistant_message_id: AssistantMessageID | None = None
    """For TOOL-role messages: the assistant message that produced the tool call."""

    @property
    def content(self) -> str:
        """Concatenated text content for backward compatibility.

        Returns the text of all SystemPart, TextPart, and ReasoningPart in order.
        MediaPart, ToolCallPart, ToolResultPart are excluded.
        """
        texts: list[str] = []
        for part in self.parts:
            match part:
                case SystemPart(text=t) | TextPart(text=t) | ReasoningPart(text=t):
                    texts.append(t)
                case _:
                    pass
        return "".join(texts)

    def to_dict(self) -> dict[str, object]:
        """Serialize to the legacy dict format for provider compatibility.

        Returns a dict with keys: role, content, tool_calls (optional).
        This is the format expected by the existing provider implementations.
        """
        parts: list[dict[str, object]] = []
        tool_calls: list[dict[str, object]] = []

        for part in self.parts:
            match part:
                case SystemPart(text=t) | TextPart(text=t):
                    parts.append({"type": "text", "text": t})
                case MediaPart(media_type=m, data=d):
                    parts.append({"type": "media", "media_type": m, "data": d})
                case ToolCallPart(tool_call_id=i, name=n, args=a):
                    tool_calls.append({"id": i, "type": "function", "function": {"name": n, "arguments": a}})
                case ToolResultPart(tool_call_id=i, name=n, result=r, is_error=e) as trp:
                    entry: dict[str, object] = {
                        "type": "tool-result",
                        "tool_call_id": i,
                        "name": n,
                        "result": r,
                        "is_error": e,
                    }
                    # G-3: 条件序列化新字段——默认形状与改造前一致
                    if trp.provider_executed:
                        entry["provider_executed"] = True
                    if trp.cache is not None:
                        entry["cache"] = {"type": trp.cache.type, "ttl_seconds": trp.cache.ttl_seconds}
                    if trp.metadata:
                        entry["metadata"] = dict(trp.metadata)
                    parts.append(entry)
                case ReasoningPart(text=t, signature=s):
                    reasoning_entry: dict[str, object] = {"type": "reasoning", "text": t}
                    if s is not None:
                        reasoning_entry["signature"] = s
                    parts.append(reasoning_entry)

        result: dict[str, object] = {"role": self.role, "content": ""}
        if parts:
            result["content"] = parts
        if tool_calls:
            result["tool_calls"] = tool_calls
        return result

    @classmethod
    def from_text(cls, role: str, text: str) -> Message:
        """Convenience constructor for text-only messages."""
        return cls(role=role, parts=(TextPart(text=text),))

    @classmethod
    def from_tool_result(
        cls,
        tool_call_id: ToolCallID,
        name: str,
        result: str,
        is_error: bool = False,
        assistant_message_id: AssistantMessageID | None = None,
    ) -> Message:
        """Convenience constructor for tool result messages."""
        return cls(
            role=MessageRole.TOOL,
            parts=(ToolResultPart(tool_call_id=tool_call_id, name=name, result=result, is_error=is_error),),
            assistant_message_id=assistant_message_id,
        )

    @classmethod
    def system(cls, text: str) -> Message:
        """Convenience constructor for system messages."""
        return cls(role=MessageRole.SYSTEM, parts=(SystemPart(text=text),))

    @classmethod
    def user(cls, text: str) -> Message:
        """Convenience constructor for user messages."""
        return cls(role=MessageRole.USER, parts=(TextPart(text=text),))

    @classmethod
    def assistant(cls, text: str = "") -> Message:
        """Convenience constructor for assistant messages."""
        return cls(role=MessageRole.ASSISTANT, parts=(TextPart(text=text),) if text else ())

    # ─── Protocol: Sequence for iteration ───────────────────────

    def __iter__(self) -> Iterator[Part]:
        return iter(self.parts)

    def __len__(self) -> int:
        return len(self.parts)
