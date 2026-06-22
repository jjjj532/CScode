from __future__ import annotations

import re
from typing import Any

from cscode.core.events import EventBus
from cscode.core.permissions import PermissionService
from cscode.providers.base import LLMProvider
from cscode.tools.base import ToolRegistry
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class SubAgentOrchestrator:
    # Matches @ToolName key=value key=value
    # Values can be quoted ("value with spaces") or unquoted (simple)
    MENTION_PATTERN = re.compile(r'@(\w+)((?:\s+\w+=(?:"[^"]*"|[^\s"]+))*)')

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
        if "@" not in user_input:
            return user_input

        result = user_input
        for match in self.MENTION_PATTERN.finditer(user_input):
            tool_name = match.group(1)
            raw_args = match.group(2).strip()

            tool = self._registry.get(tool_name)
            if tool is None:
                logger.info("Unknown @mention: %s (not a registered tool)", tool_name)
                continue

            args = self._parse_args(raw_args)
            logger.info("Dispatching sub-agent for @%s with args=%s", tool_name, args)

            try:
                tool_result = await tool.execute(args)
                if tool_result.success:
                    replacement = tool_result.data
                else:
                    replacement = f"[Error executing @{tool_name}: {tool_result.error}]"
            except Exception as e:
                replacement = f"[Error executing @{tool_name}: {e}]"

            result = result.replace(match.group(0), replacement, 1)

        return result

    @staticmethod
    def _parse_args(raw: str) -> dict[str, Any]:
        if not raw:
            return {}
        args: dict[str, Any] = {}
        for pair in re.findall(r'(\w+)=(?:"([^"]*)"|(\S+))', raw):
            key = pair[0]
            value = pair[1] if pair[1] else pair[2]
            # Try to parse as number
            if value.isdigit():
                args[key] = int(value)
            elif value.replace(".", "", 1).isdigit() and value.count(".") == 1:
                args[key] = float(value)
            else:
                args[key] = value
        return args
