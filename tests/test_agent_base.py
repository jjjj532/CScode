"""Tests for BaseAgent, BuildAgent, and the agent mode hierarchy."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cscode.core.agent.base import AgentMode, BaseAgent
from cscode.core.agent.build import BuildAgent
from cscode.core.agent.factory import create_agent
from cscode.core.agent.plan import PlanAgent
from cscode.core.agent.subagent import SubAgentAgent
from cscode.core.agent.system_prompts import PLAN_SYSTEM_PROMPT
from cscode.schema.events import LLMEvent, TextDelta


def _make_mock_tool_registry() -> MagicMock:
    """Create a mock ToolRegistryV2 with synchronous materialize()."""
    from unittest.mock import AsyncMock

    registry = MagicMock()
    settle_mock = AsyncMock(return_value=None)
    registry.materialize.return_value = MagicMock(
        definitions=[],
        settle=settle_mock,
    )
    return registry


class TestBaseAgent:
    def test_abstract_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            BaseAgent(llm_client=AsyncMock(), tool_registry=AsyncMock())  # type: ignore[abstract]

    def test_mode_property(self) -> None:
        class TestAgent(BaseAgent):
            @property
            def mode(self) -> AgentMode:
                return AgentMode.BUILD

            async def run(  # type: ignore[override]
                self,
                user_input: str,
                **kwargs: Any,
            ) -> str:
                return "test"

        agent = TestAgent(llm_client=AsyncMock(), tool_registry=AsyncMock())
        assert agent.mode == AgentMode.BUILD

    def test_get_allowed_tools_default(self) -> None:
        class TestAgent(BaseAgent):
            @property
            def mode(self) -> AgentMode:
                return AgentMode.BUILD

            async def run(  # type: ignore[override]
                self,
                user_input: str,
                **kwargs: Any,
            ) -> str:
                return "test"

        agent = TestAgent(llm_client=AsyncMock(), tool_registry=AsyncMock())
        assert agent.get_allowed_tools() is None

    def test_get_system_prompt_default(self) -> None:
        class TestAgent(BaseAgent):
            @property
            def mode(self) -> AgentMode:
                return AgentMode.BUILD

            async def run(  # type: ignore[override]
                self,
                user_input: str,
                **kwargs: Any,
            ) -> str:
                return "test"

        agent = TestAgent(llm_client=AsyncMock(), tool_registry=AsyncMock())
        prompt = agent.get_system_prompt()
        assert prompt is not None and "You are a coding assistant" in prompt


class TestBuildAgent:
    def test_init(self) -> None:
        agent = BuildAgent(
            llm_client=AsyncMock(),
            tool_registry=AsyncMock(),
            system_prompt="You are a test agent",
        )
        assert agent.mode == AgentMode.BUILD
        assert agent._system_prompt == "You are a test agent"  # noqa: SLF001

    def test_get_system_prompt(self) -> None:
        agent = BuildAgent(
            llm_client=AsyncMock(),
            tool_registry=AsyncMock(),
            system_prompt="Custom prompt",
        )
        assert agent.get_system_prompt() == "Custom prompt"

    def test_get_allowed_tools(self) -> None:
        agent = BuildAgent(llm_client=AsyncMock(), tool_registry=AsyncMock())
        tools = agent.get_allowed_tools()
        assert tools is None  # None means all tools allowed

    @pytest.mark.asyncio
    async def test_run_returns_string(self) -> None:
        """BuildAgent.run() should return a string even on empty input."""
        events: list[LLMEvent] = []

        async def mock_stream(request: Any) -> AsyncIterator[LLMEvent]:
            yield TextDelta(text="hello")
            from cscode.schema.events import TextEnded
            yield TextEnded(full_text="hello")
            from cscode.schema.events import Finish
            yield Finish(finish_reason="stop")

        mock_llm = AsyncMock()
        mock_llm.route.model = "gpt-4o"
        mock_llm.stream = mock_stream  # type: ignore[method-assign]

        agent = BuildAgent(llm_client=mock_llm, tool_registry=_make_mock_tool_registry())
        result = await agent.run("test")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_run_empty_input(self) -> None:
        """Empty user input should still produce a response."""
        events: list[LLMEvent] = []

        async def mock_stream(request: Any) -> AsyncIterator[LLMEvent]:
            yield TextDelta(text="reply")
            from cscode.schema.events import TextEnded
            yield TextEnded(full_text="reply")
            from cscode.schema.events import Finish
            yield Finish(finish_reason="stop")

        mock_llm = AsyncMock()
        mock_llm.route.model = "gpt-4o"
        mock_llm.stream = mock_stream  # type: ignore[method-assign]

        agent = BuildAgent(llm_client=mock_llm, tool_registry=_make_mock_tool_registry())
        result = await agent.run("")
        assert isinstance(result, str)
        assert result == "reply"

    @pytest.mark.asyncio
    async def test_run_with_session(self) -> None:
        """Session parameter should be accepted and passed through."""

        events: list[LLMEvent] = []

        async def mock_stream(request: Any) -> AsyncIterator[LLMEvent]:
            yield TextDelta(text="response")
            from cscode.schema.events import TextEnded
            yield TextEnded(full_text="response")
            from cscode.schema.events import Finish
            yield Finish(finish_reason="stop")

        mock_llm = AsyncMock()
        mock_llm.route.model = "gpt-4o"
        mock_llm.stream = mock_stream  # type: ignore[method-assign]

        mock_session = AsyncMock()
        agent = BuildAgent(llm_client=mock_llm, tool_registry=_make_mock_tool_registry())
        result = await agent.run("hello", session=mock_session)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_run_stream(self) -> None:
        """run_stream should yield LLMEvents."""
        async def mock_stream(request: Any) -> AsyncIterator[LLMEvent]:
            yield TextDelta(text="streaming")
            from cscode.schema.events import TextEnded
            yield TextEnded(full_text="streaming")
            from cscode.schema.events import Finish
            yield Finish(finish_reason="stop")

        mock_llm = AsyncMock()
        mock_llm.route.model = "gpt-4o"
        mock_llm.stream = mock_stream  # type: ignore[method-assign]

        agent = BuildAgent(llm_client=mock_llm, tool_registry=_make_mock_tool_registry())
        events: list[LLMEvent] = []
        async for event in agent.run_stream("test"):
            events.append(event)
        assert len(events) > 0


class TestPlanAgent:
    def test_init(self) -> None:
        agent = PlanAgent(
            llm_client=AsyncMock(),
            tool_registry=MagicMock(),
        )
        assert agent.mode == AgentMode.PLAN

    def test_get_system_prompt_default(self) -> None:
        agent = PlanAgent(llm_client=AsyncMock(), tool_registry=MagicMock())
        prompt = agent.get_system_prompt()
        assert prompt is not None and "planning" in prompt.lower()

    def test_get_system_prompt_custom(self) -> None:
        agent = PlanAgent(
            llm_client=AsyncMock(),
            tool_registry=MagicMock(),
            system_prompt="Custom plan prompt",
        )
        assert agent.get_system_prompt() == "Custom plan prompt"

    def test_get_allowed_tools(self) -> None:
        agent = PlanAgent(llm_client=AsyncMock(), tool_registry=MagicMock())
        tools = agent.get_allowed_tools()
        assert tools is not None
        assert "read" in tools
        assert "grep" in tools
        assert "glob" in tools
        assert "edit" not in tools
        assert "bash" not in tools

    def test_permissions_restrict_to_read_only(self) -> None:
        """PlanAgent permissions should only allow read-only tools."""
        from cscode.core.permission_v2 import PermissionV2, RuleEffect

        agent = PlanAgent(llm_client=AsyncMock(), tool_registry=MagicMock())
        # Check via the internal permission builder
        from cscode.core.agent.plan import _build_plan_permissions

        perms = _build_plan_permissions()
        assert PermissionV2.is_allowed("read", "*", perms)
        assert PermissionV2.is_allowed("grep", "*", perms)
        assert not PermissionV2.is_allowed("edit", "*", perms)
        assert not PermissionV2.is_allowed("bash", "*", perms)
        assert not PermissionV2.is_allowed("write", "*", perms)

    @pytest.mark.asyncio
    async def test_run_returns_string(self) -> None:
        async def mock_stream(request: Any) -> AsyncIterator[LLMEvent]:
            yield TextDelta(text="plan")
            from cscode.schema.events import TextEnded
            yield TextEnded(full_text="plan result")
            from cscode.schema.events import Finish
            yield Finish(finish_reason="stop")

        mock_llm = AsyncMock()
        mock_llm.route.model = "gpt-4o"
        mock_llm.stream = mock_stream  # type: ignore[method-assign]

        agent = PlanAgent(llm_client=mock_llm, tool_registry=_make_mock_tool_registry())
        result = await agent.run("plan a feature")
        assert isinstance(result, str)
        assert result == "plan result"

    @pytest.mark.asyncio
    async def test_run_stream(self) -> None:
        async def mock_stream(request: Any) -> AsyncIterator[LLMEvent]:
            yield TextDelta(text="step 1")
            from cscode.schema.events import TextEnded
            yield TextEnded(full_text="step 1")
            from cscode.schema.events import Finish
            yield Finish(finish_reason="stop")

        mock_llm = AsyncMock()
        mock_llm.route.model = "gpt-4o"
        mock_llm.stream = mock_stream  # type: ignore[method-assign]

        agent = PlanAgent(llm_client=mock_llm, tool_registry=_make_mock_tool_registry())
        events: list[LLMEvent] = []
        async for event in agent.run_stream("plan this"):
            events.append(event)
        assert len(events) > 0


class TestSubAgentAgent:
    def test_init(self) -> None:
        agent = SubAgentAgent(
            llm_client=AsyncMock(),
            tool_registry=MagicMock(),
        )
        assert agent.mode == AgentMode.SUBAGENT

    def test_get_system_prompt_default(self) -> None:
        agent = SubAgentAgent(llm_client=AsyncMock(), tool_registry=MagicMock())
        prompt = agent.get_system_prompt()
        assert prompt is not None and "sub-agent" in prompt.lower()

    def test_get_system_prompt_custom(self) -> None:
        agent = SubAgentAgent(
            llm_client=AsyncMock(),
            tool_registry=MagicMock(),
            system_prompt="You are a focused sub-agent",
        )
        assert agent.get_system_prompt() == "You are a focused sub-agent"

    def test_get_allowed_tools(self) -> None:
        agent = SubAgentAgent(llm_client=AsyncMock(), tool_registry=MagicMock())
        assert agent.get_allowed_tools() is None

    @pytest.mark.asyncio
    async def test_run_returns_string(self) -> None:
        async def mock_stream(request: Any) -> AsyncIterator[LLMEvent]:
            yield TextDelta(text="done")
            from cscode.schema.events import TextEnded
            yield TextEnded(full_text="done")
            from cscode.schema.events import Finish
            yield Finish(finish_reason="stop")

        mock_llm = AsyncMock()
        mock_llm.route.model = "gpt-4o"
        mock_llm.stream = mock_stream  # type: ignore[method-assign]

        agent = SubAgentAgent(llm_client=mock_llm, tool_registry=_make_mock_tool_registry())
        result = await agent.run("do this task")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_run_stream(self) -> None:
        async def mock_stream(request: Any) -> AsyncIterator[LLMEvent]:
            yield TextDelta(text="working")
            from cscode.schema.events import TextEnded
            yield TextEnded(full_text="working")
            from cscode.schema.events import Finish
            yield Finish(finish_reason="stop")

        mock_llm = AsyncMock()
        mock_llm.route.model = "gpt-4o"
        mock_llm.stream = mock_stream  # type: ignore[method-assign]

        agent = SubAgentAgent(llm_client=mock_llm, tool_registry=_make_mock_tool_registry())
        events: list[LLMEvent] = []
        async for event in agent.run_stream("execute"):
            events.append(event)
        assert len(events) > 0


class TestAgentFactory:
    def test_create_build(self) -> None:
        agent = create_agent(
            AgentMode.BUILD,
            llm_client=AsyncMock(),
            tool_registry=MagicMock(),
        )
        assert isinstance(agent, BuildAgent)
        assert agent.mode == AgentMode.BUILD

    def test_create_plan(self) -> None:
        agent = create_agent(
            AgentMode.PLAN,
            llm_client=AsyncMock(),
            tool_registry=MagicMock(),
        )
        assert isinstance(agent, PlanAgent)
        assert agent.mode == AgentMode.PLAN

    def test_create_subagent(self) -> None:
        agent = create_agent(
            AgentMode.SUBAGENT,
            llm_client=AsyncMock(),
            tool_registry=MagicMock(),
        )
        assert isinstance(agent, SubAgentAgent)
        assert agent.mode == AgentMode.SUBAGENT

    def test_create_with_string_mode(self) -> None:
        agent = create_agent(
            "build",
            llm_client=AsyncMock(),
            tool_registry=MagicMock(),
        )
        assert isinstance(agent, BuildAgent)

    def test_create_with_custom_system_prompt(self) -> None:
        agent = create_agent(
            AgentMode.BUILD,
            llm_client=AsyncMock(),
            tool_registry=MagicMock(),
            system_prompt="Custom",
        )
        assert agent.get_system_prompt() == "Custom"

    def test_create_unknown_mode(self) -> None:
        with pytest.raises((ValueError, KeyError)):
            create_agent(
                "unknown_mode",
                llm_client=AsyncMock(),
                tool_registry=MagicMock(),
            )

    def test_create_default_tool_rounds(self) -> None:
        build = create_agent(AgentMode.BUILD, llm_client=AsyncMock(), tool_registry=MagicMock())
        plan = create_agent(AgentMode.PLAN, llm_client=AsyncMock(), tool_registry=MagicMock())
        sub = create_agent(AgentMode.SUBAGENT, llm_client=AsyncMock(), tool_registry=MagicMock())
        assert build._max_tool_rounds == 20  # type: ignore[attr-defined]
        assert plan._max_tool_rounds == 5  # type: ignore[attr-defined]
        assert sub._max_tool_rounds == 5  # type: ignore[attr-defined]
