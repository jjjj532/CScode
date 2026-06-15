from __future__ import annotations

import pytest

from cscode.core.events import EventBus, ToolExecuteEvent
from cscode.plugins.hooks import PluginHookManager


class TestPluginHookManager:
    @pytest.mark.asyncio
    async def test_register_hook(self) -> None:
        bus = EventBus()
        mgr = PluginHookManager(bus)
        received = []

        async def handler(event):
            received.append(event)

        mgr.register("my_plugin", "tool.execute.before", handler)
        await bus.emit("tool.execute.before", ToolExecuteEvent(name="Read", args={}))

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_unregister_all(self) -> None:
        bus = EventBus()
        mgr = PluginHookManager(bus)

        async def handler(event):
            msg = "should not be called"
            raise RuntimeError(msg)

        mgr.register("p1", "test.event", handler)
        mgr.unregister_all("p1")
        await bus.emit("test.event", ToolExecuteEvent(name="Read", args={}))
        assert True

    @pytest.mark.asyncio
    async def test_multiple_plugins_same_event(self) -> None:
        bus = EventBus()
        mgr = PluginHookManager(bus)
        order = []

        async def h1(event):
            order.append("p1")

        async def h2(event):
            order.append("p2")

        mgr.register("p1", "test.event", h1)
        mgr.register("p2", "test.event", h2)
        await bus.emit("test.event", ToolExecuteEvent(name="Read", args={}))

        assert order == ["p1", "p2"]

    @pytest.mark.asyncio
    async def test_multiple_unregister_all(self) -> None:
        bus = EventBus()
        mgr = PluginHookManager(bus)
        received = []

        async def h1(event):
            received.append("p1")

        async def h2(event):
            received.append("p2")

        mgr.register("p1", "test.event", h1)
        mgr.register("p2", "test.event", h2)
        mgr.unregister_all("p1")
        await bus.emit("test.event", ToolExecuteEvent(name="Read", args={}))

        assert received == ["p2"]
