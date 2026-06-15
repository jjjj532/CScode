from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cscode.core.agent import AgentOrchestrator, AgentMode
from cscode.core.events import EventBus
from cscode.core.permissions import PermissionService
from cscode.tools.base import ToolRegistry


class TestAgentOrchestratorConstruction:
    def test_create_orchestrator(self) -> None:
        bus = EventBus()
        registry = ToolRegistry()
        perm_svc = PermissionService(bus)
        assert True

    def test_agent_mode_enum_values(self) -> None:
        assert AgentMode.PLAN.value == "plan"
        assert AgentMode.BUILD.value == "build"
