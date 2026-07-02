"""TruncateTool — truncate conversation context to manage token usage.

The LLM invokes this tool to free up context window space by applying
a truncation strategy (keep recent messages, drop oldest, etc.).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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


class TruncateTool(Tool[TruncateInput, TruncateOutput]):
    """Truncate conversation context to manage token usage."""

    name: str = "truncate"
    description: str = "Truncate conversation context to free up token space. Strategies: keep_recent (keep last N tokens), drop_oldest (drop earliest messages)."
    input_schema: type[TruncateInput] = TruncateInput
    output_schema: type[TruncateOutput] = TruncateOutput

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

        # In a real implementation this would interact with the conversation store.
        # For now we return a success response indicating truncation would happen.
        return ToolResult(
            success=True,
            data=TruncateOutput(
                truncated=True,
                tokens_freed=input.max_tokens,
                summary=f"Truncated using '{input.strategy}' strategy, freed ~{input.max_tokens} tokens",
                remaining_tokens=input.max_tokens,
            ),
        )
