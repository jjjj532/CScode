from __future__ import annotations

from enum import Enum

from cscode.core.messages import Message, MessageRole
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class CompressionStrategy(str, Enum):
    TRUNCATE = "truncate"
    SUMMARIZE = "summarize"


class ContextCompressor:
    def __init__(
        self,
        threshold: int = 100_000,
        keep_recent: int = 10,
        strategy: CompressionStrategy = CompressionStrategy.TRUNCATE,
    ) -> None:
        self.threshold = threshold
        self.keep_recent = keep_recent
        self.strategy = strategy

    def needs_compression(self, messages: list[Message]) -> bool:
        if not messages:
            return False
        return self._total_chars(messages) > self.threshold

    def compress(self, messages: list[Message]) -> list[Message]:
        if not self.needs_compression(messages):
            return messages

        total = self._total_chars(messages)
        logger.info(
            "Compressing %d messages (%d chars, threshold=%d)",
            len(messages),
            total,
            self.threshold,
        )

        match self.strategy:
            case CompressionStrategy.TRUNCATE:
                return self._truncate(messages)
            case CompressionStrategy.SUMMARIZE:
                return self._summarize(messages)

    def _truncate(self, messages: list[Message]) -> list[Message]:
        system_msgs = [m for m in messages if m.role == MessageRole.SYSTEM]
        recent = messages[-self.keep_recent :]

        result: list[Message] = []
        compression_note = Message(
            role=MessageRole.SYSTEM,
            content=f"[Compressed] Earlier conversation history was compressed. Keeping last {self.keep_recent} messages.",
        )

        if system_msgs:
            result.append(system_msgs[0])
        result.append(compression_note)
        result.extend(recent)

        new_total = self._total_chars(result)
        logger.info(
            "Truncated %d messages to %d (%d chars)",
            len(messages),
            len(result),
            new_total,
        )
        return result

    def _summarize(self, messages: list[Message]) -> list[Message]:
        logger.warning("SUMMARIZE strategy not yet implemented, falling back to TRUNCATE")
        return self._truncate(messages)

    def _total_chars(self, messages: list[Message]) -> int:
        return sum(len(m.content) for m in messages)
