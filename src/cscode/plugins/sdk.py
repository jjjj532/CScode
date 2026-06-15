from __future__ import annotations

from typing import Any

from cscode.plugins.hooks import PluginHookManager
from cscode.plugins.manifest import PluginManifest
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class PluginSDK:
    def __init__(self, name: str, version: str = "0.0.0", description: str = "") -> None:
        self.name = name
        self.version = version
        self.description = description
        self.tools: dict[str, type] = {}
        self._hook_handlers: list[tuple[str, Any]] = []

    def tool(self, name: str | None = None, description: str = "") -> Any:
        def decorator(cls: type) -> type:
            tool_name = name or cls.__name__.lower()
            self.tools[tool_name] = cls
            logger.debug("SDK: registered tool '%s' from plugin '%s'", tool_name, self.name)
            return cls
        return decorator

    def on(self, event_type: str) -> Any:
        def decorator(func: Any) -> Any:
            self._hook_handlers.append((event_type, func))
            logger.debug("SDK: registered hook '%s' from plugin '%s'", event_type, self.name)
            return func
        return decorator

    def register_hooks(self, hook_manager: PluginHookManager) -> None:
        for event_type, handler in self._hook_handlers:
            hook_manager.register(self.name, event_type, handler)

    def to_manifest(self) -> PluginManifest:
        return PluginManifest(
            name=self.name,
            version=self.version,
            description=self.description,
            hooks=[h[0] for h in self._hook_handlers],
            tools=list(self.tools.keys()),
        )
