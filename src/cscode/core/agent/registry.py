from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final, List

from cscode.core.agent.base import AgentMode, BaseAgent

# Sentinel returned by route() when no matching agent is found and fallback is off.
NO_MATCH_FOUND: Final[object] = object()


@dataclass
class AgentDef:
    """Definition of a registered agent type.

    Attributes:
        name: Unique agent identifier.
        description: Human-readable description.
        mode: Agent execution mode.
        capabilities: Set of capability strings for discovery (e.g. "read", "write", "search").
        priority: Higher = preferred when routing by capability (default 0).
        factory: Callable that creates an agent instance.
            Signature: ``(llm_client, tool_registry, **kwargs) -> BaseAgent``
        metadata: Arbitrary key-value metadata for extension.
    """

    name: str
    description: str
    mode: AgentMode
    factory: Callable[..., BaseAgent]
    capabilities: set[str] = field(default_factory=set)
    priority: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


class AgentRegistry:
    """Central registry for agent types.

    Supports registration, discovery by capability/mode, and factory invocation.
    Designed for both built-in agents and plugin-registered agents.
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentDef] = {}

    def register(self, agent_def: AgentDef) -> None:
        """Register an agent type.

        Raises ValueError if an agent with the same name already exists.
        """
        if agent_def.name in self._agents:
            msg = f"Agent '{agent_def.name}' already registered"
            raise ValueError(msg)
        self._agents[agent_def.name] = agent_def

    def unregister(self, name: str) -> None:
        """Remove a registered agent type.

        Raises KeyError if not found.
        """
        if name not in self._agents:
            msg = f"Agent '{name}' not found"
            raise KeyError(msg)
        del self._agents[name]

    def get(self, name: str) -> AgentDef | None:
        """Look up an agent type by name."""
        return self._agents.get(name)

    def list(self) -> list[AgentDef]:
        """Return all registered agent types."""
        return list(self._agents.values())

    def find_by_capability(self, capability: str) -> List[AgentDef]:
        """Find all agent types that have a given capability."""
        return [a for a in self._agents.values() if capability in a.capabilities]

    def find_by_mode(self, mode: AgentMode) -> List[AgentDef]:
        """Find all agent types matching an execution mode."""
        return [a for a in self._agents.values() if a.mode == mode]

    def count(self) -> int:
        """Return the number of registered agent types."""
        return len(self._agents)

    def route(self, capability: str, fallback: bool = True) -> AgentDef | object:
        """Capability-based agent routing.

        Returns the highest-priority agent that has the given capability.
        If none match and *fallback* is True (default), returns the agent
        named ``"build"``. If *fallback* is False, returns ``NO_MATCH_FOUND``.

        Returns:
            The best-matching AgentDef, or ``NO_MATCH_FOUND``.
        """
        candidates = self.find_by_capability(capability)
        if candidates:
            return max(candidates, key=lambda a: a.priority)
        if fallback:
            build = self._agents.get("build")
            if build is not None:
                return build
        return NO_MATCH_FOUND

    def create(
        self,
        name: str,
        llm_client: Any,
        tool_registry: Any,
        **kwargs: Any,
    ) -> BaseAgent:
        """Create an agent instance by registered name.

        Args:
            name: Registered agent name.
            llm_client: LLM client for the agent.
            tool_registry: Tool registry for the agent.
            **kwargs: Additional keyword arguments passed to the factory.

        Returns:
            A new agent instance.

        Raises:
            KeyError: If the agent name is not registered.
        """
        agent_def = self._agents.get(name)
        if agent_def is None:
            msg = f"Agent '{name}' not found"
            raise KeyError(msg)
        return agent_def.factory(llm_client, tool_registry, **kwargs)
