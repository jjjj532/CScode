from __future__ import annotations

import pytest
from cscode.core.events import EventBus, Event, ToolExecuteEvent, SessionCreatedEvent


@pytest.mark.asyncio
async def test_subscribe_and_emit() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("tool.execute.before", handler)
    event = ToolExecuteEvent(name="Read", args={})
    await bus.emit("tool.execute.before", event)

    assert len(received) == 1
    assert received[0].type == "tool.execute.before"
    assert received[0].name == "Read"


@pytest.mark.asyncio
async def test_unsubscribe() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("tool.execute.before", handler)
    bus.unsubscribe("tool.execute.before", handler)
    await bus.emit("tool.execute.before", ToolExecuteEvent(name="Read", args={}))

    assert len(received) == 0


@pytest.mark.asyncio
async def test_sync_handler() -> None:
    bus = EventBus()
    received: list[Event] = []

    def sync_handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("session.created", sync_handler)
    await bus.emit("session.created", SessionCreatedEvent(session_id="test-1"))

    assert len(received) == 1


@pytest.mark.asyncio
async def test_multiple_listeners() -> None:
    bus = EventBus()
    received: list[str] = []

    async def h1(event: Event) -> None:
        received.append("h1")

    async def h2(event: Event) -> None:
        received.append("h2")

    bus.subscribe("tool.execute.before", h1)
    bus.subscribe("tool.execute.before", h2)
    await bus.emit("tool.execute.before", ToolExecuteEvent(name="Read", args={}))

    assert received == ["h1", "h2"]


@pytest.mark.asyncio
async def test_cleanup_all_listeners() -> None:
    bus = EventBus()
    bus.subscribe("test", lambda e: None)
    bus.subscribe("test", lambda e: None)
    bus.clear()
    assert bus.listener_count("test") == 0


@pytest.mark.asyncio
async def test_no_listeners_does_not_raise() -> None:
    bus = EventBus()
    await bus.emit("nonexistent", ToolExecuteEvent(name="Read", args={}))
    assert True
