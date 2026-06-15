from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from cscode.utils.logging import get_logger

logger = get_logger(__name__)

Handler = Callable[["Event"], Any]


@dataclass
class Event:
    type: str = ""


@dataclass
class ToolExecuteEvent(Event):
    type: str = "tool.execute.before"
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutedEvent(Event):
    type: str = "tool.execute.after"
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    result: str = ""


@dataclass
class SessionCreatedEvent(Event):
    type: str = "session.created"
    session_id: str = ""


@dataclass
class SessionDeletedEvent(Event):
    type: str = "session.deleted"
    session_id: str = ""


@dataclass
class MessageCreatedEvent(Event):
    type: str = "message.created"
    session_id: str = ""
    role: str = ""
    content: str = ""


@dataclass
class PermissionAskedEvent(Event):
    type: str = "permission.asked"
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionRepliedEvent(Event):
    type: str = "permission.replied"
    tool_name: str = ""
    allowed: bool = False


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Handler]] = {}

    def subscribe(self, event_type: str, handler: Handler) -> None:
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        if event_type in self._listeners:
            self._listeners[event_type] = [h for h in self._listeners[event_type] if h is not handler]
            if not self._listeners[event_type]:
                del self._listeners[event_type]

    async def emit(self, event_type: str, event: Event) -> None:
        if event_type not in self._listeners:
            return
        for handler in list(self._listeners[event_type]):
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception:
                logger.exception("EventBus handler failed for %s", event_type)

    def clear(self) -> None:
        self._listeners.clear()

    def listener_count(self, event_type: str) -> int:
        return len(self._listeners.get(event_type, []))
