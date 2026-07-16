"""PluginHost — plugin lifecycle orchestrator.

Manages the full lifecycle: discover → install → load → activate → deactivate → uninstall.
"""

from __future__ import annotations

import importlib
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from cscode.core.events import EventBus
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


def _import_plugin(manifest: PluginManifest) -> ModuleType:
    """Import a plugin's Python module from its source path.

    Args:
        manifest: Plugin manifest with ``source`` field.
                  Supports ``pip:<pkg_name>`` and local directory paths.

    Returns:
        The imported module.

    Raises:
        ImportError: If the module cannot be imported.
    """
    source = manifest.source
    if source.startswith("pip:"):
        pkg_name = source[4:]
        return importlib.import_module(pkg_name)

    # Local path
    path = Path(source).resolve()
    if path.is_dir():
        parent = str(path.parent)
        mod_name = path.name
    else:
        parent = str(path.parent)
        mod_name = path.stem

    if parent not in sys.path:
        sys.path.insert(0, parent)
    return importlib.import_module(mod_name)


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
        event_bus: EventBus | None = None,
    ) -> None:
        self._registry = registry or PluginRegistry()
        self._discoverer = discoverer or PluginDiscoverer()
        self._pip_packages = pip_packages or []
        self._event_bus = event_bus

        self._plugin_apis: dict[str, PluginAPI] = {}
        self._loaded_modules: dict[str, ModuleType] = {}

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

        Registers a DISCOVERED manifest and calls the plugin's
        ``install(api)`` callback (if defined) with a PluginAPI instance.
        The install callback is best-effort — failures are logged but
        do not block the install.
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
            await self._call_install_callback(m)
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
        await self._call_install_callback(m)
        return m

    async def _call_install_callback(self, manifest: PluginManifest) -> None:
        """Call the plugin's ``install(api)`` callback if defined.

        Best-effort: failures are logged but not propagated.
        """
        try:
            module = _import_plugin(manifest)
        except (ImportError, Exception):
            logger.debug("PluginHost._call_install_callback: cannot import plugin %s", manifest.id)
            return
        if hasattr(module, "install"):
            try:
                api = PluginAPI(event_bus=self._event_bus)
                module.install(api)
                logger.info("PluginHost: install callback called for %s", manifest.id)
            except Exception:
                logger.exception("PluginHost._call_install_callback: install callback failed for %s", manifest.id)

    # ── Load ──────────────────────────────────────────────────────────

    async def load(self, plugin_id: str) -> ModuleType:
        """Import the plugin's Python module.

        Transitions state: DISCOVERED → LOADED.
        Uses ``_import_plugin()`` to import the module from the plugin's
        source path (pip package or local directory).

        Args:
            plugin_id: ID of the plugin to load.

        Returns:
            The imported module.

        Raises:
            ValueError: If the plugin is not found or already loaded.
            ImportError: If the module cannot be imported.
        """
        manifest = self._registry.get(plugin_id)
        if manifest is None:
            msg = f"Plugin '{plugin_id}' not found"
            raise ValueError(msg)

        if manifest.state >= PluginState.LOADED:
            msg = f"Plugin '{plugin_id}' is already loaded (state={manifest.state.value})"
            raise ValueError(msg)

        try:
            module = _import_plugin(manifest)
        except ImportError:
            logger.exception("PluginHost.load: failed to import plugin %s", plugin_id)
            raise

        self._loaded_modules[plugin_id] = module
        self._registry.update_state(plugin_id, PluginState.LOADED)

        logger.info("PluginHost.load: plugin=%s module=%s", plugin_id, module.__name__)
        return module

    # ── Activate ──────────────────────────────────────────────────────

    async def activate(self, plugin_id: str) -> PluginAPI:
        """Activate a plugin and return its PluginAPI.

        Transitions state: DISCOVERED/LOADED → ACTIVE.
        Loads the plugin module if not already loaded, creates a PluginAPI
        instance with EventBus, and calls the plugin's ``activate(api)``
        function (if defined).

        Args:
            plugin_id: ID of the plugin to activate.

        Returns:
            PluginAPI instance for the plugin.

        Raises:
            ValueError: If the plugin is not found or already active.
            ImportError: If the plugin module cannot be imported.
        """
        manifest = self._registry.get(plugin_id)
        if manifest is None:
            msg = f"Plugin '{plugin_id}' not found"
            raise ValueError(msg)

        if manifest.state == PluginState.ACTIVE:
            msg = f"Plugin '{plugin_id}' is already active"
            raise ValueError(msg)

        # Load first if not already loaded
        if manifest.state < PluginState.LOADED:
            await self.load(plugin_id)

        # Create PluginAPI with EventBus for hook integration
        api = PluginAPI(event_bus=self._event_bus)
        self._plugin_apis[plugin_id] = api

        # Call plugin's activate(api) callback if defined
        module = self._loaded_modules[plugin_id]
        if hasattr(module, "activate"):
            try:
                module.activate(api)
            except Exception:
                logger.exception(
                    "PluginHost.activate: activate callback failed for plugin %s, setting INACTIVE",
                    plugin_id,
                )
                self._plugin_apis.pop(plugin_id, None)
                self._loaded_modules.pop(plugin_id, None)
                self._registry.update_state(plugin_id, PluginState.INACTIVE)
                return api

        self._registry.update_state(plugin_id, PluginState.ACTIVE)

        logger.info("PluginHost.activate: plugin=%s version=%s", plugin_id, manifest.version)
        return api

    # ── Deactivate ────────────────────────────────────────────────────

    async def deactivate(self, plugin_id: str) -> None:
        """Deactivate a plugin.

        Transitions state: ACTIVE → INACTIVE.
        Calls the plugin's ``deactivate()`` function (if defined),
        then removes the PluginAPI instance.

        Args:
            plugin_id: ID of the plugin to deactivate.

        Raises:
            ValueError: If the plugin is not found or not active.
        """
        manifest = self._registry.get(plugin_id)
        if manifest is None:
            msg = f"Plugin '{plugin_id}' not found"
            raise ValueError(msg)

        if manifest.state != PluginState.ACTIVE:
            msg = f"Plugin '{plugin_id}' is not active (state={manifest.state.value})"
            raise ValueError(msg)

        # Notify plugin of deactivation
        module = self._loaded_modules.get(plugin_id)
        if module is not None and hasattr(module, "deactivate"):
            module.deactivate()

        self._plugin_apis.pop(plugin_id, None)
        self._loaded_modules.pop(plugin_id, None)
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

        # Call plugin's uninstall() callback if defined (best-effort)
        await self._call_uninstall_callback(manifest)

        self._plugin_apis.pop(plugin_id, None)
        self._registry.unregister(plugin_id)

        logger.info("PluginHost.uninstall: plugin=%s", plugin_id)

    async def _call_uninstall_callback(self, manifest: PluginManifest) -> None:
        """Call the plugin's ``uninstall()`` callback if defined.

        Best-effort: failures are logged but not propagated.
        """
        try:
            module = _import_plugin(manifest)
        except (ImportError, Exception):
            logger.debug("PluginHost._call_uninstall_callback: cannot import plugin %s", manifest.id)
            return
        if hasattr(module, "uninstall"):
            try:
                module.uninstall()
                logger.info("PluginHost: uninstall callback called for %s", manifest.id)
            except Exception:
                logger.exception("PluginHost._call_uninstall_callback: uninstall callback failed for %s", manifest.id)

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
