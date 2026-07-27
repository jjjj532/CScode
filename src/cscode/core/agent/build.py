"""BuildAgent — full tool-loop agent for BUILD mode."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from cscode.core.agent.base import AgentMode, BaseAgent
from cscode.core.agent.system_prompts import BUILD_SYSTEM_PROMPT


class BuildAgent(BaseAgent):
    """BUILD-mode agent with full tool access and LLM loop.

    Wraps the existing AgentV2 implementation via lazy import to
    avoid circular dependencies (core -> app -> tools -> core).
    """

    def __init__(
        self,
        llm_client: Any,
        tool_registry: Any,
        max_tool_rounds: int = 20,
        system_prompt: str | None = None,
        permissions: Any | None = None,
    ) -> None:
        super().__init__(llm_client=llm_client, tool_registry=tool_registry)
        self._max_tool_rounds = max_tool_rounds
        self._system_prompt = system_prompt
        self._permissions = permissions
        self._agent: Any = None

    def _get_agent(self) -> Any:
        """Lazy-init the inner AgentV2 to break circular imports."""
        if self._agent is None:
            from cscode.app.agent import AgentV2

            self._agent = AgentV2(
                self._llm_client,
                self._tool_registry,
                self._max_tool_rounds,
                self._system_prompt,
                self._permissions,
            )
        return self._agent

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

    def get_system_prompt(self) -> str:
        return self._system_prompt or BUILD_SYSTEM_PROMPT

    def get_allowed_tools(self) -> list[str] | None:
        return None

    def __repr__(self) -> str:
        return f"<BuildAgent mode={self.mode.value}>"
