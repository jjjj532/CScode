"""Base agent types — AgentMode enum, AgentTab dataclass, and BaseAgent ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Any


class AgentMode(str, Enum):
    """Agent execution mode.

    - BUILD: Default development mode, full tool access.
    - PLAN: Step-by-step planning mode, read-only tools.
    - SUBAGENT: Dispatched sub-agent with limited scope.
    """

    BUILD = "build"
    PLAN = "plan"
    SUBAGENT = "subagent"


@dataclass(frozen=True)
class AgentTab:
    """A tab representing an agent session within the UI.

    Attributes:
        id: Unique tab identifier.
        mode: Agent execution mode.
        session_id: Linked SessionV2 session ID.
        title: Display title.
        created_at: Unix timestamp when the tab was created.
    """

    id: str
    mode: AgentMode
    session_id: str
    title: str
    created_at: float


class BaseAgent(ABC):
    """Abstract base class for all agent execution modes.

    Defines the standard interface all agents must implement.
    Subclasses must override ``mode`` and ``run()``.

    Attributes:
        llm_client: The LLM client for model interactions.
        tool_registry: The tool registry for available tools.
    """

    def __init__(self, llm_client: Any, tool_registry: Any) -> None:
        self._llm_client = llm_client
        self._tool_registry = tool_registry

    @property
    @abstractmethod
    def mode(self) -> AgentMode:
        """Return the execution mode of this agent."""
        ...

    @abstractmethod
    async def run(
        self,
        user_input: str,
        session: Any | None = None,
        on_event: Any | None = None,
        generation_options: Any | None = None,
    ) -> str:
        """Process a user prompt and return the final response.

        Args:
            user_input: The user's prompt text.
            session: Optional session for persistence.
            on_event: Optional callback for streaming events.
            generation_options: Optional generation parameters.

        Returns:
            The final assistant response text.
        """
        ...

    async def run_stream(
        self,
        user_input: str,
        session: Any | None = None,
        generation_options: Any | None = None,
    ) -> AsyncIterator[Any]:
        """Stream response events for a user prompt.

        Default implementation yields nothing; subclasses should override
        for streaming support.
        """
        if False:
            yield  # pragma: no cover

    async def run_with_messages(
        self,
        messages: list[Any],
        on_event: Any | None = None,
        generation_options: Any | None = None,
    ) -> str:
        """Run the agent on a pre-built message list.

        Args:
            messages: Pre-built message list (may be modified in place).
            on_event: Optional callback for streaming events.
            generation_options: Optional generation parameters.

        Returns:
            The final assistant response text.
        """
        raise NotImplementedError("run_with_messages not implemented")

    def get_system_prompt(self) -> str | None:
        """Return the system prompt for this agent.

        Returns None if no custom system prompt is set.
        """
        return "You are a coding assistant with access to development tools."

    def get_allowed_tools(self) -> list[str] | None:
        """Return the list of allowed tool names.

        Returns None if all tools are allowed.
        """
        return None

    @property
    def llm_client(self) -> Any:
        """The LLM client for model interactions."""
        return self._llm_client

    @property
    def tool_registry(self) -> Any:
        """The tool registry for available tools."""
        return self._tool_registry
