"""AgentV2 契约测试 — mock LLM + mock tools。

测试策略:
  - Mock LLMClient 替代真实网络调用
  - 使用 conftest 中的 _EchoTool 作为 mock tool
  - 覆盖 text-only、tool call、error 三种路径
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from cscode.app.agent import AgentV2
from cscode.app.factory import create_agent_v2, create_tool_registry
from cscode.core.config import Config
from cscode.llm.client import LLMClient
from cscode.llm.route import Route
from cscode.llm.types import LLMRequest
from cscode.schema.events import (
    Finish,
    LLMEvent,
    Pending,
    TextDelta,
    TextEnded,
    ToolCallEnded,
)
from cscode.schema.ids import ModelID, ToolCallID
from cscode.core.tool_registry import ToolRegistryV2
from cscode.tools2 import Tool, ToolResult

# ─── Mock LLMClient ───────────────────────────────────────────────


class MockLLMClient(LLMClient):
    """Mock LLMClient that yields different event batches per call.

    Each batch in event_batches is consumed once. The first call uses
    batch[0], second call uses batch[1], etc.
    """

    def __init__(self, event_batches: list[list[LLMEvent]]) -> None:
        self._batches = event_batches
        self._call_count = 0
        self._requests: list[LLMRequest] = []
        # Route is required by LLMClient.__init__, create a minimal one
        from cscode.llm.route import Auth, Endpoint, ProtocolID

        super().__init__(
            route=Route(
                id="mock/test",
                protocol=ProtocolID.OPENAI_CHAT,
                endpoint=Endpoint.from_base("https://mock.test"),
                auth=Auth.none(),
                model=ModelID("test-model"),
            )
        )

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def requests(self) -> list[LLMRequest]:
        return list(self._requests)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        idx = self._call_count
        self._call_count += 1
        self._requests.append(request)
        if idx < len(self._batches):
            for event in self._batches[idx]:
                yield event


# ─── Mock Error Tool ──────────────────────────────────────────────


class _FailingInput(BaseModel):
    pass


class _FailingOutput(BaseModel):
    result: str = ""


class _FailingTool(Tool[_FailingInput, _FailingOutput]):
    name = "fail"
    description = "Always fails"
    input_schema = _FailingInput
    output_schema = _FailingOutput

    async def execute(self, input: _FailingInput) -> ToolResult[_FailingOutput]:
        return ToolResult(success=False, error="Intentional failure")


# ─── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def echo_registry() -> ToolRegistryV2:
    """Registry with _EchoTool from conftest."""
    from tests.conftest import _EchoTool

    r = ToolRegistryV2()
    r.register_tool(_EchoTool())
    return r


@pytest.fixture
def text_only_batch() -> list[LLMEvent]:
    return [
        Pending(),
        TextDelta(text="Hello"),
        TextDelta(text=" world"),
        TextEnded(full_text="Hello world"),
        Finish(finish_reason="stop"),
    ]


# ─── Test: run() — text only ──────────────────────────────────────


@pytest.mark.asyncio
async def test_run_text_only(text_only_batch: list[LLMEvent], echo_registry: ToolRegistryV2) -> None:
    """AgentV2.run() should return concatenated text for text-only responses."""
    mock_client = MockLLMClient([text_only_batch])
    agent = AgentV2(llm_client=mock_client, tool_registry=echo_registry)

    result = await agent.run("Say hello")

    assert result == "Hello world"
    assert mock_client.call_count == 1


@pytest.mark.asyncio
async def test_run_text_with_system_prompt(
    text_only_batch: list[LLMEvent], echo_registry: ToolRegistryV2
) -> None:
    """AgentV2.run() should include system prompt in messages."""
    mock_client = MockLLMClient([text_only_batch])
    agent = AgentV2(
        llm_client=mock_client,
        tool_registry=echo_registry,
        system_prompt="You are a helpful assistant.",
    )

    result = await agent.run("Say hello")

    assert result == "Hello world"
    assert len(mock_client.requests) == 1
    req = mock_client.requests[0]
    # Should have system + user messages
    assert any(m.role == "system" for m in req.messages)
    assert any(m.role == "user" for m in req.messages)


# ─── Test: run() — tool call ──────────────────────────────────────


@pytest.mark.asyncio
async def test_run_with_tool_call(echo_registry: ToolRegistryV2) -> None:
    """AgentV2.run() should handle tool calls and return assistant text."""
    batch1: list[LLMEvent] = [
        Pending(),
        TextDelta(text="Checking..."),
        TextEnded(full_text="Checking..."),
        ToolCallEnded(
            tool_call_id=ToolCallID("call_1"),
            name="echo",
            args={"message": "echo me"},
        ),
        Finish(finish_reason="tool_use"),
    ]
    batch2: list[LLMEvent] = [
        Pending(),
        TextDelta(text="Done"),
        TextEnded(full_text="Done"),
        Finish(finish_reason="stop"),
    ]
    mock_client = MockLLMClient([batch1, batch2])
    agent = AgentV2(llm_client=mock_client, tool_registry=echo_registry)

    result = await agent.run("Echo test")

    assert result == "Checking...Done"
    assert mock_client.call_count == 2  # first call + second call after tool


@pytest.mark.asyncio
async def test_run_with_tool_error(echo_registry: ToolRegistryV2) -> None:
    """AgentV2.run() should handle tool failures gracefully."""
    # Register a failing tool
    failing_registry = ToolRegistryV2()
    failing_registry.register_tool(_FailingTool())

    batch1: list[LLMEvent] = [
        Pending(),
        TextDelta(text="Running"),
        TextEnded(full_text="Running"),
        ToolCallEnded(
            tool_call_id=ToolCallID("call_fail"),
            name="fail",
            args={},
        ),
        Finish(finish_reason="tool_use"),
    ]
    batch2: list[LLMEvent] = [
        Pending(),
        TextDelta(text="Error handled"),
        TextEnded(full_text="Error handled"),
        Finish(finish_reason="stop"),
    ]
    mock_client = MockLLMClient([batch1, batch2])
    agent = AgentV2(llm_client=mock_client, tool_registry=failing_registry)

    result = await agent.run("Run failing tool")

    assert mock_client.call_count == 2  # recovered after error
    assert "Error handled" in result


# ─── Test: run() — error path ─────────────────────────────────────


@pytest.mark.asyncio
async def test_run_llm_error(echo_registry: ToolRegistryV2) -> None:
    """AgentV2.run() should return error message on LLM failure."""
    from cscode.schema.errors import LLMError, LLMErrorReason
    from cscode.schema.events import Error as LLMEventError

    batch: list[LLMEvent] = [
        Pending(),
        LLMEventError(
            error=LLMError(
                module="test",
                method="stream",
                reason=LLMErrorReason.PROVIDER_INTERNAL,
                message="Server error (test)",
                retryable=True,
            )
        ),
    ]
    mock_client = MockLLMClient([batch])
    agent = AgentV2(llm_client=mock_client, tool_registry=echo_registry)

    result = await agent.run("Trigger error")

    assert "LLM error" in result
    assert "Server error" in result


# ─── Test: run() — on_event callback ────────────────────────────────


@pytest.mark.asyncio
async def test_run_on_event_callback(
    text_only_batch: list[LLMEvent], echo_registry: ToolRegistryV2
) -> None:
    """AgentV2.run() should invoke on_event callback for each event."""
    mock_client = MockLLMClient([text_only_batch])
    agent = AgentV2(llm_client=mock_client, tool_registry=echo_registry)

    collected: list[str] = []
    result = await agent.run("Say hello", on_event=lambda e: collected.append(e.type))

    assert result == "Hello world"
    assert "pending" in collected
    assert "text-delta" in collected
    assert "text-ended" in collected
    assert "finish" in collected


# ─── Test: run_stream() ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_stream_text_only(
    text_only_batch: list[LLMEvent], echo_registry: ToolRegistryV2
) -> None:
    """run_stream() should yield all events for text-only responses."""
    mock_client = MockLLMClient([text_only_batch])
    agent = AgentV2(llm_client=mock_client, tool_registry=echo_registry)

    events: list[LLMEvent] = []
    async for event in agent.run_stream("Say hello"):
        events.append(event)

    types = [e.type for e in events]
    assert "pending" in types
    assert "text-delta" in types
    assert "text-ended" in types
    assert "finish" in types


@pytest.mark.asyncio
async def test_run_stream_tool_call(echo_registry: ToolRegistryV2) -> None:
    """run_stream() should include tool result events."""
    batch1: list[LLMEvent] = [
        Pending(),
        ToolCallEnded(tool_call_id=ToolCallID("call_1"), name="echo", args={"message": "hi"}),
        Finish(finish_reason="tool_use"),
    ]
    batch2: list[LLMEvent] = [
        Pending(),
        TextDelta(text="Done"),
        TextEnded(full_text="Done"),
        Finish(finish_reason="stop"),
    ]
    mock_client = MockLLMClient([batch1, batch2])
    agent = AgentV2(llm_client=mock_client, tool_registry=echo_registry)

    collected: list[str] = []
    async for event in agent.run_stream("Echo"):
        collected.append(event.type)

    assert "tool-result" in collected, f"Expected tool-result in {collected}"
    assert "text-delta" in collected


# ─── Test: run_stream() — error ────────────────────────────────────


@pytest.mark.asyncio
async def test_run_stream_llm_error(echo_registry: ToolRegistryV2) -> None:
    """run_stream() should yield error event and stop."""
    from cscode.schema.errors import LLMError, LLMErrorReason
    from cscode.schema.events import Error as LLMEventError

    batch: list[LLMEvent] = [
        Pending(),
        LLMEventError(
            error=LLMError(
                module="test",
                method="stream",
                reason=LLMErrorReason.PROVIDER_INTERNAL,
                message="Server error",
            )
        ),
    ]
    mock_client = MockLLMClient([batch])
    agent = AgentV2(llm_client=mock_client, tool_registry=echo_registry)

    collected: list[str] = []
    async for event in agent.run_stream("Trigger error"):
        collected.append(event.type)

    assert "error" in collected


# ─── Test: factory ─────────────────────────────────────────────────


def test_create_tool_registry() -> None:
    """create_tool_registry() should produce a registry with standard tools."""
    registry = create_tool_registry()

    assert len(registry.list_tools()) > 0
    assert "read" in registry.list_tools()
    assert "bash" in registry.list_tools()
    assert "edit" in registry.list_tools()


@pytest.mark.asyncio
async def test_create_agent_v2() -> None:
    """create_agent_v2() should build a configured AgentV2."""
    config = Config(
        provider="openai",
        model="gpt-4o",
        api_key="test-key",
    )
    registry = create_tool_registry()
    agent = create_agent_v2(config, tool_registry=registry)

    assert agent.llm_client is not None
    assert agent.tool_registry is registry
    assert agent._system_prompt is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_create_agent_v2_with_system_prompt() -> None:
    """create_agent_v2() should pass system_prompt from config."""
    config = Config(
        provider="openai",
        model="gpt-4o",
        api_key="test-key",
        system_prompt="Custom prompt",
    )
    registry = create_tool_registry()
    agent = create_agent_v2(config, tool_registry=registry)

    assert agent._system_prompt == "Custom prompt"  # noqa: SLF001


# ─── Test: run() — empty input ─────────────────────────────────────


@pytest.mark.asyncio
async def test_run_empty_input(echo_registry: ToolRegistryV2) -> None:
    """AgentV2.run() should handle empty user input."""
    batch: list[LLMEvent] = [
        Pending(),
        TextEnded(full_text=""),
        Finish(finish_reason="stop"),
    ]
    mock_client = MockLLMClient([batch])
    agent = AgentV2(llm_client=mock_client, tool_registry=echo_registry)

    result = await agent.run("")
    assert result == ""


# ─── Test: run() — max tool rounds ─────────────────────────────────


@pytest.mark.asyncio
async def test_run_max_tool_rounds(echo_registry: ToolRegistryV2) -> None:
    """AgentV2.run() should stop after max_tool_rounds."""
    batch: list[LLMEvent] = [
        Pending(),
        ToolCallEnded(tool_call_id=ToolCallID("call_1"), name="echo", args={"message": "x"}),
        Finish(finish_reason="tool_use"),
    ]
    mock_client = MockLLMClient([batch, batch])
    agent = AgentV2(llm_client=mock_client, tool_registry=echo_registry, max_tool_rounds=2)

    await agent.run("Loop test")

    # Should have called LLM 3 times (initial + 2 rounds)
    assert mock_client.call_count <= 3
