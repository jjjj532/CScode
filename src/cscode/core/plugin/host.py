"""PluginHost — plugin lifecycle orchestrator.

Manages the full lifecycle: discover → install → load → activate → deactivate → uninstall.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from cscode.core.plugin.api import (
    CommandDef,
    PluginAPI,
    UIExtension,
)
from cscode.core.plugin.discovery import PluginDiscoverer
from cscode.core.plugin.registry import PluginManifest, PluginRegistry, PluginState
from cscode.tools.base import BaseTool
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class PluginHost:
    """Plugin lifecycle orchestrator.

    Wires together PluginRegistry, PluginDiscoverer, and PluginAPI
    into a cohesive lifecycle manager.
    """

    def __init__(
        self,
        registry: PluginRegistry | None = None,
        discoverer: PluginDiscoverer | None = None,
        api_provider: Callable[[], PluginAPI] | None = None,
        pip_packages: list[str] | None = None,
    ) -> None:
        self._registry = registry or PluginRegistry()
        self._discoverer = discoverer or PluginDiscoverer()
        self._pip_packages = pip_packages or []

        # Per-plugin API instances (created on activate)
        self._plugin_apis: dict[str, PluginAPI] = {}

    @property
    def registry(self) -> PluginRegistry:
        """Expose the underlying registry for querying."""
        return self._registry

    # ── Discovery ─────────────────────────────────────────────────────

    async def discover(self, sources: list[str]) -> list[PluginManifest]:
        """Discover plugins from local paths and pip packages.

        Args:
            sources: List of local directory paths to scan.

        Returns:
            List of newly discovered PluginManifests.
        """
        manifests = await self._discoverer.discover_local(sources)

        if self._pip_packages:
            pip_manifests = await self._discoverer.discover_pip(self._pip_packages)
            manifests.extend(pip_manifests)

        registered: list[PluginManifest] = []
        for m in manifests:
            existing = self._registry.get(m.id)
            if existing is None:
                m.state = PluginState.DISCOVERED
                self._registry.register(m)
                registered.append(m)

        logger.info("PluginHost.discover: %d new, %d total", len(registered), self._registry.count())
        return registered

    # ── Install ───────────────────────────────────────────────────────

    async def install(self, source: str) -> PluginManifest:
        """Install a plugin from a source path/URL.

        For Phase 0, this registers a DISCOVERED manifest without
        actual package installation (pip/git clone).
        """
        manifests = await self._discoverer.discover_local([source])
        if not manifests:
            # Create a minimal manifest for the source
            plugin_id = source.rstrip("/").split("/")[-1]
            m = PluginManifest(
                id=plugin_id,
                name=plugin_id,
                version="0.0.0",
                source=source,
                state=PluginState.DISCOVERED,
                installed_at=time.time(),
            )
            self._registry.register(m)
            return m

        m = manifests[0]
        m.installed_at = time.time()
        # Update if already registered
        existing = self._registry.get(m.id)
        if existing is None:
            self._registry.register(m)
        else:
            existing.installed_at = m.installed_at
            existing.source = m.source
        return m

    # ── Activate ──────────────────────────────────────────────────────

    async def activate(self, plugin_id: str) -> PluginAPI:
        """Activate a plugin and return its PluginAPI.

        Transitions state: DISCOVERED/LOADED → ACTIVE.
        Creates a PluginAPI instance that the plugin can use
        to register tools, commands, hooks, etc.
        """
        manifest = self._registry.get(plugin_id)
        if manifest is None:
            msg = f"Plugin '{plugin_id}' not found"
            raise ValueError(msg)

        if manifest.state == PluginState.ACTIVE:
            msg = f"Plugin '{plugin_id}' is already active"
            raise ValueError(msg)

        # Create a fresh PluginAPI for this plugin
        api = PluginAPI()
        self._plugin_apis[plugin_id] = api
        self._registry.update_state(plugin_id, PluginState.ACTIVE)

        logger.info("PluginHost.activate: plugin=%s version=%s", plugin_id, manifest.version)
        return api

    # ── Deactivate ────────────────────────────────────────────────────

    async def deactivate(self, plugin_id: str) -> None:
        """Deactivate a plugin.

        Transitions state: ACTIVE → INACTIVE.
        Removes the PluginAPI instance.
        """
        manifest = self._registry.get(plugin_id)
        if manifest is None:
            msg = f"Plugin '{plugin_id}' not found"
            raise ValueError(msg)

        if manifest.state != PluginState.ACTIVE:
            msg = f"Plugin '{plugin_id}' is not active (state={manifest.state.value})"
            raise ValueError(msg)

        self._plugin_apis.pop(plugin_id, None)
        self._registry.update_state(plugin_id, PluginState.INACTIVE)

        logger.info("PluginHost.deactivate: plugin=%s", plugin_id)

    # ── Uninstall ─────────────────────────────────────────────────────

    async def uninstall(self, plugin_id: str) -> None:
        """Uninstall a plugin and remove it from the registry."""
        manifest = self._registry.get(plugin_id)
        if manifest is None:
            msg = f"Plugin '{plugin_id}' not found"
            raise ValueError(msg)

        # Deactivate first if active
        if manifest.state == PluginState.ACTIVE:
            await self.deactivate(plugin_id)

        self._plugin_apis.pop(plugin_id, None)
        self._registry.unregister(plugin_id)

        logger.info("PluginHost.uninstall: plugin=%s", plugin_id)

    # ── Queries ───────────────────────────────────────────────────────

    def get_tool_providers(self) -> list[type[BaseTool]]:
        """Collect tools from all active plugin APIs."""
        tools: list[type[BaseTool]] = []
        seen: set[str] = set()
        for api in self._plugin_apis.values():
            for t in api.get_tools():
                name = getattr(t, "name", t.__name__.lower())
                if name not in seen:
                    tools.append(t)
                    seen.add(name)
        return tools

    def get_commands(self) -> list[CommandDef]:
        """Collect commands from all active plugin APIs."""
        commands: list[CommandDef] = []
        seen: set[str] = set()
        for api in self._plugin_apis.values():
            for c in api.get_commands():
                if c.name not in seen:
                    commands.append(c)
                    seen.add(c.name)
        return commands

    def get_ui_extensions(self, layer: str | None = None) -> list[UIExtension]:
        """Collect UI extensions from all active plugin APIs."""
        extensions: list[UIExtension] = []
        seen: set[str] = set()
        for api in self._plugin_apis.values():
            for e in api.get_ui_extensions(layer):
                key = f"{e.layer}:{e.extension_id}"
                if key not in seen:
                    extensions.append(e)
                    seen.add(key)
        return extensions
