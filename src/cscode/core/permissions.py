from __future__ import annotations

import enum
from typing import Any

from cscode.core.events import EventBus, PermissionAskedEvent


class PermissionPolicy(str, enum.Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionResult(str, enum.Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    ASK = "ask"


class PermissionService:
    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._policies: dict[str, PermissionPolicy] = {}
        self._resolve_table: dict[str, bool | None] = {}

    def set_policy(self, tool_name: str, policy: PermissionPolicy) -> None:
        self._policies[tool_name] = policy

    async def check(self, tool_name: str, args: dict[str, Any]) -> PermissionResult:
        if tool_name in self._policies:
            policy = self._policies[tool_name]
            if policy == PermissionPolicy.ALLOW:
                return PermissionResult.ALLOWED
            if policy == PermissionPolicy.DENY:
                return PermissionResult.DENIED

        if tool_name in self._resolve_table:
            val = self._resolve_table.pop(tool_name)
            if val is True:
                return PermissionResult.ALLOWED
            if val is False:
                return PermissionResult.DENIED

        event = PermissionAskedEvent(tool_name=tool_name, args=args)
        await self._bus.emit("permission.asked", event)

        if tool_name in self._resolve_table:
            val = self._resolve_table.pop(tool_name)
            if val is True:
                return PermissionResult.ALLOWED
            if val is False:
                return PermissionResult.DENIED

        return PermissionResult.ASK

    def resolve(self, tool_name: str, allowed: bool, remember: bool = False) -> None:
        if remember:
            self._policies[tool_name] = PermissionPolicy.ALLOW if allowed else PermissionPolicy.DENY
        else:
            self._resolve_table[tool_name] = allowed

    def clear(self) -> None:
        self._policies.clear()
        self._resolve_table.clear()
