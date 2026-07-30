"""PluginLifecycle — plugin lifecycle hooks.

Plugins can hook into key lifecycle events:
- on_activate: plugin is being activated
- on_deactivate: plugin is being deactivated
- on_session_start: a new session has started
- on_session_end: a session has ended
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass
class PluginLifecycle:
    """Lifecycle hook container for a plugin.

    Each field is an optional async callback.
    """

    on_activate: Callable[[], Awaitable[None]] | None = None
    """Called when the plugin is activated."""

    on_deactivate: Callable[[], Awaitable[None]] | None = None
    """Called when the plugin is deactivated."""

    on_session_start: Callable[[str], Awaitable[None]] | None = None
    """Called when a new session starts. Receives session_id."""

    on_session_end: Callable[[str], Awaitable[None]] | None = None
    """Called when a session ends. Receives session_id."""

    _handlers: list[tuple[str, Callable[..., Awaitable[None]]]] = field(default_factory=list, repr=False)

    def register(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        """Register a lifecycle handler for a named event."""
        self._handlers.append((event, handler))

    def get_handlers(self) -> list[tuple[str, Callable[..., Awaitable[None]]]]:
        """Return all registered handlers."""
        return list(self._handlers)
