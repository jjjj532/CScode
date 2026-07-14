"""HookPoint enum and HookRegistry — type-safe plugin hook management."""

from __future__ import annotations

from enum import Enum

from cscode.core.events import EventBus, Handler


class HookPoint(str, Enum):
    """Well-known plugin hook points.

    Each value corresponds to an EventBus event type string.
    """

    SESSION_START = "session.start"
    TOOL_CALL = "tool.call"
    MESSAGE = "message"
    SESSION_END = "session.end"


class HookRegistry:
    """Type-safe hook registration backed by EventBus.

    Provides register/unregister for HookPoint values,
    delegating to an EventBus instance.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus

    def register(self, hook: HookPoint, handler: Handler) -> None:
        """Register a handler for a hook point."""
        self._bus.subscribe(hook.value, handler)

    def unregister(self, hook: HookPoint, handler: Handler) -> None:
        """Unregister a handler from a hook point."""
        self._bus.unsubscribe(hook.value, handler)
