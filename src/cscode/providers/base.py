from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from cscode.core.config import Config
from cscode.core.messages import Message
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LLMResult:
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, int] | None = None
    model: str = ""
    finish_reason: str = ""


class LLMProvider(ABC):
    def __init__(self, config: Config) -> None:
        self.config = config
        logger.debug("LLMProvider.__init__: config=%s", config)

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResult: ...

    @abstractmethod
    def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]: ...

    @abstractmethod
    def build_messages(self, messages: list[Message]) -> list[dict[str, Any]]: ...
