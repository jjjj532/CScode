from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cscode.core.config import Config
from cscode.core.engine import Agent, AgentOptions
from cscode.core.messages import Message, MessageRole
from cscode.providers.base import LLMResult
from cscode.tools.base import BaseTool, ToolResult, ToolRegistry


class TestEngine:
    @pytest.fixture
    def registry(self) -> ToolRegistry:
        r = ToolRegistry()

        class EchoTool(BaseTool):
            name = "echo"
            description = "Echo text back"
            parameters = {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            }

            async def execute(self, args: dict) -> ToolResult:
                return ToolResult(success=True, data=args.get("text", ""))

        r.register(EchoTool())
        return r

    @pytest.fixture
    def mock_provider(self):
        provider = AsyncMock()
        provider.model = "test-model"
        return provider

    @pytest.fixture
    def agent(self, registry: ToolRegistry, mock_provider) -> Agent:
        return Agent(
            config=Config(api_key="test", model="test-model"),
            provider=mock_provider,
            registry=registry,
            options=AgentOptions(max_tool_rounds=5),
        )

    async def test_simple_response(self, agent: Agent, mock_provider):
        """Agent 返回简单文本回复"""
        mock_provider.complete.return_value = LLMResult(
            content="Hello! How can I help?",
            finish_reason="stop",
        )

        response = await agent.run("Hi")
        assert "Hello! How can I help?" in response

    async def test_tool_call_then_response(self, agent: Agent, mock_provider):
        """Agent 调用工具后返回结果"""
        # 第一次调用：LLM 返回工具调用
        mock_provider.complete.return_value = LLMResult(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "arguments": '{"text": "hello world"}',
                    },
                }
            ],
            finish_reason="tool_calls",
        )

        # 模拟 LLM 第二次调用返回最终回复
        second_result = LLMResult(
            content="The echo said: hello world",
            finish_reason="stop",
        )

        original_complete = mock_provider.complete
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return second_result
            return original_complete.return_value

        mock_provider.complete.side_effect = side_effect

        response = await agent.run("Echo hello")
        assert "hello world" in response

    async def test_tool_error_handling(self, agent: Agent, mock_provider):
        """工具调用出错时 Agent 不崩溃"""
        mock_provider.complete.return_value = LLMResult(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "nonexistent_tool",
                        "arguments": "{}",
                    },
                }
            ],
            finish_reason="tool_calls",
        )

        second_result = LLMResult(
            content="The tool is not available",
            finish_reason="stop",
        )

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return second_result
            return mock_provider.complete.return_value

        mock_provider.complete.side_effect = side_effect

        response = await agent.run("Run unknown tool")
        assert "not available" in response

    async def test_max_tool_rounds(self, agent: Agent, mock_provider):
        """达到最大工具调用轮次后停止"""
        mock_provider.complete.return_value = LLMResult(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "arguments": '{"text": "hi"}',
                    },
                }
            ],
            finish_reason="tool_calls",
        )

        agent.options.max_tool_rounds = 3
        response = await agent.run("Loop")
        assert isinstance(response, str)


class TestRunLoopEvents:
    @pytest.mark.asyncio
    async def test_run_loop_events_emits_correct_events(self):
        """Verify run_loop_events emits step.started, text.ended, and step.ended for direct response."""
        from cscode.core.engine import Agent, AgentOptions
        from cscode.core.messages import Message, MessageRole

        class MockProvider:
            async def complete(self, messages, tools=None):
                return LLMResult(content="Hello!", tool_calls=None)

        config = Config(api_key="test", model="test-model")
        registry = MagicMock()
        registry.to_llm_tools.return_value = []

        agent = Agent(config=config, provider=MockProvider(), registry=registry, options=AgentOptions(max_tool_rounds=5))

        events = []
        async def on_event(e):
            events.append(e)

        messages = [Message(role=MessageRole.USER, content="hi")]
        result = await agent.run_loop_events(messages, on_event=on_event)

        assert result == "Hello!"
        event_types = [e["type"] for e in events]
        assert "step.started" in event_types
        assert "text.ended" in event_types
        assert events[-1]["type"] == "step.ended"

    @pytest.mark.asyncio
    async def test_run_loop_events_tool_call_flow(self):
        """Verify run_loop_events emits tool.called, tool.success, and step.ended with tool_use."""
        from cscode.core.engine import Agent, AgentOptions
        from cscode.core.messages import Message, MessageRole

        call_count = 0

        class MockProvider:
            async def complete(self, messages, tools=None):
                nonlocal call_count
                if call_count == 0:
                    call_count += 1
                    return LLMResult(
                        content="",
                        tool_calls=[{
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "echo", "arguments": '{"text": "hi"}'},
                        }],
                    )
                return LLMResult(content="Done", tool_calls=None)

        config = Config(api_key="test", model="test-model")
        registry = MagicMock()
        registry.to_llm_tools.return_value = []
        registry.execute_tool_call = AsyncMock()
        registry.execute_tool_call.return_value = ToolResult(success=True, data="echoed: hi")

        agent = Agent(config=config, provider=MockProvider(), registry=registry, options=AgentOptions(max_tool_rounds=5))

        events = []
        async def on_event(e):
            events.append(e)

        messages = [Message(role=MessageRole.USER, content="echo hi")]
        result = await agent.run_loop_events(messages, on_event=on_event)

        assert result == "Done"
        event_types = [e["type"] for e in events]
        assert "tool.called" in event_types
        assert "tool.success" in event_types
        assert "tool.failed" not in event_types
        assert events[-1]["type"] == "step.ended"
        tool_use_ended = [e for e in events if e["type"] == "step.ended" and e["data"]["finish_reason"] == "tool_use"]
        assert len(tool_use_ended) == 1
