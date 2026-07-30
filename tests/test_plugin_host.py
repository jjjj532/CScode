"""Tests for PluginHost lifecycle and PluginDiscoverer."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from cscode.core.events import Event, EventBus
from cscode.core.plugin.api import CommandDef, PluginAPI, UIExtension
from cscode.core.plugin.discovery import PluginDiscoverer
from cscode.core.plugin.host import PluginHost
from cscode.core.plugin.registry import PluginManifest, PluginState
from cscode.schema.tool import ToolResult
from cscode.tools.base import BaseTool

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


# ── Activation Pipeline Tests ─────────────────────────────────────────


def _create_test_plugin(tmp_dir: Path, source: str) -> PluginManifest:
    """Create a PluginManifest pointing to a temp dir with __init__.py."""
    manifest = PluginManifest(
        id=tmp_dir.name,
        name=tmp_dir.name,
        version="1.0.0",
        source=source,
    )
    return manifest


def _write_init(p: Path, content: str) -> Path:
    init_file = p / "__init__.py"
    init_file.write_text(content)
    return init_file


class TestPluginHostActivation:
    """Tests for the PluginHost activation pipeline (load/activate/deactivate callbacks)."""

    async def test_load_unknown_raises(self) -> None:
        """load() with nonexistent plugin raises ValueError."""
        host = PluginHost()
        with pytest.raises(ValueError, match="not found"):
            await host.load("nonexistent")

    async def test_load_twice_raises(self) -> None:
        """load() called twice on same plugin raises ValueError."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_load_twice"
            p.mkdir()
            _write_init(p, "")
            host.registry.register(PluginManifest(
                id="load_twice", name="LT", version="1.0", source=str(p),
            ))
            await host.load("load_twice")
            with pytest.raises(ValueError, match="already loaded"):
                await host.load("load_twice")

    async def test_activate_calls_plugin_activate(self) -> None:
        """activate() invokes module's activate(api) callback."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_act_cb"
            p.mkdir()
            _write_init(p, """
from cscode.core.plugin.api import PluginAPI

_called = False

def activate(api: PluginAPI) -> None:
    global _called
    _called = True
""")
            pid = "act_cb"
            host.registry.register(PluginManifest(
                id=pid, name="ActCB", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            # Verify module.activate() was called — import the module and check
            mod = sys.modules.get("test_act_cb")
            assert mod is not None, "Plugin module should be imported"
            assert mod._called is True  # type: ignore[union-attr]

    async def test_activate_registers_tools_via_callback(self) -> None:
        """Plugin registers tools via activate(api); host.get_tool_providers reflects them."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_act_tools"
            p.mkdir()
            _write_init(p, """
from cscode.core.plugin.api import PluginAPI

class _ReaderTool:
    name = "reader"
    description = "Reads stuff"

def activate(api: PluginAPI) -> None:
    api.register_tool(_ReaderTool)
""")
            pid = "act_tools"
            host.registry.register(PluginManifest(
                id=pid, name="ActTools", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            tools = host.get_tool_providers()
            assert len(tools) == 1
            assert tools[0].name == "reader"

    async def test_deactivate_calls_plugin_deactivate(self) -> None:
        """deactivate() invokes module's deactivate() callback."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_deact_cb"
            p.mkdir()
            _write_init(p, """
_called = False

def activate(api: object) -> None:
    pass

def deactivate() -> None:
    global _called
    _called = True
""")
            pid = "deact_cb"
            host.registry.register(PluginManifest(
                id=pid, name="DeactCB", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            await host.deactivate(pid)

            mod = sys.modules.get("test_deact_cb")
            assert mod is not None
            assert mod._called is True  # type: ignore[union-attr]

    async def test_deactivate_cleans_loaded_module(self) -> None:
        """deactivate() removes the module from _loaded_modules."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_deact_clean"
            p.mkdir()
            _write_init(p, "")
            pid = "deact_clean"
            host.registry.register(PluginManifest(
                id=pid, name="DeactClean", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            assert pid in host._loaded_modules  # type: ignore[attr-defined]
            await host.deactivate(pid)
            assert pid not in host._loaded_modules  # type: ignore[attr-defined]

    async def test_activate_import_error_raised(self) -> None:
        """activate() on a plugin with invalid module raises ImportError."""
        host = PluginHost()
        host.registry.register(PluginManifest(
            id="bad_import", name="Bad", version="1.0", source="/nonexistent/path",
        ))
        with pytest.raises(ImportError):
            await host.activate("bad_import")

    async def test_activate_with_eventbus_hooks_wired(self) -> None:
        """Plugin register on_session_start hook via EventBus."""
        bus = EventBus()
        host = PluginHost(event_bus=bus)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_eb_hook"
            p.mkdir()
            _write_init(p, """
from cscode.core.plugin.api import PluginAPI

_handler_called = False

def handler(event: object) -> None:
    global _handler_called
    _handler_called = True

def activate(api: PluginAPI) -> None:
    api.on_session_start(handler)
""")
            pid = "eb_hook"
            host.registry.register(PluginManifest(
                id=pid, name="EBHook", version="1.0", source=str(p),
            ))
            await host.activate(pid)

            # Emit a session.start event — the plugin handler should fire
            await bus.emit("session.start", Event())

            mod = sys.modules.get("test_eb_hook")
            assert mod is not None
            assert mod._handler_called is True  # type: ignore[union-attr]


class TestPluginHostLifecycleHooks:
    """Tests for install(api)/uninstall() callbacks and error resilience."""

    # ── install(api) callback ──────────────────────────────────────────

    async def test_install_calls_plugin_install_callback(self) -> None:
        """install() invokes module's install(api) when source has __init__.py with install()."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_install_cb"
            p.mkdir()
            _write_init(p, """
from cscode.core.plugin.api import PluginAPI

_called = False

def install(api: PluginAPI) -> None:
    global _called
    _called = True
""")
            await host.install(str(p))
            mod = sys.modules.get("test_install_cb")
            assert mod is not None, "Plugin module should be imported"
            assert mod._called is True  # type: ignore[union-attr]

    async def test_install_callback_receives_plugin_api(self) -> None:
        """install(api) receives a PluginAPI instance."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_install_api"
            p.mkdir()
            _write_init(p, """
from cscode.core.plugin.api import PluginAPI

_received: PluginAPI | None = None

def install(api: PluginAPI) -> None:
    global _received
    _received = api
""")
            await host.install(str(p))
            mod = sys.modules.get("test_install_api")
            assert mod is not None
            assert mod._received is not None  # type: ignore[union-attr]
            assert isinstance(mod._received, PluginAPI)  # type: ignore[union-attr]

    async def test_install_no_callback_still_works(self) -> None:
        """install() works fine when module has no install() function."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_install_none"
            p.mkdir()
            _write_init(p, "")
            m = await host.install(str(p))
            assert m.state == PluginState.DISCOVERED

    # ── uninstall() callback ───────────────────────────────────────────

    async def test_uninstall_calls_plugin_uninstall_callback(self) -> None:
        """uninstall() invokes module's uninstall() when module has it."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_uninstall_cb"
            p.mkdir()
            _write_init(p, """
_called = False

def uninstall() -> None:
    global _called
    _called = True
""")
            pid = "uninstall_cb"
            host.registry.register(PluginManifest(
                id=pid, name="UninstCB", version="1.0", source=str(p),
            ))
            await host.install(str(p))
            await host.uninstall(pid)
            mod = sys.modules.get("test_uninstall_cb")
            assert mod is not None
            assert mod._called is True  # type: ignore[union-attr]

    async def test_uninstall_no_callback_still_works(self) -> None:
        """uninstall() works fine when module has no uninstall() function."""
        host = PluginHost()
        host.registry.register(PluginManifest(
            id="no_uninst", name="NoUninst", version="1.0",
        ))
        await host.uninstall("no_uninst")
        assert host.registry.get("no_uninst") is None

    async def test_uninstall_callback_called_before_removal(self) -> None:
        """uninstall() is called while the manifest still exists."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_uninst_order"
            p.mkdir()
            _write_init(p, """
from cscode.core.plugin.registry import PluginManifest, PluginState

_manifest_before: object = None

def uninstall() -> None:
    global _manifest_before
    import sys
    _manifest_before = "called"
""")
            pid = "uninst_order"
            host.registry.register(PluginManifest(
                id=pid, name="UninstOrder", version="1.0", source=str(p),
            ))
            await host.install(str(p))
            await host.uninstall(pid)
            # Verify plugin was removed
            assert host.registry.get(pid) is None

    # ── Error resilience during activate() ─────────────────────────────

    async def test_activate_does_not_crash_on_callback_error(self) -> None:
        """If module.activate(api) raises, host should catch and set state to INACTIVE."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_act_err"
            p.mkdir()
            _write_init(p, """
def activate(api: object) -> None:
    raise RuntimeError("Plugin activation failed")
""")
            pid = "act_err"
            host.registry.register(PluginManifest(
                id=pid, name="ActErr", version="1.0", source=str(p),
            ))
            api = await host.activate(pid)
            assert isinstance(api, PluginAPI)
            m = host.registry.get(pid)
            assert m is not None
            # Should not be ACTIVE — either INACTIVE or LOADED
            assert m.state != PluginState.ACTIVE

    async def test_activate_error_does_not_affect_other_plugins(self) -> None:
        """A failing plugin's activate() should not crash other plugins."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            # Good plugin
            gp = Path(tmp) / "good_plugin"
            gp.mkdir()
            _write_init(gp, """
def activate(api: object) -> None:
    pass
""")
            # Bad plugin
            bp = Path(tmp) / "bad_plugin"
            bp.mkdir()
            _write_init(bp, """
def activate(api: object) -> None:
    raise RuntimeError("bad")
""")
            host.registry.register(PluginManifest(
                id="good", name="Good", version="1.0", source=str(gp),
            ))
            host.registry.register(PluginManifest(
                id="bad", name="Bad", version="1.0", source=str(bp),
            ))
            # Activate good one first
            await host.activate("good")
            m_good = host.registry.get("good")
            assert m_good is not None and m_good.state == PluginState.ACTIVE

            # Activate bad one — should not crash
            api = await host.activate("bad")
            assert isinstance(api, PluginAPI)
            m_bad = host.registry.get("bad")
            assert m_bad is not None and m_bad.state != PluginState.ACTIVE

            # Good plugin should still be active
            m_good2 = host.registry.get("good")
            assert m_good2 is not None and m_good2.state == PluginState.ACTIVE


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


class TestPluginHostBuildPluginContext:
    """Tests for PluginHost.build_plugin_context()."""

    async def test_no_active_plugins_returns_empty_context(self) -> None:
        """No active plugins → empty SystemContext."""
        host = PluginHost()
        ctx = await host.build_plugin_context()
        assert len(ctx.sources) == 0

    async def test_active_plugin_without_sources_returns_empty(self) -> None:
        """Active plugin with no context sources → empty SystemContext."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "no_src"
            p.mkdir()
            _write_init(p, """
from cscode.core.plugin.api import PluginAPI

def activate(api: PluginAPI) -> None:
    pass  # no context sources registered
""")
            pid = "no_src"
            host.registry.register(PluginManifest(
                id=pid, name="NoSrc", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            ctx = await host.build_plugin_context()
            assert len(ctx.sources) == 0

    async def test_single_plugin_with_context_source(self) -> None:
        """Single plugin with one context source → SystemContext with that source."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "src_plugin"
            p.mkdir()
            _write_init(p, """
from cscode.core.plugin.api import PluginAPI
from cscode.plugins.context_source import PluginContextSource

async def _load() -> str:
    return "active"

def activate(api: PluginAPI) -> None:
    src = PluginContextSource(
        key="plugin/status",
        load=_load,
        baseline=lambda v: f"Status: {v}",
        update=lambda old, new: f"Status: {old} -> {new}",
    )
    api.register_context_source(src)
""")
            pid = "src_plugin"
            host.registry.register(PluginManifest(
                id=pid, name="SrcPlugin", version="1.0", source=str(p),
            ))
            await host.activate(pid)

            ctx = await host.build_plugin_context()
            assert len(ctx.sources) == 1
            from cscode.core.system_context import ContextKey
            assert ContextKey("plugin/status") in ctx.sources

    async def test_multiple_plugins_aggregated(self) -> None:
        """Multiple plugins with context sources → all sources in SystemContext."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            # Plugin A
            pa = Path(tmp) / "plugin_a"
            pa.mkdir()
            _write_init(pa, """
from cscode.core.plugin.api import PluginAPI
from cscode.plugins.context_source import PluginContextSource

async def _load_a() -> str:
    return "a"

def activate(api: PluginAPI) -> None:
    src = PluginContextSource(
        key="plugin/a",
        load=_load_a,
        baseline=lambda v: f"a: {v}",
        update=lambda old, new: f"a: {old} -> {new}",
    )
    api.register_context_source(src)
""")
            # Plugin B
            pb = Path(tmp) / "plugin_b"
            pb.mkdir()
            _write_init(pb, """
from cscode.core.plugin.api import PluginAPI
from cscode.plugins.context_source import PluginContextSource

async def _load_b() -> str:
    return "b"

def activate(api: PluginAPI) -> None:
    src = PluginContextSource(
        key="plugin/b",
        load=_load_b,
        baseline=lambda v: f"b: {v}",
        update=lambda old, new: f"b: {old} -> {new}",
    )
    api.register_context_source(src)
""")
            host.registry.register(PluginManifest(
                id="plugin_a", name="PluginA", version="1.0", source=str(pa),
            ))
            host.registry.register(PluginManifest(
                id="plugin_b", name="PluginB", version="1.0", source=str(pb),
            ))
            await host.activate("plugin_a")
            await host.activate("plugin_b")

            ctx = await host.build_plugin_context()
            assert len(ctx.sources) == 2
            from cscode.core.system_context import ContextKey
            assert ContextKey("plugin/a") in ctx.sources
            assert ContextKey("plugin/b") in ctx.sources

    async def test_context_after_plugin_deactivation(self) -> None:
        """Deactivating a plugin should remove its context sources."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "deact_src"
            p.mkdir()
            _write_init(p, """
from cscode.core.plugin.api import PluginAPI
from cscode.plugins.context_source import PluginContextSource

async def _load() -> str:
    return "active"

def activate(api: PluginAPI) -> None:
    src = PluginContextSource(
        key="plugin/temp",
        load=_load,
        baseline=lambda v: f"Status: {v}",
        update=lambda old, new: f"Status: {old} -> {new}",
    )
    api.register_context_source(src)
""")
            pid = "deact_src"
            host.registry.register(PluginManifest(
                id=pid, name="DeactSrc", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            ctx_active = await host.build_plugin_context()
            assert len(ctx_active.sources) == 1

            await host.deactivate(pid)
            ctx_deact = await host.build_plugin_context()
            assert len(ctx_deact.sources) == 0


class TestPluginHostRenderPluginContext:
    """Tests for PluginHost.render_plugin_context()."""

    async def test_no_active_plugins_returns_empty_string(self) -> None:
        """No active plugins → empty string."""
        host = PluginHost()
        text = await host.render_plugin_context()
        assert text == ""

    async def test_active_plugin_without_sources_returns_empty(self) -> None:
        """Active plugin with no context sources → empty string."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "no_src_render"
            p.mkdir()
            _write_init(p, """
from cscode.core.plugin.api import PluginAPI

def activate(api: PluginAPI) -> None:
    pass
""")
            pid = "no_src_render"
            host.registry.register(PluginManifest(
                id=pid, name="NoSrcRender", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            text = await host.render_plugin_context()
            assert text == ""

    async def test_plugin_with_context_source_returns_baseline(self) -> None:
        """Plugin with context source → baseline text returned."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "render_src"
            p.mkdir()
            _write_init(p, """
from cscode.core.plugin.api import PluginAPI
from cscode.plugins.context_source import PluginContextSource

async def _load() -> str:
    return "ready"

def activate(api: PluginAPI) -> None:
    src = PluginContextSource(
        key="plugin/status",
        load=_load,
        baseline=lambda v: f"Plugin status: {v}",
        update=lambda old, new: f"Plugin status: {old} -> {new}",
    )
    api.register_context_source(src)
""")
            pid = "render_src"
            host.registry.register(PluginManifest(
                id=pid, name="RenderSrc", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            text = await host.render_plugin_context()
            assert "Plugin status: ready" in text

    async def test_multiple_plugins_aggregated_baseline(self) -> None:
        """Multiple plugins → merged baseline text."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            pa = Path(tmp) / "rpa"
            pa.mkdir()
            _write_init(pa, """
from cscode.core.plugin.api import PluginAPI
from cscode.plugins.context_source import PluginContextSource

async def _load_a() -> str:
    return "value_a"

def activate(api: PluginAPI) -> None:
    src = PluginContextSource(
        key="plugin/a",
        load=_load_a,
        baseline=lambda v: f"Source A: {v}",
        update=lambda old, new: f"A: {old} -> {new}",
    )
    api.register_context_source(src)
""")
            pb = Path(tmp) / "rpb"
            pb.mkdir()
            _write_init(pb, """
from cscode.core.plugin.api import PluginAPI
from cscode.plugins.context_source import PluginContextSource

async def _load_b() -> str:
    return "value_b"

def activate(api: PluginAPI) -> None:
    src = PluginContextSource(
        key="plugin/b",
        load=_load_b,
        baseline=lambda v: f"Source B: {v}",
        update=lambda old, new: f"B: {old} -> {new}",
    )
    api.register_context_source(src)
""")
            host.registry.register(PluginManifest(
                id="rpa", name="RPA", version="1.0", source=str(pa),
            ))
            host.registry.register(PluginManifest(
                id="rpb", name="RPB", version="1.0", source=str(pb),
            ))
            await host.activate("rpa")
            await host.activate("rpb")
            text = await host.render_plugin_context()
            assert "Source A: value_a" in text
            assert "Source B: value_b" in text
