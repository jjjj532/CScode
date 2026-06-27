from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from cscode.tools2 import Tool, ToolResult, ToolRegistry


@pytest.fixture(scope="function")
def event_loop():
    """Create an instance of the default event loop for each test."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Test tools for contract tests
# ---------------------------------------------------------------------------

class _EchoInput(BaseModel):
    message: str = "hello"


class _EchoOutput(BaseModel):
    echo: str


class _EchoTool(Tool[_EchoInput, _EchoOutput]):
    name = "echo"
    description = "Echoes a message back"
    input_schema = _EchoInput
    output_schema = _EchoOutput

    async def execute(self, input: _EchoInput) -> ToolResult[_EchoOutput]:
        return ToolResult(success=True, data=_EchoOutput(echo=input.message))


@pytest.fixture
def tool() -> Tool[_EchoInput, _EchoOutput]:
    return _EchoTool()


@pytest.fixture
def registry_with_tools() -> ToolRegistry:
    r = ToolRegistry()
    r.register(_EchoTool())
    return r
