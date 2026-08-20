"""TuiPluginAPI — Textual TUI 插件接口（spec §5.2.3）。

对齐 OpenCode TuiPlugin API 的 Python 版（裁剪）：
app / command(register) / theme(install/set) / kv(state) / screens(navigate)。
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TuiPluginHost(Protocol):
    """Duck-typed host surface the plugin API talks to.

    Implemented by CScodeTUI (and _FakeHost in tests).
    """

    @property
    def registry(self) -> Any: ...

    def navigate(self, screen: str, params: dict[str, object] | None = None) -> None: ...

    def install_theme(self, name: str, theme: object) -> None: ...

    def set_theme(self, name: str) -> bool: ...

    def get_kv(self) -> dict[str, object]: ...


class TuiPluginAPI:
    """API handed to a plugin's ``install(api)`` callback."""

    def __init__(self, host: TuiPluginHost, plugin_id: str = "") -> None:
        self._host = host
        self._plugin_id = plugin_id
        self._kv: dict[str, object] = {}

    # ── Commands ──────────────────────────────────────────────────

    def register_command(
        self,
        name: str,
        handler: Callable[[str], Coroutine[object, object, None] | None],
        category: str = "general",
        aliases: list[str] | None = None,
    ) -> None:
        """Register a slash command in the TUI command panel."""
        self._host.registry.register(
            name,
            handler,
            category=category,
            aliases=aliases,
            plugin_id=self._plugin_id,
        )

    # ── Screens ──────────────────────────────────────────────────

    def navigate(self, screen: str, params: dict[str, object] | None = None) -> None:
        """Push a named screen (delegates to the host app)."""
        self._host.navigate(screen, params)

    # ── Theme ────────────────────────────────────────────────────

    def theme_set(self, name: str) -> bool:
        """Switch the active theme. Returns False if the theme is unknown."""
        return self._host.set_theme(name)

    def theme_install(self, name: str, theme: object) -> None:
        """Install a custom theme definition on the host."""
        self._host.install_theme(name, theme)

    # ── KV state ─────────────────────────────────────────────────

    def kv_set(self, key: str, value: object) -> None:
        """Store a plugin-scoped key/value pair."""
        self._kv[key] = value

    def kv_get(self, key: str) -> object | None:
        """Read a plugin-scoped value, or None if missing."""
        return self._kv.get(key)

    def kv_store(self) -> dict[str, object]:
        """Return the plugin's full KV state (for lifecycle cleanup)."""
        return self._kv


def _import_plugin_module(module_path: Path) -> ModuleType | None:
    """Import a plugin.py by file path, caching in sys.modules."""
    spec = importlib.util.spec_from_file_location(
        f"cscode_tui_plugin_{module_path.parent.name}", module_path
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TuiPluginLoader:
    """Discovers plugin.py modules and wires them to the TUI host.

    Each plugin module exposes an ``install(api)`` callback. Deactivation
    removes every command the plugin registered — no residual state.
    """

    def __init__(self, host: TuiPluginHost) -> None:
        self._host = host
        self._active: list[tuple[str, TuiPluginAPI]] = []

    def load(self, plugin_dirs: list[str]) -> list[TuiPluginAPI]:
        """Load plugins from the given directories. Returns active APIs."""
        apis: list[TuiPluginAPI] = []
        for dir_str in plugin_dirs:
            plugin_dir = Path(dir_str)
            if not plugin_dir.is_dir():
                continue
            module_paths: list[Path] = []
            direct = plugin_dir / "plugin.py"
            if direct.is_file():
                module_paths.append(direct)
            module_paths.extend(sorted(plugin_dir.glob("*/plugin.py")))
            for module_path in module_paths:
                api = self._install(module_path)
                if api is not None:
                    apis.append(api)
                    self._active.append((module_path.parent.name, api))
        return apis

    def _install(self, module_path: Path) -> TuiPluginAPI | None:
        module = _import_plugin_module(module_path)
        if module is None or not hasattr(module, "install"):
            return None
        api = TuiPluginAPI(self._host, plugin_id=module_path.parent.name)
        try:
            module.install(api)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "TuiPluginLoader: install failed for %s", module_path
            )
            return None
        return api

    def deactivate_all(self) -> None:
        """Deactivate every plugin, removing all registered commands."""
        for _plugin_id, api in self._active:
            for cmd in api._host.registry.list():
                if cmd.plugin_id == api._plugin_id:
                    api._host.registry.unregister(cmd.name)
        self._active.clear()
