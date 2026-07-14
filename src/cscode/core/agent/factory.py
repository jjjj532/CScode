"""AgentFactory — create agents by mode."""

from __future__ import annotations

from typing import Any

from cscode.core.agent.base import AgentMode, BaseAgent
from cscode.core.agent.build import BuildAgent
from cscode.core.agent.plan import PlanAgent
from cscode.core.agent.subagent import SubAgentAgent


def create_agent(
    mode: AgentMode | str,
    llm_client: Any,
    tool_registry: Any,
    *,
    max_tool_rounds: int | None = None,
    system_prompt: str | None = None,
    permissions: Any | None = None,
) -> BaseAgent:
    """Create an agent for the given mode.

    Args:
        mode: Agent execution mode (AgentMode enum or string).
        llm_client: The LLM client for model interactions.
        tool_registry: The tool registry for available tools.
        max_tool_rounds: Max tool call rounds. Defaults per mode:
                         BUILD=20, PLAN=5, SUBAGENT=5.
        system_prompt: Optional custom system prompt.
        permissions: Optional permission rulesets (only for BUILD mode).

    Returns:
        A BaseAgent subclass instance matching the mode.

    Raises:
        ValueError: If mode is unknown.
    """
    if isinstance(mode, str):
        mode = AgentMode(mode)

    match mode:
        case AgentMode.BUILD:
            return BuildAgent(
                llm_client=llm_client,
                tool_registry=tool_registry,
                max_tool_rounds=max_tool_rounds or 20,
                system_prompt=system_prompt,
                permissions=permissions,
            )
        case AgentMode.PLAN:
            return PlanAgent(
                llm_client=llm_client,
                tool_registry=tool_registry,
                max_tool_rounds=max_tool_rounds or 5,
                system_prompt=system_prompt,
            )
        case AgentMode.SUBAGENT:
            return SubAgentAgent(
                llm_client=llm_client,
                tool_registry=tool_registry,
                max_tool_rounds=max_tool_rounds or 5,
                system_prompt=system_prompt,
            )
        case _:
            msg = f"Unknown agent mode: {mode}"
            raise ValueError(msg)
