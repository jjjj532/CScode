"""PlanAgent — read-only planning mode for PLAN mode."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from cscode.core.agent.base import AgentMode, BaseAgent
from cscode.core.agent.system_prompts import PLAN_SYSTEM_PROMPT
from cscode.core.permission_v2 import Rule, RuleEffect, Ruleset

# Read-only tools allowed in plan mode
_PLAN_ALLOWED_TOOLS = frozenset({
    "read",
    "grep",
    "glob",
    "ls",
    "web_search",
    "web_fetch",
})


def _build_plan_permissions() -> list[Ruleset]:
    """Build a permission ruleset that only allows read-only tools."""
    rules = [
        Rule(action=tool, resource="*", effect=RuleEffect.ALLOW)
        for tool in sorted(_PLAN_ALLOWED_TOOLS)
    ]
    return [Ruleset(name="plan-readonly", rules=rules)]


class PlanAgent(BaseAgent):
    """PLAN-mode agent with read-only tool access.

    Generates structured plans using only observation tools.
    Wraps AgentV2 via lazy import to avoid circular dependencies.
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
                permissions=_build_plan_permissions(),
            )
        return self._agent

    @property
    def mode(self) -> AgentMode:
        return AgentMode.PLAN

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
        return self._custom_prompt or PLAN_SYSTEM_PROMPT

    def get_allowed_tools(self) -> list[str] | None:
        return sorted(_PLAN_ALLOWED_TOOLS)

    def __repr__(self) -> str:
        return f"<PlanAgent mode={self.mode.value}>"
