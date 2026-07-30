from __future__ import annotations

import pytest

from cscode.core.events import EventBus, ToolExecuteEvent
from cscode.plugins.hooks import PluginHookManager
from cscode.plugins.sdk import PluginSDK


class TestPluginSDK:
    def test_create_sdk(self) -> None:
        sdk = PluginSDK(name="test-plugin", version="1.0.0")
        assert sdk.name == "test-plugin"
        assert sdk.version == "1.0.0"

    def test_register_tool(self) -> None:
        sdk = PluginSDK(name="test-plugin", version="1.0.0")

        @sdk.tool(name="custom_tool", description="A custom tool")
        class CustomTool:
            async def execute(self, args):
                return {"success": True, "data": "done"}

        assert "custom_tool" in sdk.tools

    def test_register_tool_default_name(self) -> None:
        sdk = PluginSDK(name="test-plugin", version="1.0.0")

        @sdk.tool()
        class MyTool:
            async def execute(self, args):
                return {"success": True}

        assert "mytool" in sdk.tools

    def test_register_hook_decorator(self) -> None:
        sdk = PluginSDK(name="hook-plugin", version="1.0.0")

        @sdk.on("session.created")
        async def handle_session(event):
            pass

        assert len(sdk._hook_handlers) == 1
        assert sdk._hook_handlers[0][0] == "session.created"

    @pytest.mark.asyncio
    async def test_register_hooks_to_manager(self) -> None:
        bus = EventBus()
        mgr = PluginHookManager(bus)
        sdk = PluginSDK(name="hook-plugin", version="1.0.0")
        received = []

        @sdk.on("tool.execute.before")
        async def handler(event):
            received.append(event)

        sdk.register_hooks(mgr)
        await bus.emit("tool.execute.before", ToolExecuteEvent(name="Read", args={}))

        assert len(received) == 1

    def test_to_manifest(self) -> None:
        sdk = PluginSDK(name="my-plugin", version="1.0.0", description="A plugin")

        @sdk.tool(name="hello", description="Hello")
        class HelloTool:
            async def execute(self, args):
                return {"success": True}

        @sdk.on("session.created")
        async def handler(event):
            pass

        manifest = sdk.to_manifest()
        assert manifest.name == "my-plugin"
        assert manifest.version == "1.0.0"
        assert "hello" in manifest.tools
        assert "session.created" in manifest.hooks


class TestPluginSDKContextSources:
    @pytest.mark.asyncio
    async def test_context_source_decorator(self) -> None:
        sdk = PluginSDK(name="cs-plugin", version="1.0.0")

        @sdk.context_source(key="plugin/my-feature")
        async def load_my_feature() -> str:
            return "enabled"

        assert len(sdk._context_sources) == 1
        src = sdk._context_sources[0]
        assert src.key == "plugin/my-feature"
        assert await src.load() == "enabled"

    @pytest.mark.asyncio
    async def test_context_source_custom_renderers(self) -> None:
        sdk = PluginSDK(name="cs-plugin", version="1.0.0")

        @sdk.context_source(
            key="plugin/status",
            baseline=lambda v: f"Status: {v}",
            update=lambda old, new: f"Status changed: {old} -> {new}",
        )
        async def load_status() -> str:
            return "running"

        src = sdk._context_sources[0]
        assert src.key == "plugin/status"
        assert src.baseline("running") == "Status: running"
        assert src.update("idle", "running") == "Status changed: idle -> running"

    def test_context_source_multiple(self) -> None:
        sdk = PluginSDK(name="multi", version="1.0.0")

        @sdk.context_source(key="plugin/a")
        async def load_a() -> str:
            return "a"

        @sdk.context_source(key="plugin/b")
        async def load_b() -> str:
            return "b"

        assert len(sdk._context_sources) == 2
        assert sdk._context_sources[0].key == "plugin/a"
        assert sdk._context_sources[1].key == "plugin/b"


class TestPluginSDKLifecycle:
    def test_lifecycle_default(self) -> None:
        sdk = PluginSDK(name="lc-plugin", version="1.0.0")
        lc = sdk._lifecycle
        assert lc.on_activate is None
        assert lc.on_deactivate is None
        assert lc.on_session_start is None
        assert lc.on_session_end is None

    def test_on_activate_decorator(self) -> None:
        sdk = PluginSDK(name="lc-plugin", version="1.0.0")

        @sdk.on_activate
        async def activate() -> None:
            pass

        assert sdk._lifecycle.on_activate is not None

    def test_on_deactivate_decorator(self) -> None:
        sdk = PluginSDK(name="lc-plugin", version="1.0.0")

        @sdk.on_deactivate
        async def deactivate() -> None:
            pass

        assert sdk._lifecycle.on_deactivate is not None

    def test_on_session_start_decorator(self) -> None:
        sdk = PluginSDK(name="lc-plugin", version="1.0.0")

        @sdk.on_session_start
        async def on_start(session_id: str) -> None:
            pass

        assert sdk._lifecycle.on_session_start is not None

    def test_on_session_end_decorator(self) -> None:
        sdk = PluginSDK(name="lc-plugin", version="1.0.0")

        @sdk.on_session_end
        async def on_end(session_id: str) -> None:
            pass

        assert sdk._lifecycle.on_session_end is not None

    def test_all_lifecycle_hooks(self) -> None:
        sdk = PluginSDK(name="all-hooks", version="1.0.0")

        @sdk.on_activate
        async def activate() -> None:
            pass

        @sdk.on_deactivate
        async def deactivate() -> None:
            pass

        @sdk.on_session_start
        async def on_start(sid: str) -> None:
            pass

        @sdk.on_session_end
        async def on_end(sid: str) -> None:
            pass

        handlers = sdk._lifecycle.get_handlers()
        events = [h[0] for h in handlers]
        assert "activate" in events
        assert "deactivate" in events
        assert "session_start" in events
        assert "session_end" in events
