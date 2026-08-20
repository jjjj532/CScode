"""Context compression — token-aware truncation and summarization.

Aligns with OpenCode `packages/core/src/session/compaction.ts`:

- Constants: DEFAULT_BUFFER_TOKENS / DEFAULT_KEEP_TOKENS / TOOL_OUTPUT_MAX_CHARS
- Serialization rules: `[User]: ...`, `[Assistant]: ...`, `[Tool result]: ...`
- select algorithm: accumulate from the tail, cut head (compress) vs recent (keep)
- SUMMARIZE strategy: head serialized → LLM summarizer → summary message
  (falls back to TRUNCATE when no summarizer is provided or it errors)
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Callable

from cscode.core.token_estimate import estimate_tokens
from cscode.schema.messages import (
    MediaPart,
    Message,
    MessageRole,
    ReasoningPart,
    SystemPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

# ─── Constants (aligned with OpenCode compaction.ts) ──────────────

DEFAULT_BUFFER_TOKENS: int = 20_000
"""Token threshold above which compression triggers."""

DEFAULT_KEEP_TOKENS: int = 8_000
"""Token budget kept in the 'recent' tail after compression."""

TOOL_OUTPUT_MAX_CHARS: int = 2_000
"""Tool result output is truncated beyond this many chars in serialization."""

#: Marker used in the compression note inserted after compressing the head.
_COMPRESSED_MARKER = "[Compressed]"


class CompressionStrategy(str, Enum):
    TRUNCATE = "truncate"
    SUMMARIZE = "summarize"


#: Summarizer callback: takes serialized head, returns summary text.
Summarizer = Callable[[str], str]


def _message_token_count(m: Message) -> int:
    """Estimate tokens for a single message (all parts)."""
    return estimate_tokens(m.content)


def serialize_messages(messages: list[Message]) -> str:
    """Serialize messages to OpenCode compaction format, joined by newlines.

    Rules:
      - user      → ``[User]: text``
      - assistant → ``[Assistant]: text`` (text / reasoning / tool call parts)
      - tool      → ``[Tool result]: result`` / ``[Tool error]: message``
      - system    → ``[System update]: text``
      - media     → ``[Attached mime: name]``
      - tool call → ``[Assistant tool call]: name(args_json)``
      - tool result output beyond TOOL_OUTPUT_MAX_CHARS → appended `` (truncated)``
    """
    lines: list[str] = []
    for m in messages:
        lines.extend(_serialize_message(m))
    return "\n".join(lines)


def _serialize_message(m: Message) -> list[str]:
    """Serialize one message into one or more lines (one per part)."""
    role = m.role
    if role == MessageRole.USER:
        return [f"[User]: {_text_of(m)}"]
    if role == MessageRole.SYSTEM:
        return [f"[System update]: {_text_of(m)}"]
    if role == MessageRole.ASSISTANT:
        return _serialize_assistant(m)
    if role == MessageRole.TOOL:
        return _serialize_tool(m)
    # Unknown role: fall back to raw content
    return [f"[Message]: {_text_of(m)}"]


def _serialize_assistant(m: Message) -> list[str]:
    lines: list[str] = []
    for part in m.parts:
        match part:
            case TextPart(text=t):
                lines.append(f"[Assistant]: {t}")
            case ReasoningPart(text=t):
                lines.append(f"[Assistant reasoning]: {t}")
            case ToolCallPart(tool_call_id=_, name=n, args=a):
                args_json = json.dumps(a, ensure_ascii=False, sort_keys=True)
                lines.append(f"[Assistant tool call]: {n}({args_json})")
            case SystemPart(text=t):
                lines.append(f"[System update]: {t}")
            case MediaPart(media_type=mt, data=_):
                lines.append(f"[Attached {mt}: attached-media]")
            case ToolResultPart(tool_call_id=_, name=_, result=r, is_error=e):
                # Malformed message: tool result nested in assistant role
                prefix = "[Tool error]" if e else "[Tool result]"
                lines.append(f"{prefix}: {_truncate_tool_result(r)}")
    if not lines:
        return [f"[Assistant]: {_text_of(m)}"]
    return lines


def _serialize_tool(m: Message) -> list[str]:
    lines: list[str] = []
    for part in m.parts:
        match part:
            case ToolResultPart(tool_call_id=_, name=_, result=r, is_error=e):
                prefix = "[Tool error]" if e else "[Tool result]"
                lines.append(f"{prefix}: {_truncate_tool_result(r)}")
            case TextPart(text=t):
                lines.append(f"[Tool result]: {_truncate_tool_result(t)}")
            case _:
                lines.append(f"[Tool result]: {_truncate_tool_result(_text_of(m))}")
    if not lines:
        lines.append(f"[Tool result]: {_truncate_tool_result(_text_of(m))}")
    return lines


def _truncate_tool_result(result: str) -> str:
    """Truncate tool result output beyond TOOL_OUTPUT_MAX_CHARS."""
    if len(result) <= TOOL_OUTPUT_MAX_CHARS:
        return result
    return f"{result[:TOOL_OUTPUT_MAX_CHARS]}... (truncated)"


def _text_of(m: Message) -> str:
    """Text content of a message (concatenated text parts)."""
    return m.content


class ContextCompressor:
    """Token-aware conversation compressor.

    Args:
        buffer_tokens: token threshold above which ``needs_compression`` is True.
        keep_tokens: token budget for the retained 'recent' tail.
        strategy: TRUNCATE (drop head, keep note) or SUMMARIZE (LLM summary).
        summarizer: callable taking the serialized head and returning summary text.
            Only used with SUMMARIZE. When None (or when it raises), SUMMARIZE
            falls back to TRUNCATE.
        threshold: deprecated alias for ``buffer_tokens`` (token semantics).
        keep_recent: deprecated alias for ``keep_tokens`` (token semantics).
    """

    def __init__(
        self,
        buffer_tokens: int | None = None,
        keep_tokens: int | None = None,
        strategy: CompressionStrategy = CompressionStrategy.TRUNCATE,
        summarizer: Summarizer | None = None,
        threshold: int | None = None,
        keep_recent: int | None = None,
    ) -> None:
        if threshold is not None and buffer_tokens is not None and threshold != buffer_tokens:
            raise ValueError("threshold and buffer_tokens are aliases; pass only one")
        if keep_recent is not None and keep_tokens is not None and keep_recent != keep_tokens:
            raise ValueError("keep_recent and keep_tokens are aliases; pass only one")
        self.buffer_tokens = buffer_tokens if buffer_tokens is not None else (
            threshold if threshold is not None else DEFAULT_BUFFER_TOKENS
        )
        self.keep_tokens = keep_tokens if keep_tokens is not None else (
            keep_recent if keep_recent is not None else DEFAULT_KEEP_TOKENS
        )
        self.strategy = strategy
        self.summarizer = summarizer

    # ─── Backward-compatible aliases ──────────────────────────────

    @property
    def threshold(self) -> int:
        """Alias for ``buffer_tokens`` (kept for existing callers)."""
        return self.buffer_tokens

    @property
    def keep_recent(self) -> int:
        """Alias for ``keep_tokens`` (kept for existing callers)."""
        return self.keep_tokens

    # ─── Public API ────────────────────────────────────────────────

    def needs_compression(self, messages: list[Message]) -> bool:
        if not messages:
            return False
        return self._total_tokens(messages) > self.buffer_tokens

    def compress(self, messages: list[Message]) -> list[Message]:
        if not self.needs_compression(messages):
            return messages

        total = self._total_tokens(messages)
        logger.info(
            "Compressing %d messages (%d tokens, buffer=%d)",
            len(messages),
            total,
            self.buffer_tokens,
        )

        match self.strategy:
            case CompressionStrategy.TRUNCATE:
                return self._truncate(messages)
            case CompressionStrategy.SUMMARIZE:
                return self._summarize(messages)
    # ─── Internals ─────────────────────────────────────────────────

    def _total_tokens(self, messages: list[Message]) -> int:
        return sum(_message_token_count(m) for m in messages)

    def _split_head_recent(self, messages: list[Message]) -> tuple[list[Message], list[Message]]:
        """Cut messages into (head, recent) accumulating tokens from the tail.

        The recent segment is the maximal trailing slice whose total token
        count does not exceed ``keep_tokens``. The head is everything before it.
        """
        # Preserve the first system message in the head? No — system prompt is
        # kept separately by callers; here we just cut a token budget.
        recent: list[Message] = []
        acc = 0
        for m in reversed(messages):
            if acc + _message_token_count(m) > self.keep_tokens and recent:
                break
            recent.append(m)
            acc += _message_token_count(m)
        recent.reverse()
        head = messages[: len(messages) - len(recent)] if recent else messages[:-1]
        if not recent:
            # Keep at least the last message when even a single message exceeds budget
            recent = messages[-1:]
            head = messages[:-1]
        return head, recent

    def _truncate(self, messages: list[Message]) -> list[Message]:
        head, recent = self._split_head_recent(messages)
        if not head:
            logger.debug("No compressible head, returning original %d messages", len(messages))
            return messages

        result: list[Message] = []
        system_msgs = [m for m in messages if m.role == MessageRole.SYSTEM]
        if system_msgs:
            result.append(system_msgs[0])

        result.append(
            Message.system(
                f"{_COMPRESSED_MARKER} Earlier conversation history was compressed. "
                f"Keeping the last {len(recent)} messages ({self.keep_tokens} token budget).",
            )
        )
        result.extend(recent)

        logger.info(
            "Truncated %d messages to %d (%d tokens)",
            len(messages),
            len(result),
            self._total_tokens(result),
        )
        return result

    def _summarize(self, messages: list[Message]) -> list[Message]:
        if self.summarizer is None:
            logger.warning("SUMMARIZE strategy without summarizer, falling back to TRUNCATE")
            return self._truncate(messages)

        head, recent = self._split_head_recent(messages)
        if not head:
            logger.debug("No compressible head, returning original %d messages", len(messages))
            return messages

        try:
            serialized_head = serialize_messages(head)
            summary = self.summarizer(serialized_head)
        except Exception:
            logger.exception("Summarizer failed, falling back to TRUNCATE")
            return self._truncate(messages)

        result: list[Message] = []
        system_msgs = [m for m in messages if m.role == MessageRole.SYSTEM]
        if system_msgs:
            result.append(system_msgs[0])

        result.append(
            Message.system(
                f"{_COMPRESSED_MARKER} Earlier conversation history was summarized:\n{summary}",
            )
        )
        result.extend(recent)

        logger.info(
            "Summarized %d messages into %d messages (%d tokens)",
            len(messages),
            len(result),
            self._total_tokens(result),
        )
        return result
