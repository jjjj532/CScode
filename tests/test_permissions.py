from __future__ import annotations

import pytest

from cscode.core.events import EventBus
from cscode.core.permissions import PermissionPolicy, PermissionResult, PermissionService


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def service(bus: EventBus) -> PermissionService:
    return PermissionService(bus)


class TestAllowList:
    async def test_allowed_tool_in_allow_list(self, service: PermissionService) -> None:
        service.set_policy("Read", PermissionPolicy.ALLOW)
        result = await service.check("Read", {})
        assert result == PermissionResult.ALLOWED

    async def test_denied_tool_in_deny_list(self, service: PermissionService) -> None:
        service.set_policy("Write", PermissionPolicy.DENY)
        result = await service.check("Write", {})
        assert result == PermissionResult.DENIED

    async def test_unknown_tool_defaults_to_ask(self, service: PermissionService) -> None:
        result = await service.check("AnyTool", {})
        assert result == PermissionResult.ASK

    async def test_multiple_tools(self, service: PermissionService) -> None:
        service.set_policy("Read", PermissionPolicy.ALLOW)
        service.set_policy("Write", PermissionPolicy.DENY)
        assert await service.check("Read", {}) == PermissionResult.ALLOWED
        assert await service.check("Write", {}) == PermissionResult.DENIED
        assert await service.check("Edit", {}) == PermissionResult.ASK


class TestPermissions:
    async def test_allow_permission(self, service: PermissionService) -> None:
        service.set_policy("Read", PermissionPolicy.ALLOW)
        result = await service.check("Read", {})
        assert result == PermissionResult.ALLOWED

    async def test_permission_fallback(self, service: PermissionService) -> None:
        assert await service.check("Unknown", {}) == PermissionResult.ASK
        assert await service.check("Unknown_2", {}) == PermissionResult.ASK

    async def test_permission_after_clear(self, service: PermissionService) -> None:
        service.set_policy("Read", PermissionPolicy.ALLOW)
        assert await service.check("Read", {}) == PermissionResult.ALLOWED
        service.clear()
        assert await service.check("Read", {}) == PermissionResult.ASK


class TestEventEmission:
    async def test_check_emits_permission_asked(self, bus: EventBus, service: PermissionService) -> None:
        received: list = []

        async def handler(event):
            received.append(event)

        bus.subscribe("permission.asked", handler)
        await service.check("Read", {"path": "/tmp"})

        assert len(received) == 1
        assert received[0].type == "permission.asked"
        assert received[0].tool_name == "Read"

    async def test_dynamic_resolve_via_event(self, bus: EventBus, service: PermissionService) -> None:
        async def auto_allow(event):
            service.resolve("Read", allowed=True)

        bus.subscribe("permission.asked", auto_allow)
        result = await service.check("Read", {})
        assert result == PermissionResult.ALLOWED


class TestResolve:
    async def test_resolve_allowed(self, service: PermissionService) -> None:
        service.set_policy("Read", PermissionPolicy.ALLOW)
        result = await service.check("Read", {})
        assert result == PermissionResult.ALLOWED

    async def test_resolve_after_resolve(self, service: PermissionService) -> None:
        service.resolve("Read", allowed=True, remember=True)
        assert await service.check("Read", {}) == PermissionResult.ALLOWED

    async def test_resolve_not_remembered(self, service: PermissionService) -> None:
        service.resolve("Read", allowed=True, remember=False)
        assert await service.check("Read", {}) == PermissionResult.ALLOWED
        assert await service.check("Read", {}) == PermissionResult.ASK
