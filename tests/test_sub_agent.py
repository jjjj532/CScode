from __future__ import annotations

import pytest
from pydantic import BaseModel

from cscode.core.sub_agent import SubAgentOrchestrator
from cscode.core.tool_registry import ToolRegistryV2
from cscode.schema.messages import Message, MessageRole, TextPart
from cscode.tools2.base import Tool, ToolResult

# ─── Test tools ─────────────────────────────────────────────────────


class EchoInput(BaseModel):
    msg: str


class EchoOutput(BaseModel):
    echoed: str


class EchoTool(Tool[EchoInput, EchoOutput]):
    name = "echo"
    description = "Echo a message back"
    input_schema = EchoInput
    output_schema = EchoOutput

    async def execute(self, input: EchoInput) -> ToolResult[EchoOutput]:
        return ToolResult(success=True, data=EchoOutput(echoed=input.msg))


class FailInput(BaseModel):
    pass


class FailOutput(BaseModel):
    pass


class FailTool(Tool[FailInput, FailOutput]):
    name = "fail"
    description = "Always fails"
    input_schema = FailInput
    output_schema = FailOutput

    async def execute(self, input: FailInput) -> ToolResult[FailOutput]:
        return ToolResult(success=False, error="Intentional failure")


# ─── Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def registry() -> ToolRegistryV2:
    reg = ToolRegistryV2()
    reg.register_tool(EchoTool())
    reg.register_tool(FailTool())
    return reg


@pytest.fixture
def sub_agent(registry: ToolRegistryV2) -> SubAgentOrchestrator:
    return SubAgentOrchestrator(registry)


# ─── process_mentions tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_mention(sub_agent: SubAgentOrchestrator) -> None:
    result = await sub_agent.process_mentions("Hello, how are you?")
    assert result == "Hello, how are you?"


@pytest.mark.asyncio
async def test_simple_echo(sub_agent: SubAgentOrchestrator) -> None:
    result = await sub_agent.process_mentions('@tool:echo msg=hello')
    assert result == "[Tool echo result: echoed='hello']"


@pytest.mark.asyncio
async def test_quoted_argument(sub_agent: SubAgentOrchestrator) -> None:
    result = await sub_agent.process_mentions('@tool:echo msg="hello world"')
    assert result == "[Tool echo result: echoed='hello world']"


@pytest.mark.asyncio
async def test_mention_with_surrounding_text(sub_agent: SubAgentOrchestrator) -> None:
    result = await sub_agent.process_mentions(
        'Read @tool:echo msg=foo and summarize'
    )
    assert "[Tool echo result: echoed='foo']" in result


@pytest.mark.asyncio
async def test_multiple_mentions(sub_agent: SubAgentOrchestrator) -> None:
    result = await sub_agent.process_mentions(
        '@tool:echo msg=first and @tool:echo msg=second'
    )
    assert "echoed='first'" in result
    assert "echoed='second'" in result


@pytest.mark.asyncio
async def test_unknown_tool(sub_agent: SubAgentOrchestrator) -> None:
    result = await sub_agent.process_mentions('@tool:nonexistent foo=bar')
    assert "error" in result
    assert "nonexistent" in result


@pytest.mark.asyncio
async def test_tool_failure(sub_agent: SubAgentOrchestrator) -> None:
    result = await sub_agent.process_mentions('@tool:fail')
    assert "error" in result
    assert "Intentional failure" in result


# ─── process_messages tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_messages_user_text(sub_agent: SubAgentOrchestrator) -> None:
    messages = [
        Message(role=MessageRole.USER, parts=(TextPart(text='@tool:echo msg=hi'),)),
    ]
    result = await sub_agent.process_messages(messages)
    assert len(result) == 1
    text = result[0].content
    assert "[Tool echo result:" in text
    assert "echoed='hi'" in text


@pytest.mark.asyncio
async def test_process_messages_assistant_untouched(sub_agent: SubAgentOrchestrator) -> None:
    messages = [
        Message(role=MessageRole.ASSISTANT, parts=(TextPart(text='@tool:echo msg=hi'),)),
    ]
    result = await sub_agent.process_messages(messages)
    assert result[0].content == '@tool:echo msg=hi'


@pytest.mark.asyncio
async def test_process_messages_system_untouched(sub_agent: SubAgentOrchestrator) -> None:
    messages = [
        Message(role=MessageRole.SYSTEM, parts=(TextPart(text='@tool:echo msg=hi'),)),
    ]
    result = await sub_agent.process_messages(messages)
    assert result[0].content == '@tool:echo msg=hi'


@pytest.mark.asyncio
async def test_process_messages_no_mentions(sub_agent: SubAgentOrchestrator) -> None:
    messages = [
        Message(role=MessageRole.USER, parts=(TextPart(text='plain text'),)),
    ]
    result = await sub_agent.process_messages(messages)
    assert result[0].content == 'plain text'
