"""Tests for PluginHost lifecycle and PluginDiscoverer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cscode.core.plugin.api import CommandDef, PluginAPI, UIExtension
from cscode.core.plugin.discovery import PluginDiscoverer
from cscode.core.plugin.host import PluginHost
from cscode.core.plugin.registry import PluginManifest, PluginState
from cscode.schema.tool import ToolResult
from cscode.tools.base import BaseTool
from typing import Any


# ── Helper Tools ──────────────────────────────────────────────────────


class _ReaderTool(BaseTool):
    name = "reader"
    description = "Reads stuff"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data="read")


class _WriterTool(BaseTool):
    name = "writer"
    description = "Writes stuff"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data="write")


# ── PluginRegistry Tests (basic, done in test_plugin_registry.py) ─────


class TestPluginHostLifecycle:
    async def test_discover_local_empty(self) -> None:
        """Empty directory yields no plugins."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            manifests = await host.discover([tmp])
        assert manifests == []

    async def test_discover_new_plugins_registered(self) -> None:
        """Discovered plugins are registered."""
        host = PluginHost()
        m = PluginManifest(id="test-p", name="Test", version="1.0.0", source="/tmp")
        host.registry.register(m)

        # No new plugins found in empty dir
        with tempfile.TemporaryDirectory() as tmp:
            manifests = await host.discover([tmp])
        assert manifests == []
        assert host.registry.count() == 1

    async def test_activate_unknown_raises(self) -> None:
        host = PluginHost()
        with pytest.raises(ValueError, match="not found"):
            await host.activate("nonexistent")

    async def test_activate_and_deactivate(self) -> None:
        host = PluginHost()
        m = PluginManifest(id="p1", name="P1", version="1.0.0")
        host.registry.register(m)

        api = await host.activate("p1")
        assert isinstance(api, PluginAPI)
        m1 = host.registry.get("p1")
        assert m1 is not None
        assert m1.state == PluginState.ACTIVE

        await host.deactivate("p1")
        m2 = host.registry.get("p1")
        assert m2 is not None
        assert m2.state == PluginState.INACTIVE

    async def test_activate_twice_raises(self) -> None:
        host = PluginHost()
        m = PluginManifest(id="p1", name="P1", version="1.0.0")
        host.registry.register(m)

        await host.activate("p1")
        with pytest.raises(ValueError, match="already active"):
            await host.activate("p1")

    async def test_deactivate_not_active_raises(self) -> None:
        host = PluginHost()
        host.registry.register(PluginManifest(id="p1", name="P1", version="1.0.0"))
        with pytest.raises(ValueError, match="not active"):
            await host.deactivate("p1")

    async def test_uninstall(self) -> None:
        host = PluginHost()
        host.registry.register(PluginManifest(id="p1", name="P1", version="1.0.0"))
        await host.uninstall("p1")
        assert host.registry.get("p1") is None

    async def test_uninstall_deactivates_first(self) -> None:
        host = PluginHost()
        m = PluginManifest(id="p1", name="P1", version="1.0.0")
        host.registry.register(m)
        await host.activate("p1")
        await host.uninstall("p1")
        assert host.registry.get("p1") is None

    async def test_uninstall_missing_raises(self) -> None:
        host = PluginHost()
        with pytest.raises(ValueError, match="not found"):
            await host.uninstall("nonexistent")

    async def test_install_creates_minimal_manifest(self) -> None:
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            m = await host.install(tmp)
        assert m.id is not None
        assert m.state == PluginState.DISCOVERED
        assert m.installed_at > 0

    async def test_get_tool_providers_empty(self) -> None:
        host = PluginHost()
        assert host.get_tool_providers() == []

    async def test_get_tool_providers_from_active_plugin(self) -> None:
        host = PluginHost()
        host.registry.register(PluginManifest(id="p1", name="P1", version="1.0.0"))
        api = await host.activate("p1")
        api.register_tool(_ReaderTool)

        tools = host.get_tool_providers()
        assert len(tools) == 1
        assert tools[0] is _ReaderTool

    async def test_get_tool_providers_multiple_plugins(self) -> None:
        host = PluginHost()
        host.registry.register(PluginManifest(id="a", name="A", version="1.0"))
        host.registry.register(PluginManifest(id="b", name="B", version="1.0"))
        api_a = await host.activate("a")
        api_b = await host.activate("b")
        api_a.register_tool(_ReaderTool)
        api_b.register_tool(_WriterTool)

        tools = host.get_tool_providers()
        assert len(tools) == 2

    async def test_get_commands(self) -> None:
        host = PluginHost()
        host.registry.register(PluginManifest(id="p1", name="P1", version="1.0"))
        api = await host.activate("p1")
        api.register_command(CommandDef(name="deploy", description="Deploy"))
        api.register_command(CommandDef(name="rollback", description="Rollback"))

        cmds = host.get_commands()
        assert len(cmds) == 2
        names = {c.name for c in cmds}
        assert names == {"deploy", "rollback"}

    async def test_get_ui_extensions(self) -> None:
        host = PluginHost()
        host.registry.register(PluginManifest(id="p1", name="P1", version="1.0"))
        api = await host.activate("p1")
        api.add_tui_panel(UIExtension(layer="tui", extension_id="panel1"))
        api.add_web_route(UIExtension(layer="web", extension_id="route1"))

        all_ext = host.get_ui_extensions()
        assert len(all_ext) == 2
        tui_ext = host.get_ui_extensions("tui")
        assert len(tui_ext) == 1


class TestPluginDiscoverer:
    async def test_discover_local_empty_dir(self) -> None:
        d = PluginDiscoverer()
        with tempfile.TemporaryDirectory() as tmp:
            manifests = await d.discover_local([tmp])
        assert manifests == []

    async def test_discover_local_with_plugin_dir(self) -> None:
        d = PluginDiscoverer()
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / "my-plugin"
            plugin_dir.mkdir()
            init_file = plugin_dir / "__init__.py"
            init_file.write_text('__plugin_name__ = "MyPlugin"\n')

            manifests = await d.discover_local([tmp])
            assert len(manifests) == 1
            assert manifests[0].id == "my-plugin"
            assert manifests[0].name == "MyPlugin"

    async def test_discover_local_skips_non_plugin_dirs(self) -> None:
        d = PluginDiscoverer()
        with tempfile.TemporaryDirectory() as tmp:
            empty_dir = Path(tmp) / "not-a-plugin"
            empty_dir.mkdir()
            # No __init__.py

            manifests = await d.discover_local([tmp])
            assert manifests == []

    async def test_discover_local_skips_nonexistent_dir(self) -> None:
        d = PluginDiscoverer()
        manifests = await d.discover_local(["/nonexistent/path"])
        assert manifests == []

    async def test_discover_local_dedup(self) -> None:
        """Same path scanned twice should not yield duplicates."""
        d = PluginDiscoverer()
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / "dup-plugin"
            plugin_dir.mkdir()
            (plugin_dir / "__init__.py").write_text("")
            r1 = await d.discover_local([tmp, tmp])
        assert len(r1) == 1

    async def test_discover_git_parses_url(self) -> None:
        d = PluginDiscoverer()
        manifests = await d.discover_git(["https://github.com/user/cscode-plugin.git"])
        assert len(manifests) == 1
        assert manifests[0].id == "git:cscode-plugin"
        assert manifests[0].source == "https://github.com/user/cscode-plugin.git"
