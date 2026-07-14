"""PluginRegistry — central plugin registration store."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class PluginState(str, Enum):
    """Lifecycle states for a plugin."""

    UNKNOWN = "unknown"
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass
class PluginManifest:
    """Plugin metadata — enhanced from v1 for v2 lifecycle."""

    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    source: str = ""
    state: PluginState = PluginState.DISCOVERED
    hooks: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    installed_at: float = 0.0
    activated_at: float | None = None


class PluginRegistry:
    """In-memory registry of all plugins and their lifecycle state.

    Provides CRUD operations for PluginManifest entries and state tracking.
    Thread-safe for read operations; mutations are single-threaded.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}

    def register(self, manifest: PluginManifest) -> None:
        """Register a new plugin manifest.

        Raises ValueError if a plugin with the same id already exists.
        """
        if manifest.id in self._plugins:
            msg = f"Plugin '{manifest.id}' already registered"
            raise ValueError(msg)
        self._plugins[manifest.id] = manifest

    def unregister(self, plugin_id: str) -> None:
        """Remove a plugin by id.

        Raises KeyError if not found.
        """
        del self._plugins[plugin_id]

    def get(self, plugin_id: str) -> PluginManifest | None:
        """Look up a plugin by id."""
        return self._plugins.get(plugin_id)

    def list(self) -> list[PluginManifest]:
        """Return all registered plugins."""
        return list(self._plugins.values())

    def update_state(self, plugin_id: str, state: PluginState) -> None:
        """Update the lifecycle state of a plugin.

        Raises KeyError if not found.
        """
        manifest = self._plugins[plugin_id]
        manifest.state = state
        if state == PluginState.ACTIVE:
            manifest.activated_at = time.time()
        elif state == PluginState.INACTIVE:
            manifest.activated_at = None

    def count(self, state: PluginState | None = None) -> int:
        """Count plugins, optionally filtered by state."""
        if state is None:
            return len(self._plugins)
        return sum(1 for m in self._plugins.values() if m.state == state)
