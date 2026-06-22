from __future__ import annotations

from cscode.core.engine import Agent, AgentOptions
from cscode.providers.base import LLMProvider
from cscode.tools.base import ToolRegistry
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

BUILD_SYSTEM_PROMPT = (
    "You are in BUILD mode. You have full tool access to create, edit, "
    "read, and delete files, run commands, and modify the codebase. "
    "You may use any available tool to implement changes. "
    "Always verify your changes work correctly before completing."
)


def create_build_agent(provider: LLMProvider, registry: ToolRegistry) -> Agent:
    return Agent(
        config=provider.config,
        provider=provider,
        registry=registry,
        options=AgentOptions(
            system_prompt=BUILD_SYSTEM_PROMPT,
            timeout=600.0,
        ),
    )
