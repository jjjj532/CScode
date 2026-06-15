from __future__ import annotations

import collections.abc
import enum
from typing import Any

from cscode.core.engine import Agent
from cscode.core.events import EventBus
from cscode.core.modes.build import create_build_agent
from cscode.core.modes.plan import create_plan_agent
from cscode.core.permissions import PermissionService
from cscode.core.sub_agent import SubAgentOrchestrator
from cscode.providers.base import LLMProvider
from cscode.tools.base import ToolRegistry
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class AgentMode(str, enum.Enum):
    PLAN = "plan"
    BUILD = "build"


class AgentOrchestrator:
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
        self._plan_agent = create_plan_agent(provider, registry)
        self._build_agent = create_build_agent(provider, registry)
        self._sub_agent_orchestrator = SubAgentOrchestrator(
            event_bus, provider, registry, permission_service
        )

    def get_agent(self, mode: AgentMode) -> Agent:
        if mode == AgentMode.PLAN:
            return self._plan_agent
        return self._build_agent

    async def run(
        self,
        mode: AgentMode,
        user_input: str,
        attached_filenames: list[str] | None = None,
        on_event: collections.abc.Callable[[dict[str, Any]], collections.abc.Awaitable[None]] | None = None,
    ) -> str:
        processed_input = await self._sub_agent_orchestrator.process_mentions(user_input)
        await self._event_bus.emit("session.command", type("Event", (), {"type": "session.command"})())
        agent = self.get_agent(mode)
        return await agent.run_with_permissions(
            processed_input,
            permission_service=self._permission_service,
            attached_filenames=attached_filenames,
            on_event=on_event,
        )
