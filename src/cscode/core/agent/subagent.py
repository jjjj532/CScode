"""SubAgentAgent — lightweight sub-agent for @tool dispatch and subtask execution."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from cscode.core.agent.base import AgentMode, BaseAgent


class SubAgentAgent(BaseAgent):
    """SUBAGENT-mode agent for dispatched subtask execution.

    Lightweight agent that processes tool mentions and limited-scope
    subtasks. Wraps AgentV2 via lazy import with reduced tool rounds.
    """

    def __init__(
        self,
        llm_client: Any,
        tool_registry: Any,
        max_tool_rounds: int = 5,
        system_prompt: str | None = None,
    ) -> None:
        super().__init__(llm_client=llm_client, tool_registry=tool_registry)
        self._max_tool_rounds = max_tool_rounds
        self._custom_prompt = system_prompt
        self._agent: Any = None

    def _get_agent(self) -> Any:
        """Lazy-init the inner AgentV2 to break circular imports."""
        if self._agent is None:
            from cscode.app.agent import AgentV2

            self._agent = AgentV2(
                self._llm_client,
                self._tool_registry,
                self._max_tool_rounds,
                self.get_system_prompt(),
            )
        return self._agent

    @property
    def mode(self) -> AgentMode:
        return AgentMode.SUBAGENT

    async def run(
        self,
        user_input: str,
        session: Any | None = None,
        on_event: Any | None = None,
        generation_options: Any | None = None,
    ) -> str:
        return await self._get_agent().run(  # type: ignore[no-any-return]
            user_input,
            session=session,
            on_event=on_event,
            generation_options=generation_options,
        )

    async def run_stream(
        self,
        user_input: str,
        session: Any | None = None,
        generation_options: Any | None = None,
    ) -> AsyncIterator[Any]:
        agent = self._get_agent()
        async for event in agent.run_stream(user_input, session=session, generation_options=generation_options):
            yield event

    def get_system_prompt(self) -> str | None:
        return self._custom_prompt or (
            "You are a sub-agent assisting with a specific task. "
            "Complete the assigned task using available tools and report back."
        )

    def get_allowed_tools(self) -> list[str] | None:
        return None  # None = all tools permitted

    def __repr__(self) -> str:
        return f"<SubAgentAgent mode={self.mode.value}>"
