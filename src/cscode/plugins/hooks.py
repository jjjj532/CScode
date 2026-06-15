from __future__ import annotations

from cscode.core.events import EventBus, Handler
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class PluginHookManager:
    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._plugin_hooks: dict[str, list[tuple[str, Handler]]] = {}

    def register(self, plugin_name: str, event_type: str, handler: Handler) -> None:
        if plugin_name not in self._plugin_hooks:
            self._plugin_hooks[plugin_name] = []
        self._plugin_hooks[plugin_name].append((event_type, handler))
        self._bus.subscribe(event_type, handler)
        logger.debug("Plugin '%s' registered hook for '%s'", plugin_name, event_type)

    def unregister_all(self, plugin_name: str) -> None:
        hooks = self._plugin_hooks.pop(plugin_name, [])
        for event_type, handler in hooks:
            self._bus.unsubscribe(event_type, handler)
        logger.info("Unregistered all hooks for plugin '%s'", plugin_name)
