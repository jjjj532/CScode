"""Tests for HookPoint, HookRegistry, and existing PluginHookManager."""

from __future__ import annotations

import pytest

from cscode.core.events import Event, EventBus, ToolExecuteEvent
from cscode.core.plugin.hooks import HookPoint, HookRegistry
from cscode.plugins.hooks import PluginHookManager


class TestHookPoint:
    def test_values(self) -> None:
        assert HookPoint.SESSION_START.value == "session.start"
        assert HookPoint.TOOL_CALL.value == "tool.call"
        assert HookPoint.MESSAGE.value == "message"
        assert HookPoint.SESSION_END.value == "session.end"

    def test_members(self) -> None:
        assert set(HookPoint) == {
            HookPoint.SESSION_START,
            HookPoint.TOOL_CALL,
            HookPoint.MESSAGE,
            HookPoint.SESSION_END,
        }


class TestHookRegistry:
    @pytest.mark.asyncio
    async def test_register_and_trigger(self) -> None:
        bus = EventBus()
        registry = HookRegistry(bus)
        results: list[str] = []

        async def handler(event: object) -> None:
            results.append("handled")

        registry.register(HookPoint.MESSAGE, handler)
        await bus.emit(HookPoint.MESSAGE.value, Event(type=HookPoint.MESSAGE.value))

        assert results == ["handled"]

    @pytest.mark.asyncio
    async def test_multiple_handlers(self) -> None:
        bus = EventBus()
        registry = HookRegistry(bus)
        results: list[str] = []

        async def h1(event: object) -> None:
            results.append("h1")

        async def h2(event: object) -> None:
            results.append("h2")

        registry.register(HookPoint.TOOL_CALL, h1)
        registry.register(HookPoint.TOOL_CALL, h2)
        await bus.emit(HookPoint.TOOL_CALL.value, Event(type=HookPoint.TOOL_CALL.value))

        assert results == ["h1", "h2"]

    @pytest.mark.asyncio
    async def test_no_handlers_no_error(self) -> None:
        bus = EventBus()
        await bus.emit(HookPoint.SESSION_START.value, Event(type=HookPoint.SESSION_START.value))

    @pytest.mark.asyncio
    async def test_unregister(self) -> None:
        bus = EventBus()
        registry = HookRegistry(bus)
        results: list[str] = []

        async def handler(event: object) -> None:
            results.append("called")

        registry.register(HookPoint.MESSAGE, handler)
        registry.unregister(HookPoint.MESSAGE, handler)
        await bus.emit(HookPoint.MESSAGE.value, Event(type=HookPoint.MESSAGE.value))

        assert results == []

    @pytest.mark.asyncio
    async def test_unregister_unknown_handler_no_error(self) -> None:
        bus = EventBus()
        registry = HookRegistry(bus)

        async def handler(event: object) -> None:
            pass

        registry.unregister(HookPoint.MESSAGE, handler)

    @pytest.mark.asyncio
    async def test_unregister_from_unknown_hook_no_error(self) -> None:
        bus = EventBus()
        registry = HookRegistry(bus)

        async def handler(event: object) -> None:
            pass

        registry.unregister(HookPoint.TOOL_CALL, handler)


class TestPluginHookManager:
    @pytest.mark.asyncio
    async def test_register_hook(self) -> None:
        bus = EventBus()
        mgr = PluginHookManager(bus)
        received = []

        async def handler(event: object) -> None:
            received.append(event)

        mgr.register("my_plugin", "tool.execute.before", handler)
        await bus.emit("tool.execute.before", ToolExecuteEvent(name="Read", args={}))

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_unregister_all(self) -> None:
        bus = EventBus()
        mgr = PluginHookManager(bus)

        async def handler(event: object) -> None:
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

        async def h1(event: object) -> None:
            order.append("p1")

        async def h2(event: object) -> None:
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

        async def h1(event: object) -> None:
            received.append("p1")

        async def h2(event: object) -> None:
            received.append("p2")

        mgr.register("p1", "test.event", h1)
        mgr.register("p2", "test.event", h2)
        mgr.unregister_all("p1")
        await bus.emit("test.event", ToolExecuteEvent(name="Read", args={}))

        assert received == ["p2"]
