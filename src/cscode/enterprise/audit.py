from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AuditEvent:
    action: str
    actor: str
    target: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class AuditLogger:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def log(self, event: AuditEvent) -> None:
        self._events.append(event)
        logger.info("AUDIT: %s by %s on %s", event.action, event.actor, event.target)

    def get_events(self) -> list[AuditEvent]:
        return list(self._events)

    def filter_by_action(self, action: str) -> list[AuditEvent]:
        return [e for e in self._events if e.action == action]

    def clear(self) -> None:
        self._events.clear()
