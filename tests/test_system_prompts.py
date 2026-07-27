"""Tests for system prompt constants and agent default prompt behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cscode.core.agent.base import AgentMode
from cscode.core.agent.system_prompts import (
    BUILD_SYSTEM_PROMPT,
    PLAN_SYSTEM_PROMPT,
    SUBAGENT_SYSTEM_PROMPT,
)


class TestPromptConstants:
    """Verify every system prompt constant is a non-empty string."""

    def test_build_prompt_defined(self) -> None:
        assert isinstance(BUILD_SYSTEM_PROMPT, str)
        assert len(BUILD_SYSTEM_PROMPT) > 50

    def test_plan_prompt_defined(self) -> None:
        assert isinstance(PLAN_SYSTEM_PROMPT, str)
        assert len(PLAN_SYSTEM_PROMPT) > 50

    def test_subagent_prompt_defined(self) -> None:
        assert isinstance(SUBAGENT_SYSTEM_PROMPT, str)
        assert len(SUBAGENT_SYSTEM_PROMPT) > 50

    def test_prompts_are_distinct(self) -> None:
        """Each mode should have a unique prompt tailored to its purpose."""
        prompts = {BUILD_SYSTEM_PROMPT, PLAN_SYSTEM_PROMPT, SUBAGENT_SYSTEM_PROMPT}
        assert len(prompts) == 3

    def test_plan_prompt_mentions_readonly(self) -> None:
        """Plan-mode prompt should restrict to read-only tools."""
        assert "read-only" in PLAN_SYSTEM_PROMPT.lower()
        assert "write" not in PLAN_SYSTEM_PROMPT.lower() or "not" in PLAN_SYSTEM_PROMPT.lower()


class TestBuildAgentDefaultPrompt:
    """BuildAgent uses BUILD_SYSTEM_PROMPT when no custom prompt given."""

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_registry(self) -> MagicMock:
        return MagicMock()

    def test_default_prompt_fallback(self, mock_llm: MagicMock, mock_registry: MagicMock) -> None:
        from cscode.core.agent.build import BuildAgent

        agent = BuildAgent(llm_client=mock_llm, tool_registry=mock_registry)
        prompt = agent.get_system_prompt()
        assert prompt == BUILD_SYSTEM_PROMPT

    def test_custom_prompt_override(self, mock_llm: MagicMock, mock_registry: MagicMock) -> None:
        from cscode.core.agent.build import BuildAgent

        custom = "You are a specialized coding assistant for Python."
        agent = BuildAgent(llm_client=mock_llm, tool_registry=mock_registry, system_prompt=custom)
        assert agent.get_system_prompt() == custom

    def test_mode_is_build(self, mock_llm: MagicMock, mock_registry: MagicMock) -> None:
        from cscode.core.agent.build import BuildAgent

        agent = BuildAgent(llm_client=mock_llm, tool_registry=mock_registry)
        assert agent.mode == AgentMode.BUILD


class TestSubAgentAgentDefaultPrompt:
    """SubAgentAgent uses SUBAGENT_SYSTEM_PROMPT when no custom prompt given."""

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_registry(self) -> MagicMock:
        return MagicMock()

    def test_default_prompt_fallback(self, mock_llm: MagicMock, mock_registry: MagicMock) -> None:
        from cscode.core.agent.subagent import SubAgentAgent

        agent = SubAgentAgent(llm_client=mock_llm, tool_registry=mock_registry)
        prompt = agent.get_system_prompt()
        assert prompt == SUBAGENT_SYSTEM_PROMPT

    def test_custom_prompt_override(self, mock_llm: MagicMock, mock_registry: MagicMock) -> None:
        from cscode.core.agent.subagent import SubAgentAgent

        custom = "You are a sub-agent focused on file analysis."
        agent = SubAgentAgent(llm_client=mock_llm, tool_registry=mock_registry, system_prompt=custom)
        assert agent.get_system_prompt() == custom

    def test_mode_is_subagent(self, mock_llm: MagicMock, mock_registry: MagicMock) -> None:
        from cscode.core.agent.subagent import SubAgentAgent

        agent = SubAgentAgent(llm_client=mock_llm, tool_registry=mock_registry)
        assert agent.mode == AgentMode.SUBAGENT


class TestPlanAgentDefaultPrompt:
    """PlanAgent uses PLAN_SYSTEM_PROMPT when no custom prompt given."""

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_registry(self) -> MagicMock:
        return MagicMock()

    def test_default_prompt_fallback(self, mock_llm: MagicMock, mock_registry: MagicMock) -> None:
        from cscode.core.agent.plan import PlanAgent

        agent = PlanAgent(llm_client=mock_llm, tool_registry=mock_registry)
        prompt = agent.get_system_prompt()
        assert prompt == PLAN_SYSTEM_PROMPT

    def test_custom_prompt_override(self, mock_llm: MagicMock, mock_registry: MagicMock) -> None:
        from cscode.core.agent.plan import PlanAgent

        custom = "You are a planning expert for frontend projects."
        agent = PlanAgent(llm_client=mock_llm, tool_registry=mock_registry, system_prompt=custom)
        assert agent.get_system_prompt() == custom

    def test_mode_is_plan(self, mock_llm: MagicMock, mock_registry: MagicMock) -> None:
        from cscode.core.agent.plan import PlanAgent

        agent = PlanAgent(llm_client=mock_llm, tool_registry=mock_registry)
        assert agent.mode == AgentMode.PLAN
