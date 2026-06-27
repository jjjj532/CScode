"""Contract tests for LLM layer (llm/service.py, llm/adapters/legacy.py).

Tests verify:
- LLMResponse and ToolExecution dataclass contracts
- LLMService ABC interface (generate/stream signatures)
- LegacyProviderAdapter construction and message conversion
- Tool loop basic behavior with MockProvider
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic import BaseModel

from cscode.llm import LLMResponse, LLMService, LegacyProviderAdapter, ToolExecution
from cscode.tools2 import Tool, ToolResult, ToolRegistry
from cscode.providers.base import LLMProvider, LLMResult
from cscode.schema.ids import ModelID, ToolCallID
from cscode.schema.messages import Message, MessageRole, TextPart, ToolCallPart
from cscode.schema.options import GenerationOptions
from cscode.tools2 import Tool, ToolResult, ToolRegistry

# ─── Mock Provider ────────────────────────────────────────────────


class _MockProvider(LLMProvider):
    """Mock provider that returns canned responses for testing."""

    def __init__(self) -> None:
        super().__init__(None)  # type: ignore[arg-type]
        self._model = "mock-model"
        self.responses: list[LLMResult] = []
        self.call_count = 0

    @property
    def model(self) -> str:
        return self._model

    def add_response(
        self,
        content: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
        finish_reason: str = "stop",
    ) -> None:
        self.responses.append(LLMResult(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
        ))

    async def complete(
        self,
        messages: list[Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        if self.call_count >= len(self.responses):
            msg = f"MockProvider: no more responses (call #{self.call_count})"
            raise RuntimeError(msg)
        result = self.responses[self.call_count]
        self.call_count += 1
        return result

    def stream(
        self,
        messages: list[Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        raise NotImplementedError

    def build_messages(self, messages: list[Any]) -> list[dict[str, Any]]:
        return []


# ─── Test Tools ───────────────────────────────────────────────────


class _ConcatInput(BaseModel):
    a: str = ""
    b: str = ""


class _ConcatOutput(BaseModel):
    result: str


class _ConcatTool(Tool[_ConcatInput, _ConcatOutput]):
    name = "concat"
    description = "Concatenates two strings"
    input_schema = _ConcatInput
    output_schema = _ConcatOutput

    async def execute(self, input: _ConcatInput) -> ToolResult[_ConcatOutput]:
        return ToolResult(success=True, data=_ConcatOutput(result=input.a + input.b))


# ─── Contract: LLMResponse ────────────────────────────────────────


class TestLLMResponseContract:
    def test_default_construction(self) -> None:
        resp = LLMResponse(content="hello")
        assert resp.content == "hello"
        assert resp.tool_executions == ()
        assert resp.usage is None
        assert resp.model == ""
        assert resp.finish_reason == ""

    def test_full_construction(self) -> None:
        execs = (ToolExecution(name="read", tool_call_id="c1", input={}, output="data", success=True, duration_ms=10.0),)
        resp = LLMResponse(
            content="done",
            tool_executions=execs,
            usage={"prompt_tokens": 10, "completion_tokens": 20},
            model="gpt-4o",
            finish_reason="stop",
        )
        assert resp.content == "done"
        assert len(resp.tool_executions) == 1
        assert resp.tool_executions[0].name == "read"
        assert resp.usage == {"prompt_tokens": 10, "completion_tokens": 20}
        assert resp.model == "gpt-4o"
        assert resp.finish_reason == "stop"

    def test_is_frozen(self) -> None:
        resp = LLMResponse(content="hello")
        with pytest.raises(AttributeError):
            resp.content = "world"  # type: ignore[misc]


class TestToolExecutionContract:
    def test_default_output_is_str(self) -> None:
        exec_ = ToolExecution(name="echo", tool_call_id="c1", input={"msg": "hi"}, output="echo: hi", success=True, duration_ms=5.0)
        assert exec_.output == "echo: hi"

    def test_is_frozen(self) -> None:
        exec_ = ToolExecution(name="echo", tool_call_id="c1", input={}, output="", success=True, duration_ms=1.0)
        with pytest.raises(AttributeError):
            exec_.output = "changed"  # type: ignore[misc]


# ─── Contract: LLMService ABC ─────────────────────────────────────


class TestLLMServiceContract:
    """Verify LLMService ABC has the expected abstract methods."""

    def test_abc_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            LLMService()  # type: ignore[abstract]

    def test_subclass_must_implement_generate(self) -> None:
        class Incomplete(LLMService):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_subclass_can_implement(self) -> None:
        class MinimalService(LLMService):
            async def generate(self, model, messages, **kwargs):
                return LLMResponse(content="ok")

            async def stream(self, model, messages, **kwargs):  # type: ignore[override]
                from collections.abc import AsyncIterator
                if False:
                    yield  # type: ignore[unreachable]

        svc = MinimalService()
        assert isinstance(svc, LLMService)

    def test_generate_signature(self) -> None:
        """Verify generate has all expected keyword parameters."""
        import inspect
        sig = inspect.signature(LLMService.generate)
        params = sig.parameters
        required = {"model", "messages"}
        optional = {"tools", "tool_choice", "system", "options", "max_tool_rounds"}
        assert required.issubset(params.keys())
        assert optional.issubset(params.keys())
        # tools should be optional
        assert params["tools"].default is None
        assert params["system"].default is None


# ─── LegacyProviderAdapter: Construction ──────────────────────────


class TestLegacyAdapterContract:
    def test_construct_with_provider_only(self) -> None:
        provider = _MockProvider()
        adapter = LegacyProviderAdapter(provider)
        assert isinstance(adapter, LLMService)

    def test_construct_with_registry(self) -> None:
        provider = _MockProvider()
        registry = ToolRegistry()
        adapter = LegacyProviderAdapter(provider, registry)
        assert isinstance(adapter, LLMService)

    async def test_generate_returns_llm_response(self) -> None:
        provider = _MockProvider()
        provider.add_response(content="Hello world")
        adapter = LegacyProviderAdapter(provider)
        msg = Message(role=MessageRole.USER, parts=(TextPart(text="Hi"),))

        resp = await adapter.generate(model=ModelID("mock"), messages=[msg])

        assert isinstance(resp, LLMResponse)
        assert resp.content == "Hello world"
        assert resp.tool_executions == ()

    async def test_generate_with_tool_call(self) -> None:
        """Generate returns tool executions when LLM calls a tool."""
        provider = _MockProvider()
        # Round 1: LLM calls concat tool
        provider.add_response(
            content="Let me concat that",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "concat",
                    "arguments": '{"a": "hello ", "b": "world"}',
                },
            }],
            finish_reason="tool_use",
        )
        # Round 2: LLM responds with final text
        provider.add_response(content="Result: hello world", finish_reason="stop")

        adapter = LegacyProviderAdapter(provider)
        msg = Message(role=MessageRole.USER, parts=(TextPart(text="concat hello and world"),))

        resp = await adapter.generate(
            model=ModelID("mock"),
            messages=[msg],
            tools=[_ConcatTool()],
        )

        # Verify final response
        assert resp.content == "Let me concat thatResult: hello world"
        assert len(resp.tool_executions) == 1
        exec_ = resp.tool_executions[0]
        assert exec_.name == "concat"
        assert exec_.input == {"a": "hello ", "b": "world"}
        assert exec_.success is True
        assert exec_.output is not None
        assert exec_.duration_ms >= 0

    async def test_generate_tool_unknown(self) -> None:
        """Unknown tool is recorded as failure, doesn't crash the loop."""
        provider = _MockProvider()
        provider.add_response(
            content="Calling unknown tool",
            tool_calls=[{
                "id": "call_bad",
                "type": "function",
                "function": {"name": "nonexistent", "arguments": "{}"},
            }],
            finish_reason="tool_use",
        )
        provider.add_response(content="Done", finish_reason="stop")

        adapter = LegacyProviderAdapter(provider)
        msg = Message(role=MessageRole.USER, parts=(TextPart(text="do it"),))

        resp = await adapter.generate(model=ModelID("mock"), messages=[msg])

        assert len(resp.tool_executions) == 1
        assert resp.tool_executions[0].success is False
        assert "Unknown tool" in resp.tool_executions[0].output

    async def test_generate_stops_at_max_rounds(self) -> None:
        """Generate stops when max_tool_rounds is reached."""
        provider = _MockProvider()

        # Add many tool-call responses
        for i in range(5):
            provider.add_response(
                content=f"Round {i}",
                tool_calls=[{
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {"name": "concat", "arguments": '{"a": "x", "b": "y"}'},
                }],
                finish_reason="tool_use",
            )

        # Add one final response
        provider.add_response(content="Final", finish_reason="stop")

        adapter = LegacyProviderAdapter(provider)
        msg = Message(role=MessageRole.USER, parts=(TextPart(text="go"),))

        resp = await adapter.generate(
            model=ModelID("mock"),
            messages=[msg],
            tools=[_ConcatTool()],
            max_tool_rounds=2,
        )

        # Should have stopped at round 2 (max_tool_rounds=2)
        assert resp.finish_reason == "max_rounds"
        assert len(resp.tool_executions) == 2
