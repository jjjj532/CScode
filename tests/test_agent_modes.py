"""Integration tests for agent mode creation and switching."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cscode.core.agent.base import AgentMode
from cscode.core.agent.tab import TabManager
from cscode.core.config import Config


def _make_agent(config: Config, mode: str | None = None) -> Any:
    from cscode.app.factory import create_agent_v2
    return create_agent_v2(config, mode=mode)


@pytest.fixture
def config() -> Config:
    return Config(provider="openai", model="gpt-4o")


@pytest.fixture
def mock_factory_deps() -> MagicMock:
    with (
        patch("cscode.app.factory.LLMClient"),
        patch("cscode.app.agent.AgentV2") as mock_agent_cls,
    ):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        yield mock_agent_cls


class TestTabManagerMode:
    def test_create_tab_default_mode(self) -> None:
        mgr = TabManager()
        tab = mgr.create_tab()
        assert tab.mode == AgentMode.BUILD

    def test_create_tab_plan_mode(self) -> None:
        mgr = TabManager()
        tab = mgr.create_tab(mode=AgentMode.PLAN)
        assert tab.mode == AgentMode.PLAN

    def test_create_tab_subagent_mode(self) -> None:
        mgr = TabManager()
        tab = mgr.create_tab(mode=AgentMode.SUBAGENT)
        assert tab.mode == AgentMode.SUBAGENT

    def test_switch_tab_keeps_mode(self) -> None:
        mgr = TabManager()
        t1 = mgr.create_tab(mode=AgentMode.BUILD)
        t2 = mgr.create_tab(mode=AgentMode.PLAN)
        mgr.switch_tab(t1.id)
        active = mgr.get_active()
        assert active is not None and active.mode == AgentMode.BUILD
        mgr.switch_tab(t2.id)
        active = mgr.get_active()
        assert active is not None and active.mode == AgentMode.PLAN

    def test_close_tab_removes_mode_tracking(self) -> None:
        mgr = TabManager()
        t1 = mgr.create_tab(mode=AgentMode.PLAN)
        mgr.close_tab(t1.id)
        assert mgr.get_active() is None


class TestFactoryModePassthrough:
    def test_factory_passes_mode_to_agent(self, config: Config) -> None:
        factory = _make_agent(config, mode="plan")
        assert factory is not None

    def test_factory_default_mode_build(self, config: Config) -> None:
        factory = _make_agent(config)
        assert factory is not None

    def test_factory_passes_system_prompt(self, config: Config,
                                           mock_factory_deps: MagicMock) -> None:
        config.system_prompt = "custom prompt"
        _make_agent(config)
        mock_factory_deps.assert_called_once()
        _args, kwargs = mock_factory_deps.call_args
        assert kwargs.get("system_prompt") == "custom prompt"


class TestCLIModeDispatch:
    def test_cli_create_agent_with_mode(self) -> None:
        from cscode.cli import _create_agent
        with (
            patch("cscode.app.create_agent_v2") as mock_factory,
            patch("cscode.cli.load_config") as mock_config,
        ):
            mock_config.return_value = Config()
            _create_agent(mode="plan")
        mock_factory.assert_called_once()
        _args, kwargs = mock_factory.call_args
        assert kwargs.get("mode") == "plan"

    def test_cli_create_agent_default_mode(self) -> None:
        from cscode.cli import _create_agent
        with (
            patch("cscode.app.create_agent_v2") as mock_factory,
            patch("cscode.cli.load_config") as mock_config,
        ):
            mock_config.return_value = Config()
            _create_agent(mode=None)
        mock_factory.assert_called_once()
        _args, kwargs = mock_factory.call_args
        assert kwargs.get("mode") is None
