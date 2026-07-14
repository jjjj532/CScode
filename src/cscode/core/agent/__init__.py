"""Agent system — mode-based agents for build, plan, and subagent execution."""

from __future__ import annotations

from cscode.core.agent.base import AgentMode, AgentTab, BaseAgent
from cscode.core.agent.build import BuildAgent
from cscode.core.agent.factory import create_agent
from cscode.core.agent.plan import PlanAgent
from cscode.core.agent.subagent import SubAgentAgent
from cscode.core.agent.tab import TabManager

__all__ = [
    "AgentMode",
    "AgentTab",
    "BaseAgent",
    "BuildAgent",
    "PlanAgent",
    "SubAgentAgent",
    "TabManager",
    "create_agent",
]
