"""Tests for the PluginSDK→PluginHost bridge.

Tests cover:
1. Detecting PluginSDK instances in a module
2. Building activate(api) functions from SDK instances
3. Full lifecycle: SDK plugin → PluginHost activate → tool registration
4. Explicit activate() still takes priority over SDK bridge
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from cscode.core.plugin.api import PluginAPI
from cscode.core.plugin.host import PluginHost
from cscode.core.plugin.registry import PluginManifest, PluginState
from cscode.plugins.sdk import PluginSDK
from cscode.schema.tool import ToolResult
from cscode.tools.base import BaseTool

# ── Helper Tools ──────────────────────────────────────────────────────


class _HelloTool(BaseTool):
    name = "hello"
    description = "Says hello"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data="hello from sdk")


class _GoodbyeTool(BaseTool):
    name = "goodbye"
    description = "Says goodbye"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data="goodbye from sdk")


# ── Unit: detect SDK instances ────────────────────────────────────────


class TestDetectSDKInstances:
    """Tests for bridge.detect_sdk_instances()."""

    def test_detects_sdk_instance_in_module(self) -> None:
        """detect_sdk_instances finds PluginSDK instances in a module."""
        import types

        from cscode.plugins import bridge
        mod = types.ModuleType("test_mod")
        sdk = PluginSDK(name="test-p", version="1.0.0")
        mod.sdk = sdk

        result = bridge.detect_sdk_instances(mod)
        assert len(result) == 1
        assert result[0] is sdk

    def test_detects_multiple_sdk_instances(self) -> None:
        """Multiple PluginSDK instances are all detected."""
        import types

        from cscode.plugins import bridge
        mod = types.ModuleType("test_mod")
        sdk1 = PluginSDK(name="p1")
        sdk2 = PluginSDK(name="p2")
        mod.sdk_a = sdk1
        mod.sdk_b = sdk2

        result = bridge.detect_sdk_instances(mod)
        assert len(result) == 2

    def test_no_sdk_instances_returns_empty(self) -> None:
        """Module without SDK instances returns empty list."""
        import types

        from cscode.plugins import bridge
        mod = types.ModuleType("test_mod")
        mod.some_attr = 42
        mod.other = "hello"

        result = bridge.detect_sdk_instances(mod)
        assert result == []

    def test_empty_module_returns_empty(self) -> None:
        """Module with no attributes returns empty list."""
        import types

        from cscode.plugins import bridge
        mod = types.ModuleType("empty_mod")

        result = bridge.detect_sdk_instances(mod)
        assert result == []

    def test_skips_non_sdk_objects(self) -> None:
        """Non-SDK objects are skipped during detection."""
        import types

        from cscode.plugins import bridge
        mod = types.ModuleType("test_mod")
        mod.not_sdk = "string"
        mod.also_not = 123
        sdk = PluginSDK(name="real")
        mod.real_sdk = sdk

        result = bridge.detect_sdk_instances(mod)
        assert len(result) == 1
        assert result[0] is sdk


# ── Unit: build activate function ─────────────────────────────────────


class TestBuildActivateFunc:
    """Tests for bridge.build_activate_func()."""

    def test_build_activate_func_registers_tools(self) -> None:
        """Generated activate(api) registers all SDK tools via PluginAPI."""
        from cscode.plugins import bridge

        sdk = PluginSDK(name="test-p", version="1.0.0")
        sdk.tools["hello"] = _HelloTool

        activate = bridge.build_activate_func([sdk])
        api = PluginAPI()
        activate(api)

        tools = api.get_tools()
        assert len(tools) == 1
        assert tools[0] is _HelloTool

    def test_build_activate_func_handles_multiple_sdks(self) -> None:
        """Multiple SDK instances each register their tools."""
        from cscode.plugins import bridge

        sdk1 = PluginSDK(name="p1")
        sdk1.tools["hello"] = _HelloTool
        sdk2 = PluginSDK(name="p2")
        sdk2.tools["goodbye"] = _GoodbyeTool

        activate = bridge.build_activate_func([sdk1, sdk2])
        api = PluginAPI()
        activate(api)

        tools = api.get_tools()
        assert len(tools) == 2

    def test_build_activate_func_empty_sdk_list(self) -> None:
        """Empty SDK list produces a no-op activate function."""
        from cscode.plugins import bridge

        activate = bridge.build_activate_func([])
        api = PluginAPI()
        activate(api)  # Should not raise

        assert api.get_tools() == []

    def test_build_activate_func_skips_sdk_without_tools(self) -> None:
        """SDK with no registered tools doesn't cause errors."""
        from cscode.plugins import bridge

        sdk = PluginSDK(name="empty-p")
        activate = bridge.build_activate_func([sdk])
        api = PluginAPI()
        activate(api)

        assert api.get_tools() == []


# ── Integration: SDK plugin through PluginHost lifecycle ──────────────


def _write_init(p: Path, content: str) -> Path:
    init_file = p / "__init__.py"
    init_file.write_text(content)
    return init_file


class TestPluginHostSDKBridge:
    """SDK-style plugins activated through PluginHost lifecycle."""

    async def test_host_activates_sdk_plugin_without_explicit_activate(self) -> None:
        """PluginHost.activate() auto-bridges SDK modules without explicit activate()."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sdk_only"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK

sdk = PluginSDK(name="sdk-only", version="1.0.0")

@sdk.tool(name="hello")
class HelloTool:
    name = "hello"
    description = "Says hello"
    async def execute(self, args):
        return {"success": True, "data": "hi"}
""")
            pid = "sdk_only"
            host.registry.register(PluginManifest(
                id=pid, name="SDKOnly", version="1.0", source=str(p),
            ))
            api = await host.activate(pid)

            assert isinstance(api, PluginAPI)
            m = host.registry.get(pid)
            assert m is not None
            assert m.state == PluginState.ACTIVE

            tools = host.get_tool_providers()
            assert len(tools) == 1
            assert tools[0].name == "hello"

    async def test_host_activates_sdk_plugin_twice_raises(self) -> None:
        """SDK plugin that's already active raises on second activate."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sdk_twice"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK
sdk = PluginSDK(name="t2")
""")
            pid = "sdk_twice"
            host.registry.register(PluginManifest(
                id=pid, name="Twice", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            with pytest.raises(ValueError, match="already active"):
                await host.activate(pid)

    async def test_explicit_activate_still_takes_priority(self) -> None:
        """Plugin with explicit activate() uses it instead of SDK bridge."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "explicit_wins"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK

sdk = PluginSDK(name="explicit-p")

_called_explicit = False

def activate(api):
    global _called_explicit
    _called_explicit = True
""")
            pid = "explicit_wins"
            host.registry.register(PluginManifest(
                id=pid, name="ExplicitWins", version="1.0", source=str(p),
            ))
            await host.activate(pid)

            mod = sys.modules.get("explicit_wins")
            assert mod is not None, "Plugin module should be imported"
            assert mod._called_explicit is True  # type: ignore[union-attr]

    async def test_sdk_plugin_state_transitions(self) -> None:
        """SDK plugin follows the correct state lifecycle."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sdk_lifecycle"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK
sdk = PluginSDK(name="lifecycle-p")
""")
            pid = "sdk_lifecycle"
            host.registry.register(PluginManifest(
                id=pid, name="Lifecycle", version="1.0", source=str(p),
            ))

            # DISCOVERED initially
            m = host.registry.get(pid)
            assert m is not None
            assert m.state == PluginState.DISCOVERED

            # Load → LOADED
            await host.load(pid)
            assert m.state == PluginState.LOADED

            # Activate → ACTIVE
            await host.activate(pid)
            assert m.state == PluginState.ACTIVE

            # Deactivate → INACTIVE
            await host.deactivate(pid)
            assert m.state == PluginState.INACTIVE

    async def test_sdk_plugin_deactivate_cleans_up(self) -> None:
        """SDK plugin deactivate removes loaded modules and APIs."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sdk_cleanup"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK
sdk = PluginSDK(name="cleanup-p")
""")
            pid = "sdk_cleanup"
            host.registry.register(PluginManifest(
                id=pid, name="Cleanup", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            assert pid in host._loaded_modules  # type: ignore[attr-defined]

            await host.deactivate(pid)
            assert pid not in host._loaded_modules  # type: ignore[attr-defined]

    async def test_sdk_plugin_uninstall_removes_entirely(self) -> None:
        """SDK plugin uninstall removes from registry."""
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sdk_uninstall"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK
sdk = PluginSDK(name="uninstall-p")
""")
            pid = "sdk_uninstall"
            host.registry.register(PluginManifest(
                id=pid, name="Uninstall", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            await host.uninstall(pid)
            assert host.registry.get(pid) is None


class TestBuildActivateFuncContextSources:
    """Tests for build_activate_func registering PluginContextSource."""

    def test_registers_context_sources_from_sdk(self) -> None:
        from cscode.plugins import bridge

        sdk = PluginSDK(name="cs-test", version="1.0.0")

        @sdk.context_source(key="plugin/status")
        async def load_status() -> str:
            return "running"

        activate = bridge.build_activate_func([sdk])
        api = PluginAPI()
        activate(api)

        sources = api.get_context_sources()
        assert len(sources) == 1
        assert sources[0].key == "plugin/status"

    def test_registers_multiple_context_sources(self) -> None:
        from cscode.plugins import bridge

        sdk = PluginSDK(name="multi-cs")

        @sdk.context_source(key="plugin/a")
        async def load_a() -> str:
            return "a"

        @sdk.context_source(key="plugin/b")
        async def load_b() -> str:
            return "b"

        activate = bridge.build_activate_func([sdk])
        api = PluginAPI()
        activate(api)

        assert len(api.get_context_sources()) == 2

    def test_no_context_sources_empty_list(self) -> None:
        from cscode.plugins import bridge

        sdk = PluginSDK(name="no-cs")
        activate = bridge.build_activate_func([sdk])
        api = PluginAPI()
        activate(api)

        assert api.get_context_sources() == []

    def test_registers_lifecycle_from_sdk(self) -> None:
        from cscode.plugins import bridge

        sdk = PluginSDK(name="lc-test")

        @sdk.on_activate
        async def activate() -> None:
            pass

        @sdk.on_deactivate
        async def deactivate() -> None:
            pass

        activate_fn = bridge.build_activate_func([sdk])
        api = PluginAPI()
        activate_fn(api)

        hooks = api.get_lifecycle_hooks()
        assert len(hooks) == 1
        assert hooks[0].on_activate is not None
        assert hooks[0].on_deactivate is not None

    def test_no_lifecycle_empty_hooks(self) -> None:
        from cscode.plugins import bridge

        sdk = PluginSDK(name="no-lc")
        activate = bridge.build_activate_func([sdk])
        api = PluginAPI()
        activate(api)

        hooks = api.get_lifecycle_hooks()
        # SDK always creates a PluginLifecycle — verify all fields are None
        assert len(hooks) == 1
        assert hooks[0].on_activate is None
        assert hooks[0].on_deactivate is None
        assert hooks[0].on_session_start is None
        assert hooks[0].on_session_end is None

    def test_registers_both_tools_and_context_sources_and_lifecycle(self) -> None:
        from cscode.plugins import bridge

        sdk = PluginSDK(name="all-in-one")

        class _MyTool:
            name = "mytool"
            description = "My tool"

        sdk.tools["mytool"] = _MyTool

        @sdk.context_source(key="plugin/mytool")
        async def load_mytool() -> str:
            return "ready"

        @sdk.on_activate
        async def on_activate() -> None:
            pass

        activate = bridge.build_activate_func([sdk])
        api = PluginAPI()
        activate(api)

        assert len(api.get_tools()) == 1
        assert len(api.get_context_sources()) == 1
        assert len(api.get_lifecycle_hooks()) == 1


class TestPluginHostSDKLifecycle:
    """SDK lifecycle hooks invoked through PluginHost activate/deactivate."""

    async def test_host_activate_invokes_on_activate(self) -> None:
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sdk_activate_lc"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK

sdk = PluginSDK(name="activate-lc")
_called = False

@sdk.on_activate
async def on_activate():
    global _called
    _called = True
""")
            pid = "activate_lc"
            host.registry.register(PluginManifest(
                id=pid, name="ActivateLC", version="1.0", source=str(p),
            ))
            await host.activate(pid)

            mod = sys.modules.get("sdk_activate_lc")
            assert mod is not None
            assert mod._called is True

    async def test_host_deactivate_invokes_on_deactivate(self) -> None:
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sdk_deactivate_lc"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK

sdk = PluginSDK(name="deactivate-lc")
_called = False

@sdk.on_deactivate
async def on_deactivate():
    global _called
    _called = True
""")
            pid = "deactivate_lc"
            host.registry.register(PluginManifest(
                id=pid, name="DeactivateLC", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            await host.deactivate(pid)

            mod = sys.modules.get("sdk_deactivate_lc")
            assert mod is not None
            assert mod._called is True

    async def test_host_get_context_sources_from_active_sdk_plugin(self) -> None:
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sdk_cs_query"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK

sdk = PluginSDK(name="cs-query")

@sdk.context_source(key="plugin/status")
async def load_status():
    return "running"
""")
            pid = "cs_query"
            host.registry.register(PluginManifest(
                id=pid, name="CSQuery", version="1.0", source=str(p),
            ))
            api = await host.activate(pid)

            sources = api.get_context_sources()
            assert len(sources) == 1
            assert sources[0].key == "plugin/status"

    async def test_host_get_lifecycle_hooks_from_active_sdk_plugin(self) -> None:
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sdk_lc_query"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK

sdk = PluginSDK(name="lc-query")

@sdk.on_activate
async def on_activate():
    pass
""")
            pid = "lc_query"
            host.registry.register(PluginManifest(
                id=pid, name="LCQuery", version="1.0", source=str(p),
            ))
            api = await host.activate(pid)

            hooks = api.get_lifecycle_hooks()
            assert len(hooks) == 1
            assert hooks[0].on_activate is not None

    async def test_emit_session_start_calls_lifecycle_hooks(self) -> None:
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sdk_sess_start"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK

sdk = PluginSDK(name="sess-start")
_called = None

@sdk.on_session_start
async def on_session_start(session_id: str):
    global _called
    _called = session_id
""")
            pid = "sess_start"
            host.registry.register(PluginManifest(
                id=pid, name="SessStart", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            await host.emit_session_start("session-1")

            mod = sys.modules.get("sdk_sess_start")
            assert mod is not None
            assert mod._called == "session-1"

    async def test_emit_session_end_calls_lifecycle_hooks(self) -> None:
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sdk_sess_end"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK

sdk = PluginSDK(name="sess-end")
_called = None

@sdk.on_session_end
async def on_session_end(session_id: str):
    global _called
    _called = session_id
""")
            pid = "sess_end"
            host.registry.register(PluginManifest(
                id=pid, name="SessEnd", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            await host.emit_session_end("session-1")

            mod = sys.modules.get("sdk_sess_end")
            assert mod is not None
            assert mod._called == "session-1"

    async def test_emit_session_start_no_hooks_no_crash(self) -> None:
        host = PluginHost()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sdk_no_hook"
            p.mkdir()
            _write_init(p, """
from cscode.plugins.sdk import PluginSDK
sdk = PluginSDK(name="no-hook")
""")
            pid = "no_hook"
            host.registry.register(PluginManifest(
                id=pid, name="NoHook", version="1.0", source=str(p),
            ))
            await host.activate(pid)
            # Should not raise
            await host.emit_session_start("session-1")
            await host.emit_session_end("session-1")
