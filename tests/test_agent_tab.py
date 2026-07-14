"""Tests for AgentMode, AgentTab, and TabManager."""

from __future__ import annotations

import pytest

from cscode.core.agent.base import AgentMode, AgentTab
from cscode.core.agent.tab import TabManager


class TestAgentMode:
    def test_values(self) -> None:
        assert AgentMode.BUILD.value == "build"
        assert AgentMode.PLAN.value == "plan"
        assert AgentMode.SUBAGENT.value == "subagent"

    def test_members(self) -> None:
        assert set(AgentMode) == {AgentMode.BUILD, AgentMode.PLAN, AgentMode.SUBAGENT}

    def test_from_string(self) -> None:
        assert AgentMode("build") == AgentMode.BUILD
        assert AgentMode("plan") == AgentMode.PLAN
        assert AgentMode("subagent") == AgentMode.SUBAGENT

    def test_invalid_string(self) -> None:
        with pytest.raises(ValueError):
            AgentMode("invalid")  # type: ignore[arg-type]


class TestAgentTab:
    def test_fields(self) -> None:
        tab = AgentTab(
            id="tab_001",
            mode=AgentMode.BUILD,
            session_id="sess_001",
            title="My Tab",
            created_at=1000.0,
        )
        assert tab.id == "tab_001"
        assert tab.mode == AgentMode.BUILD
        assert tab.session_id == "sess_001"
        assert tab.title == "My Tab"
        assert tab.created_at == 1000.0

    def test_default_title_empty(self) -> None:
        tab = AgentTab(
            id="tab_002",
            mode=AgentMode.PLAN,
            session_id="sess_002",
            title="",
            created_at=2000.0,
        )
        assert tab.title == ""

    def test_immutable(self) -> None:
        tab = AgentTab(
            id="tab_003",
            mode=AgentMode.SUBAGENT,
            session_id="sess_003",
            title="Sub",
            created_at=3000.0,
        )
        with pytest.raises(AttributeError):
            tab.title = "changed"  # type: ignore[misc]


class TestTabManager:
    def test_create_tab_returns_tab(self) -> None:
        mgr = TabManager()
        tab = mgr.create_tab(mode=AgentMode.BUILD)
        assert isinstance(tab, AgentTab)
        assert tab.mode == AgentMode.BUILD
        assert tab.session_id != ""

    def test_create_tab_auto_title(self) -> None:
        mgr = TabManager()
        tab1 = mgr.create_tab()
        assert tab1.title == "Tab 1"
        tab2 = mgr.create_tab()
        assert tab2.title == "Tab 2"

    def test_create_tab_custom_title(self) -> None:
        mgr = TabManager()
        tab = mgr.create_tab(mode=AgentMode.PLAN, title="My Plan")
        assert tab.title == "My Plan"

    def test_create_tab_sets_active(self) -> None:
        mgr = TabManager()
        tab = mgr.create_tab()
        active = mgr.get_active()
        assert active is not None
        assert active.id == tab.id

    def test_create_tab_generates_session_id(self) -> None:
        mgr = TabManager()
        tab = mgr.create_tab()
        assert tab.session_id.startswith("sess_")

    def test_create_tab_unique_ids(self) -> None:
        mgr = TabManager()
        t1 = mgr.create_tab()
        t2 = mgr.create_tab()
        assert t1.id != t2.id
        assert t1.session_id != t2.session_id

    def test_switch_tab(self) -> None:
        mgr = TabManager()
        t1 = mgr.create_tab(title="First")
        mgr.create_tab(title="Second")
        switched = mgr.switch_tab(t1.id)
        assert switched is not None
        assert switched.id == t1.id
        active = mgr.get_active()
        assert active is not None
        assert active.id == t1.id

    def test_switch_tab_unknown_returns_none(self) -> None:
        mgr = TabManager()
        mgr.create_tab()
        result = mgr.switch_tab("nonexistent")
        assert result is None

    def test_close_tab_removes_and_returns(self) -> None:
        mgr = TabManager()
        t1 = mgr.create_tab(title="First")
        mgr.create_tab(title="Second")
        closed = mgr.close_tab(t1.id)
        assert closed is not None
        assert closed.id == t1.id
        assert t1.id not in [t.id for t in mgr.list_tabs()]

    def test_close_tab_unknown_returns_none(self) -> None:
        mgr = TabManager()
        mgr.create_tab()
        result = mgr.close_tab("nonexistent")
        assert result is None

    def test_close_active_tab_moves_to_other(self) -> None:
        mgr = TabManager()
        t1 = mgr.create_tab(title="First")
        t2 = mgr.create_tab(title="Second")
        mgr.close_tab(t2.id)
        active = mgr.get_active()
        assert active is not None
        assert active.id == t1.id

    def test_close_last_tab_sets_active_none(self) -> None:
        mgr = TabManager()
        tab = mgr.create_tab()
        mgr.close_tab(tab.id)
        assert mgr.get_active() is None

    def test_list_tabs_empty(self) -> None:
        mgr = TabManager()
        assert mgr.list_tabs() == []

    def test_list_tabs_returns_all(self) -> None:
        mgr = TabManager()
        t1 = mgr.create_tab(title="A")
        t2 = mgr.create_tab(title="B")
        tabs = mgr.list_tabs()
        assert len(tabs) == 2
        assert {t.id for t in tabs} == {t1.id, t2.id}

    def test_max_tabs_overflow(self) -> None:
        mgr = TabManager(max_tabs=2)
        mgr.create_tab()
        mgr.create_tab()
        with pytest.raises(ValueError, match="Maximum tabs"):
            mgr.create_tab()

    def test_get_active_none_when_empty(self) -> None:
        mgr = TabManager()
        assert mgr.get_active() is None
