from __future__ import annotations

import re

from cscode.core.events import EventBus
from cscode.core.permissions import PermissionService
from cscode.providers.base import LLMProvider
from cscode.tools.base import ToolRegistry
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class SubAgentOrchestrator:
    MENTION_PATTERN = re.compile(r"@(\w+)")

    def __init__(
        self,
        event_bus: EventBus,
        provider: LLMProvider,
        registry: ToolRegistry,
        permission_service: PermissionService,
    ) -> None:
        self._event_bus = event_bus
        self._provider = provider
        self._registry = registry
        self._permission_service = permission_service

    async def process_mentions(self, user_input: str) -> str:
        mentions = self.MENTION_PATTERN.findall(user_input)
        if mentions:
            logger.info("Found @mentions in input: %s", mentions)
        return user_input
