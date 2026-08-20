"""TruncateTool — truncate conversation context to manage token usage.

The LLM invokes this tool to free up context window space by applying
a truncation strategy (keep recent messages, drop oldest, etc.).

When constructed without dependencies (``TruncateTool()``), the tool keeps
the legacy stub behaviour (returns success without touching storage) for
backward compatibility. When a :class:`CompactorLike` and
:class:`EventStoreLike` are injected, the tool performs a real compaction:
it reads the session events, estimates the token footprint, calls the
compactor (which writes a ``compaction`` event + ``context_epochs`` row),
and reports the real number of tokens freed.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from cscode.core.token_estimate import estimate_tokens
from cscode.schema.events import PersistenceEvent
from cscode.tools2.base import Tool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

Strategy = Literal["keep_recent", "drop_oldest"]


class TruncateInput(BaseModel):
    strategy: Strategy = Field(..., description="Truncation strategy: keep_recent or drop_oldest")
    max_tokens: int = Field(default=0, description="Maximum tokens to keep (must be > 0)")
    session_id: str | None = Field(None, description="Optional session ID to truncate")


class TruncateOutput(BaseModel):
    truncated: bool
    tokens_freed: int
    summary: str = ""
    remaining_tokens: int = 0


class CompactorLike(Protocol):
    """Minimal compactor interface (implemented by server.Compactor)."""

    async def compact(self, session_id: str, system_prompt: str | None = None) -> int:
        ...


class EventStoreLike(Protocol):
    """Minimal event store interface (implemented by storage.EventStore)."""

    async def read(
        self, aggregate_id: str, after_seq: int = 0, limit: int = 1000
    ) -> list[PersistenceEvent]:
        ...


class TruncateTool(Tool[TruncateInput, TruncateOutput]):
    """Truncate conversation context to manage token usage.

    With injected ``compactor``/``event_store`` this performs a real
    compaction against the session store. Without them it keeps the legacy
    stub behaviour (success without side effects).
    """

    name: str = "truncate"
    description: str = "Truncate conversation context to free up token space. Strategies: keep_recent (keep last N tokens), drop_oldest (drop earliest messages)."
    input_schema: type[TruncateInput] = TruncateInput
    output_schema: type[TruncateOutput] = TruncateOutput

    def __init__(
        self,
        compactor: CompactorLike | None = None,
        event_store: EventStoreLike | None = None,
    ) -> None:
        super().__init__()
        self._compactor = compactor
        self._event_store = event_store

    async def execute(self, input: TruncateInput) -> ToolResult[TruncateOutput]:
        if input.strategy not in ("keep_recent", "drop_oldest"):
            return ToolResult(
                success=False,
                error=f"Unknown strategy: {input.strategy}. Use 'keep_recent' or 'drop_oldest'.",
            )

        if input.max_tokens <= 0:
            return ToolResult(
                success=False,
                error="max_tokens must be > 0",
            )

        # Legacy stub path (no dependencies injected).
        if self._compactor is None or self._event_store is None:
            return ToolResult(
                success=True,
                data=TruncateOutput(
                    truncated=True,
                    tokens_freed=input.max_tokens,
                    summary=f"Truncated using '{input.strategy}' strategy, freed ~{input.max_tokens} tokens",
                    remaining_tokens=input.max_tokens,
                ),
            )

        # Real path: compact against the session store.
        if not input.session_id:
            return ToolResult(
                success=False,
                error="session_id is required when truncating a real session",
            )

        events = await self._event_store.read(input.session_id)
        if not events:
            return ToolResult(
                success=False,
                error=f"Session '{input.session_id}' is empty, nothing to truncate",
            )

        total_before = self._estimate_tokens(events)
        baseline_seq = await self._compactor.compact(input.session_id)
        remaining = self._estimate_tokens_after(events, baseline_seq)
        freed = max(0, total_before - remaining)

        logger.info(
            "TruncateTool: session=%s strategy=%s total_before=%d baseline_seq=%d remaining=%d freed=%d",
            input.session_id,
            input.strategy,
            total_before,
            baseline_seq,
            remaining,
            freed,
        )

        return ToolResult(
            success=True,
            data=TruncateOutput(
                truncated=True,
                tokens_freed=freed,
                summary=(
                    f"Truncated session '{input.session_id}' using '{input.strategy}' strategy, "
                    f"freed ~{freed} tokens"
                ),
                remaining_tokens=remaining,
            ),
        )

    @staticmethod
    def _estimate_tokens(events: list[PersistenceEvent]) -> int:
        """Estimate total tokens across all event payloads (content when available)."""
        total = 0
        for e in events:
            data = getattr(e, "data", None) or {}
            content = data.get("content") if isinstance(data, dict) else None
            if isinstance(content, str) and content:
                total += estimate_tokens(content)
        return total

    @staticmethod
    def _estimate_tokens_after(events: list[PersistenceEvent], baseline_seq: int) -> int:
        """Estimate tokens of events not covered by the compaction snapshot."""
        remaining_events = [e for e in events if e.seq > baseline_seq]
        return TruncateTool._estimate_tokens(remaining_events)
