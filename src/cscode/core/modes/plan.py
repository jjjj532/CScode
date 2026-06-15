from __future__ import annotations

from cscode.core.engine import Agent, AgentOptions
from cscode.providers.base import LLMProvider
from cscode.tools.base import ToolRegistry
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

PLAN_SYSTEM_PROMPT = (
    "You are in PLAN mode. You are a read-only agent. "
    "You may search, explore, analyze, and reason about the codebase, "
    "but you MUST NOT create, edit, or delete any files. "
    "Do not execute any tool that modifies the file system. "
    "Suggest changes only — do not implement them."
)


def create_plan_agent(provider: LLMProvider, registry: ToolRegistry) -> Agent:
    return Agent(
        config=provider.config,
        provider=provider,
        registry=registry,
        options=AgentOptions(
            max_tool_rounds=15,
            system_prompt=PLAN_SYSTEM_PROMPT,
            timeout=300.0,
        ),
    )
