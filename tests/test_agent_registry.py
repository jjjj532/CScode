"""Tests for AgentRegistry — central agent type registry."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from cscode.core.agent.base import AgentMode, BaseAgent
from cscode.core.agent.registry import AgentDef, AgentRegistry, NO_MATCH_FOUND


class _FakeAgent(BaseAgent):
    """Minimal agent for testing registry integration."""

    @property
    def mode(self) -> AgentMode:
        return AgentMode.BUILD

    async def run(
        self,
        user_input: str,
        session: Any | None = None,
        on_event: Any | None = None,
        generation_options: Any | None = None,
    ) -> str:
        return f"fake:{user_input}"


def _fake_factory(llm_client: Any, tool_registry: Any, **kwargs: Any) -> BaseAgent:
    return _FakeAgent(llm_client=llm_client, tool_registry=tool_registry)


class TestAgentRegistry:
    def test_register_and_get(self) -> None:
        reg = AgentRegistry()
        d = AgentDef(
            name="test-builder",
            description="A test agent",
            mode=AgentMode.BUILD,
            factory=_fake_factory,
        )
        reg.register(d)
        got = reg.get("test-builder")
        assert got is not None
        assert got.name == "test-builder"
        assert got.mode == AgentMode.BUILD

    def test_register_duplicate_raises(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(name="dup", description="", mode=AgentMode.BUILD, factory=_fake_factory))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(AgentDef(name="dup", description="", mode=AgentMode.BUILD, factory=_fake_factory))

    def test_unregister(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(name="x", description="", mode=AgentMode.BUILD, factory=_fake_factory))
        reg.unregister("x")
        assert reg.get("x") is None

    def test_unregister_missing_raises(self) -> None:
        reg = AgentRegistry()
        with pytest.raises(KeyError, match="not found"):
            reg.unregister("nonexistent")

    def test_list(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(name="a", description="", mode=AgentMode.PLAN, factory=_fake_factory))
        reg.register(AgentDef(name="b", description="", mode=AgentMode.BUILD, factory=_fake_factory))
        all_agents = reg.list()
        assert len(all_agents) == 2
        names = {a.name for a in all_agents}
        assert names == {"a", "b"}

    def test_list_empty(self) -> None:
        reg = AgentRegistry()
        assert reg.list() == []

    def test_find_by_capability(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(
            name="reader", description="", mode=AgentMode.PLAN,
            capabilities={"read", "search"}, factory=_fake_factory,
        ))
        reg.register(AgentDef(
            name="writer", description="", mode=AgentMode.BUILD,
            capabilities={"write", "edit"}, factory=_fake_factory,
        ))
        reg.register(AgentDef(
            name="full", description="", mode=AgentMode.BUILD,
            capabilities={"read", "write", "search"}, factory=_fake_factory,
        ))

        readers = reg.find_by_capability("read")
        assert len(readers) == 2
        assert {a.name for a in readers} == {"reader", "full"}

        writers = reg.find_by_capability("write")
        assert len(writers) == 2
        assert {a.name for a in writers} == {"writer", "full"}

    def test_find_by_capability_none_match(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(
            name="reader", description="", mode=AgentMode.PLAN,
            capabilities={"read"}, factory=_fake_factory,
        ))
        assert reg.find_by_capability("fly") == []

    def test_find_by_capability_empty_registry(self) -> None:
        reg = AgentRegistry()
        assert reg.find_by_capability("anything") == []

    def test_find_by_mode(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(name="p1", description="", mode=AgentMode.PLAN, factory=_fake_factory))
        reg.register(AgentDef(name="p2", description="", mode=AgentMode.PLAN, factory=_fake_factory))
        reg.register(AgentDef(name="b1", description="", mode=AgentMode.BUILD, factory=_fake_factory))

        plans = reg.find_by_mode(AgentMode.PLAN)
        assert len(plans) == 2

        builds = reg.find_by_mode(AgentMode.BUILD)
        assert len(builds) == 1
        assert builds[0].name == "b1"

    def test_count(self) -> None:
        reg = AgentRegistry()
        assert reg.count() == 0
        reg.register(AgentDef(name="a", description="", mode=AgentMode.BUILD, factory=_fake_factory))
        assert reg.count() == 1
        reg.register(AgentDef(name="b", description="", mode=AgentMode.PLAN, factory=_fake_factory))
        assert reg.count() == 2

    def test_create_returns_agent_instance(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(name="test", description="", mode=AgentMode.BUILD, factory=_fake_factory))
        agent = reg.create("test", llm_client=None, tool_registry=None)
        assert isinstance(agent, BaseAgent)
        assert isinstance(agent, _FakeAgent)

    def test_create_missing_raises(self) -> None:
        reg = AgentRegistry()
        with pytest.raises(KeyError, match="not found"):
            reg.create("nonexistent", llm_client=None, tool_registry=None)


class TestGlobalRegistry:
    """Tests for the global registry singleton in factory.py."""

    def test_get_registry_creates_singleton(self) -> None:
        from cscode.core.agent.factory import get_registry, reset_registry
        reset_registry()
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_global_registry_has_builtins(self) -> None:
        from cscode.core.agent.factory import get_registry, reset_registry
        reset_registry()
        reg = get_registry()
        assert reg.count() == 3
        assert reg.get("build") is not None
        assert reg.get("plan") is not None
        assert reg.get("subagent") is not None

    def test_builtin_agent_modes(self) -> None:
        from cscode.core.agent.factory import get_registry, reset_registry
        reset_registry()
        reg = get_registry()
        build = reg.get("build")
        plan = reg.get("plan")
        sub = reg.get("subagent")
        assert build is not None and plan is not None and sub is not None
        assert build.mode == AgentMode.BUILD
        assert plan.mode == AgentMode.PLAN
        assert sub.mode == AgentMode.SUBAGENT

    def test_builtin_capabilities(self) -> None:
        from cscode.core.agent.factory import get_registry, reset_registry
        reset_registry()
        reg = get_registry()
        build = reg.get("build")
        assert build is not None
        assert "read" in build.capabilities
        assert "write" in build.capabilities
        assert "plan" not in build.capabilities

    def test_reset_registry_clears(self) -> None:
        from cscode.core.agent.factory import get_registry, reset_registry
        reset_registry()
        reg1 = get_registry()
        assert reg1.count() == 3
        reset_registry()
        reg2 = get_registry()
        assert reg2 is not reg1


class TestRoute:
    """Tests for AgentRegistry.route() — capability-based agent routing."""

    def test_route_returns_matching_agent(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(name="reader", description="", mode=AgentMode.PLAN,
                              capabilities={"read"}, priority=1, factory=_fake_factory))
        reg.register(AgentDef(name="writer", description="", mode=AgentMode.BUILD,
                              capabilities={"write"}, priority=1, factory=_fake_factory))
        got = reg.route("write")
        assert got is not None
        assert got.name == "writer"

    def test_route_returns_highest_priority(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(name="base", description="", mode=AgentMode.PLAN,
                              capabilities={"read"}, priority=0, factory=_fake_factory))
        reg.register(AgentDef(name="preferred", description="", mode=AgentMode.BUILD,
                              capabilities={"read"}, priority=10, factory=_fake_factory))
        got = reg.route("read")
        assert got is not None
        assert got.name == "preferred"

    def test_route_returns_first_when_same_priority(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(name="a", description="", mode=AgentMode.BUILD,
                              capabilities={"read"}, priority=1, factory=_fake_factory))
        reg.register(AgentDef(name="b", description="", mode=AgentMode.BUILD,
                              capabilities={"read"}, priority=1, factory=_fake_factory))
        got = reg.route("read")
        assert got is not None
        assert got.name == "a"

    def test_route_fallback_returns_no_match_when_no_fallback(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(name="reader", description="", mode=AgentMode.PLAN,
                              capabilities={"read"}, priority=1, factory=_fake_factory))
        got = reg.route("write", fallback=False)
        assert got is NO_MATCH_FOUND

    def test_route_with_fallback_returns_build_when_no_match(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(name="build", description="", mode=AgentMode.BUILD,
                              capabilities={"write"}, priority=0, factory=_fake_factory))
        reg.register(AgentDef(name="reader", description="", mode=AgentMode.PLAN,
                              capabilities={"read"}, priority=1, factory=_fake_factory))
        got = reg.route("fly", fallback=True)
        assert got is not None
        assert got.name == "build"

    def test_route_empty_registry_returns_no_match(self) -> None:
        reg = AgentRegistry()
        got = reg.route("anything", fallback=False)
        assert got is NO_MATCH_FOUND

    def test_route_empty_registry_with_fallback(self) -> None:
        reg = AgentRegistry()
        reg.register(AgentDef(name="build", description="", mode=AgentMode.BUILD,
                              capabilities={"write"}, priority=0, factory=_fake_factory))
        got = reg.route("anything", fallback=True)
        assert got is not None
        assert got.name == "build"
