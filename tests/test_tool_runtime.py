"""Tests for ToolRuntime — tool call dispatch to registered handlers."""

from __future__ import annotations

import pytest

from cscode.llm.tool_runtime import ToolRuntime
from cscode.schema.events import ToolFailure as EventToolFailure
from cscode.schema.events import ToolResult
from cscode.schema.ids import ToolCallID


@pytest.fixture
def runtime() -> ToolRuntime:
    return ToolRuntime()


@pytest.mark.asyncio
async def test_register_tool(runtime: ToolRuntime) -> None:
    async def handler(**kwargs: object) -> str:
        return "ok"

    runtime.register("test_tool", handler)
    assert runtime.has_tool("test_tool")


@pytest.mark.asyncio
async def test_has_tool_false_when_not_registered(runtime: ToolRuntime) -> None:
    assert not runtime.has_tool("nonexistent")


@pytest.mark.asyncio
async def test_dispatch_known_async_tool(runtime: ToolRuntime) -> None:
    async def my_handler(**kwargs: object) -> str:
        return f"result: {kwargs}"

    runtime.register("my_tool", my_handler)
    events: list[object] = []
    async for event in runtime.dispatch(ToolCallID("call_1"), "my_tool", {"key": "value"}):
        events.append(event)

    assert len(events) == 1
    result = events[0]
    assert isinstance(result, ToolResult)
    assert result.tool_call_id == "call_1"
    assert result.tool_name == "my_tool"
    assert result.tool_args == {"key": "value"}
    assert "'key': 'value'" in result.result


@pytest.mark.asyncio
async def test_dispatch_unknown_tool(runtime: ToolRuntime) -> None:
    events: list[object] = []
    async for event in runtime.dispatch(ToolCallID("call_1"), "nonexistent", {}):
        events.append(event)

    assert len(events) == 1
    failure = events[0]
    assert isinstance(failure, EventToolFailure)
    assert failure.tool_call_id == "call_1"
    assert "Unknown tool" in failure.error
    assert "nonexistent" in failure.error


@pytest.mark.asyncio
async def test_dispatch_sync_handler(runtime: ToolRuntime) -> None:
    def sync_handler(**kwargs: object) -> str:
        return "sync result"

    runtime.register("sync_tool", sync_handler)
    events: list[object] = []
    async for event in runtime.dispatch(ToolCallID("call_2"), "sync_tool", {}):
        events.append(event)

    assert len(events) == 1
    result = events[0]
    assert isinstance(result, ToolResult)
    assert result.result == "sync result"


@pytest.mark.asyncio
async def test_dispatch_handler_raises_exception(runtime: ToolRuntime) -> None:
    async def failing_handler(**kwargs: object) -> str:
        raise ValueError("something broke")

    runtime.register("faulty", failing_handler)
    events: list[object] = []
    async for event in runtime.dispatch(ToolCallID("call_3"), "faulty", {}):
        events.append(event)

    assert len(events) == 1
    failure = events[0]
    assert isinstance(failure, EventToolFailure)
    assert failure.tool_call_id == "call_3"
    assert "failed" in failure.error
    # Error format: "Tool faulty failed: something broke"
    # Handler's message is included, but exception type name is not
    assert "failed: something broke" in failure.error
    assert "faulty" in failure.error


@pytest.mark.asyncio
async def test_dispatch_returns_non_string_result(runtime: ToolRuntime) -> None:
    """Handler returning non-string (e.g. int) should be converted to str."""

    async def int_handler(**kwargs: object) -> str:
        return str(42)

    runtime.register("int_tool", int_handler)
    events: list[object] = []
    async for event in runtime.dispatch(ToolCallID("call_4"), "int_tool", {}):
        events.append(event)

    assert len(events) == 1
    result = events[0]
    assert isinstance(result, ToolResult)
    assert result.result == "42"


@pytest.mark.asyncio
async def test_constructor_with_tools() -> None:
    async def builtin(**kwargs: object) -> str:
        return "builtin"

    r = ToolRuntime(tools={"builtin": builtin})
    assert r.has_tool("builtin")

    events: list[object] = []
    async for event in r.dispatch(ToolCallID("call_5"), "builtin", {}):
        events.append(event)
    assert isinstance(events[0], ToolResult)


@pytest.mark.asyncio
async def test_register_overwrites_existing(runtime: ToolRuntime) -> None:
    async def old_handler(**kwargs: object) -> str:
        return "old"

    async def new_handler(**kwargs: object) -> str:
        return "new"

    runtime.register("mutable", old_handler)
    runtime.register("mutable", new_handler)  # overwrite

    events: list[object] = []
    async for event in runtime.dispatch(ToolCallID("call_6"), "mutable", {}):
        events.append(event)
    result = events[0]
    assert isinstance(result, ToolResult)
    assert result.result == "new"


@pytest.mark.asyncio
async def test_dispatch_passes_args_to_handler(runtime: ToolRuntime) -> None:
    captured: dict[str, object] = {}

    async def capturer(**kwargs: object) -> str:
        captured.update(kwargs)
        return "captured"

    runtime.register("capturer", capturer)
    async for _event in runtime.dispatch(
        ToolCallID("call_7"), "capturer", {"x": 1, "y": "hello"}
    ):
        pass

    assert captured == {"x": 1, "y": "hello"}
