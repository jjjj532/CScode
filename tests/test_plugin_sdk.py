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
