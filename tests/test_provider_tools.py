"""Tests for Provider-defined Tools (llm/provider_tools.py).

Tests verify:
- ProviderTool dataclass structure
- ProviderToolExecutor creation for anthropic and openai
- Tool definition generation
- execute() dispatch
- Unknown provider/tool error handling
"""

from __future__ import annotations

import pytest

from cscode.llm.provider_tools import ProviderTool, ProviderToolExecutor


class TestProviderTool:
    """ProviderTool dataclass structure."""

    def test_minimal(self) -> None:
        tool = ProviderTool(
            name="web_search",
            description="Search the web",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        )
        assert tool.name == "web_search"
        assert tool.description == "Search the web"
        assert tool.input_schema["type"] == "object"
        assert tool.executor is None

    def test_with_executor(self) -> None:
        async def fake_execute(**kwargs: str) -> str:
            return f"result: {kwargs}"

        tool = ProviderTool(
            name="test_tool",
            description="A test tool",
            input_schema={},
            executor=fake_execute,
        )
        assert tool.executor is not None


class TestProviderToolExecutorAnthropic:
    """Anthropic provider tools."""

    @pytest.fixture
    def executor(self) -> ProviderToolExecutor:
        return ProviderToolExecutor.for_anthropic()

    def test_has_web_search(self, executor: ProviderToolExecutor) -> None:
        assert "web_search" in executor.tools
        assert executor.tools["web_search"].name == "web_search"

    def test_has_code_execution(self, executor: ProviderToolExecutor) -> None:
        assert "code_execution" in executor.tools
        assert executor.tools["code_execution"].name == "code_execution"

    def test_get_tool_definitions(self, executor: ProviderToolExecutor) -> None:
        defs = executor.get_tool_definitions()
        assert len(defs) == 2
        names = {d["function"]["name"] for d in defs}
        assert names == {"web_search", "code_execution"}


class TestProviderToolExecutorOpenAI:
    """OpenAI provider tools."""

    @pytest.fixture
    def executor(self) -> ProviderToolExecutor:
        return ProviderToolExecutor.for_openai()

    def test_has_web_search(self, executor: ProviderToolExecutor) -> None:
        assert "web_search" in executor.tools

    def test_has_file_search(self, executor: ProviderToolExecutor) -> None:
        assert "file_search" in executor.tools

    def test_has_code_interpreter(self, executor: ProviderToolExecutor) -> None:
        assert "code_interpreter" in executor.tools

    def test_get_tool_definitions(self, executor: ProviderToolExecutor) -> None:
        defs = executor.get_tool_definitions()
        assert len(defs) == 3

    def test_execute_unknown_tool(self, executor: ProviderToolExecutor) -> None:
        with pytest.raises(ValueError, match="Unknown tool"):
            import asyncio
            asyncio.run(executor.execute("nonexistent_tool", {}))


class TestProviderToolExecutorExecute:
    """Execute dispatch."""

    @pytest.mark.asyncio
    async def test_execute_without_executor_returns_not_implemented(self) -> None:
        executor = ProviderToolExecutor.for_anthropic()
        result = await executor.execute("web_search", {"query": "test"})
        # Should return a not_implemented response when no executor is set
        assert isinstance(result, dict)
        assert result.get("status") == "not_implemented"

    @pytest.mark.asyncio
    async def test_execute_with_custom_executor(self) -> None:
        async def fake_search(query: str) -> str:
            return f"Searched: {query}"

        executor = ProviderToolExecutor(provider_name="test")
        executor.add_tool(
            name="my_tool",
            description="A custom tool",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            executor=fake_search,
        )
        result = await executor.execute("my_tool", {"query": "hello"})
        assert result == "Searched: hello"

    @pytest.mark.asyncio
    async def test_execute_passes_kwargs(self) -> None:
        """Executor must receive arguments as keyword arguments."""
        received: dict = {}

        async def capture(**kwargs: str) -> str:
            received.update(kwargs)
            return "ok"

        executor = ProviderToolExecutor(provider_name="test")
        executor.add_tool("capture", "Captures args", {}, executor=capture)
        await executor.execute("capture", {"a": "1", "b": "2"})
        assert received == {"a": "1", "b": "2"}


class TestProviderMetadata:
    """Provider metadata tests."""

    def test_provider_name(self) -> None:
        executor = ProviderToolExecutor.for_anthropic()
        assert executor.provider_name == "anthropic"

        executor2 = ProviderToolExecutor.for_openai()
        assert executor2.provider_name == "openai"

    def test_empty_executor(self) -> None:
        executor = ProviderToolExecutor(provider_name="custom")
        assert executor.tools == {}
        assert executor.get_tool_definitions() == []
