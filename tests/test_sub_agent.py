from collections.abc import AsyncIterator

import pytest

from cscode.core.config import Config
from cscode.core.events import EventBus
from cscode.core.messages import Message
from cscode.core.sub_agent import SubAgentOrchestrator
from cscode.providers.base import LLMProvider, LLMResult
from cscode.tools.base import ToolRegistry, BaseTool, ToolResult


class FakeProvider(LLMProvider):
    def __init__(self):
        super().__init__(Config())

    @property
    def model(self) -> str:
        return "fake-model"

    async def complete(self, messages, tools=None) -> LLMResult:
        return LLMResult(content="fake")

    def stream(self, messages, tools=None) -> AsyncIterator[str]:
        yield "fake"

    def build_messages(self, messages) -> list[dict]:
        return [{"role": m.role.value, "content": m.content} for m in messages]


class FakeReadTool(BaseTool):
    name = "Read"
    description = "Read file contents"
    requires_permission = False
    parameters = {
        "type": "object",
        "properties": {
            "filePath": {"type": "string"},
        },
        "required": ["filePath"],
    }
    async def execute(self, args):
        path = args.get("filePath", "")
        return ToolResult(success=True, data=f"Content of {path}")


class FakeBashTool(BaseTool):
    name = "Bash"
    description = "Execute shell command"
    requires_permission = True
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
        },
        "required": ["command"],
    }
    async def execute(self, args):
        cmd = args.get("command", "")
        return ToolResult(success=True, data=f"Output: {cmd}")


class FakeFailingTool(BaseTool):
    name = "Fail"
    description = "Always fails"
    requires_permission = False
    parameters = {"type": "object", "properties": {}}
    async def execute(self, args):
        return ToolResult(success=False, data="", error="Intentional failure")


@pytest.fixture
def orchestrator():
    event_bus = EventBus()
    provider = FakeProvider()
    registry = ToolRegistry()
    registry.register(FakeReadTool())
    registry.register(FakeBashTool())
    registry.register(FakeFailingTool())
    from cscode.core.permissions import PermissionService
    permission_service = PermissionService(event_bus)
    return SubAgentOrchestrator(event_bus, provider, registry, permission_service)


@pytest.mark.asyncio
async def test_no_mentions_returns_input(orchestrator):
    result = await orchestrator.process_mentions("Hello, how are you?")
    assert result == "Hello, how are you?"


@pytest.mark.asyncio
async def test_simple_tool_mention(orchestrator):
    result = await orchestrator.process_mentions("Read @Read filePath=test.txt")
    assert "Content of test.txt" in result
    assert "Read @Read" not in result  # mention should be replaced


@pytest.mark.asyncio
async def test_tool_mention_with_quoted_value(orchestrator):
    result = await orchestrator.process_mentions('Run @Bash command="echo hello"')
    assert "Output: echo hello" in result
    assert "@Bash" not in result


@pytest.mark.asyncio
async def test_unknown_tool_mention_left_as_is(orchestrator):
    result = await orchestrator.process_mentions("Check @NonexistentTool key=val")
    assert "@NonexistentTool" in result


@pytest.mark.asyncio
async def test_multiple_tool_mentions(orchestrator):
    result = await orchestrator.process_mentions(
        'Read file @Read filePath=a.txt and run @Bash command="ls"'
    )
    assert "Content of a.txt" in result
    assert "Output: ls" in result
    assert "@Read" not in result
    assert "@Bash" not in result


@pytest.mark.asyncio
async def test_tool_mention_error_handling(orchestrator):
    result = await orchestrator.process_mentions("Run @Fail")
    assert "Error" in result or "Intentional failure" in result
