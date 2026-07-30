from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from cscode.plugins.context_source import PluginContextSource
from cscode.plugins.hooks import PluginHookManager
from cscode.plugins.lifecycle import PluginLifecycle
from cscode.plugins.manifest import PluginManifest
from cscode.tools.base import BaseTool
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class PluginSDK:
    def __init__(self, name: str, version: str = "0.0.0", description: str = "") -> None:
        self.name = name
        self.version = version
        self.description = description
        self.tools: dict[str, type[BaseTool]] = {}
        self._context_sources: list[PluginContextSource] = []
        self._lifecycle = PluginLifecycle()
        self._hook_handlers: list[tuple[str, Any]] = []

    def tool(self, name: str | None = None, description: str = "") -> Any:
        def decorator(cls: type[BaseTool]) -> type[BaseTool]:
            tool_name = name or cls.__name__.lower()
            self.tools[tool_name] = cls
            logger.debug("SDK: registered tool '%s' from plugin '%s'", tool_name, self.name)
            return cls
        return decorator

    def context_source(self, key: str, baseline: Callable[[str], str] | None = None, update: Callable[[str, str], str] | None = None) -> Callable:
        """Register a system context source.

        Can be used as a decorator on an async function that loads the context value.
        """
        def decorator(func: Callable[[], Awaitable[str]]) -> Callable[[], Awaitable[str]]:
            source = PluginContextSource(
                key=key,
                load=func,
                baseline=baseline or (lambda v: f"{key}: {v}"),
                update=update or (lambda old, new: f"{key}: {old} -> {new}"),
            )
            self._context_sources.append(source)
            logger.debug("SDK: registered context source '%s' from plugin '%s'", key, self.name)
            return func
        return decorator

    def on(self, event_type: str) -> Any:
        def decorator(func: Any) -> Any:
            self._hook_handlers.append((event_type, func))
            logger.debug("SDK: registered hook '%s' from plugin '%s'", event_type, self.name)
            return func
        return decorator

    def on_activate(self, func: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        self._lifecycle.on_activate = func
        self._lifecycle.register("activate", func)
        return func

    def on_deactivate(self, func: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        self._lifecycle.on_deactivate = func
        self._lifecycle.register("deactivate", func)
        return func

    def on_session_start(self, func: Callable[[str], Awaitable[None]]) -> Callable[[str], Awaitable[None]]:
        self._lifecycle.on_session_start = func
        self._lifecycle.register("session_start", func)
        return func

    def on_session_end(self, func: Callable[[str], Awaitable[None]]) -> Callable[[str], Awaitable[None]]:
        self._lifecycle.on_session_end = func
        self._lifecycle.register("session_end", func)
        return func

    def get_tool_instances(self) -> list[BaseTool]:
        instances: list[BaseTool] = []
        for tool_cls in self.tools.values():
            try:
                instances.append(tool_cls())
            except Exception:
                logger.exception("SDK: failed to instantiate tool '%s'", tool_cls.__name__)
        return instances

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
