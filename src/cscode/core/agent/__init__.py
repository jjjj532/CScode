"""Agent system — mode-based agents for build, plan, and subagent execution."""

from __future__ import annotations

from cscode.core.agent.base import AgentMode, AgentTab, BaseAgent
from cscode.core.agent.build import BuildAgent
from cscode.core.agent.factory import create_agent
from cscode.core.agent.plan import PlanAgent
from cscode.core.agent.registry import AgentDef, AgentRegistry
from cscode.core.agent.subagent import SubAgentAgent
from cscode.core.agent.system_prompts import (
    BUILD_SYSTEM_PROMPT,
    PLAN_SYSTEM_PROMPT,
    SUBAGENT_SYSTEM_PROMPT,
)
from cscode.core.agent.tab import TabManager

__all__ = [
    "AgentDef",
    "AgentMode",
    "AgentRegistry",
    "AgentTab",
    "BUILD_SYSTEM_PROMPT",
    "BaseAgent",
    "BuildAgent",
    "PLAN_SYSTEM_PROMPT",
    "PlanAgent",
    "SUBAGENT_SYSTEM_PROMPT",
    "SubAgentAgent",
    "TabManager",
    "create_agent",
]
