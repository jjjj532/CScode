"""AgentV2 工厂 — 从配置构建 AgentV2 实例。

用法:
    config = load_config()
    agent = create_agent_v2(config)
    result = await agent.run("Hello!")
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cscode.app.agent import AgentV2
    from cscode.core.config import Config

from cscode.core.permission_v2 import Ruleset, SavedRules
from cscode.core.tool_registry import ToolRegistryV2
from cscode.llm.client import LLMClient
from cscode.llm.route import resolve_route
from cscode.schema.ids import ModelID, ProviderID
from cscode.storage.db import Database
from cscode.tools2 import (
    ApplyPatchTool,
    BashTool,
    BrowserTool,
    EditTool,
    GlobTool,
    GrepTool,
    LSPTool,
    LsTool,
    OutputStoreTool,
    PlanTool,
    PTYTool,
    QuestionTool,
    ReadTool,
    SkillTool,
    TaskTool,
    TodoWriteTool,
    TruncateTool,
    WebFetchTool,
    WebSearchTool,
    WriteTool,
)
from cscode.tools2.base import Tool as _Tool
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

# Provider → standard env var name for API key
_PROVIDER_KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "azure": "AZURE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _resolve_api_key(config: Config) -> str:
    """Resolve API key from config or environment fallback.

    Priority:
      1. config.api_key (set via CSCODE_API_KEY or config file)
      2. Provider-specific env var (e.g. OPENAI_API_KEY)
      3. Empty string (provider may work without key, e.g. Ollama)
    """
    if config.api_key:
        logger.debug("API key resolved from config for provider=%s", config.provider)
        return config.api_key

    env_name = _PROVIDER_KEY_ENV.get(config.provider.lower())
    if env_name:
        env_val = os.environ.get(env_name)
        if env_val:
            logger.debug("API key resolved from env %s for provider=%s", env_name, config.provider)
            return env_val

    logger.debug("No API key found for provider=%s", config.provider)
    return ""


async def load_permission_rules(database: Database) -> list[Ruleset]:
    """Load permission rules from the database via SavedRules.

    Returns an empty list when no rules exist (→ all tools allowed).

    Usage:
        database = Database()
        await database.init()
        rules = await load_permission_rules(database)
        agent = create_agent_v2(config, permissions=rules)
    """
    saved = SavedRules(database)
    rules = await saved.load()
    if not rules:
        logger.debug("load_permission_rules: no rules found")
        return []
    ruleset = Ruleset(name="saved", rules=rules)
    logger.info("load_permission_rules: loaded %d rule(s)", len(rules))
    return [ruleset]


def create_tool_registry() -> ToolRegistryV2:
    """Create the default tool registry with all standard tools."""
    registry = ToolRegistryV2()
    tools: list[_Tool[Any, Any]] = [
        ReadTool(),
        WriteTool(),
        EditTool(),
        BashTool(),
        GrepTool(),
        GlobTool(),
        LsTool(),
        LSPTool(),
        BrowserTool(),
        WebFetchTool(),
        WebSearchTool(),
        TodoWriteTool(),
        SkillTool(),
        QuestionTool(),
        ApplyPatchTool(),
        PlanTool(),
        PTYTool(),
        TaskTool(),
        TruncateTool(),
        OutputStoreTool(),
    ]
    for tool in tools:
        registry.register_tool(tool)
    logger.info("Tool registry created with %d tools: %s", len(tools), [t.name for t in tools])
    return registry


async def build_full_tool_registry(
    plugin_dirs: list[str] | None = None,
) -> ToolRegistryV2:
    """Build a ``ToolRegistryV2`` with standard tools + plugin tools.

    Discovers, loads, and activates plugins from ``plugin_dirs``, wraps
    their v1 tools via ``LegacyToolAdapter``, and registers them alongside
    the standard v2 tools.

    Usage::

        registry = await build_full_tool_registry()
        agent = create_agent_v2(config, tool_registry=registry)

    Args:
        plugin_dirs: Optional list of plugin directory paths to scan.
                     When ``None`` or empty, only standard tools are included.

    Returns:
        A fully populated ``ToolRegistryV2``.
    """
    registry = create_tool_registry()

    if plugin_dirs:
        from cscode.core.plugin.host import PluginHost
        from cscode.tools2.adapter import LegacyToolAdapter

        host = PluginHost()
        try:
            await host.discover(plugin_dirs)
        except Exception:
            logger.exception("build_full_tool_registry: plugin discovery failed")
            return registry

        for manifest in host.registry.list():
            try:
                await host.activate(manifest.id)
            except Exception:
                logger.exception(
                    "build_full_tool_registry: failed to activate plugin=%s, skipping",
                    manifest.id,
                )
                continue

        for tool_cls in host.get_tool_providers():
            try:
                adapted = LegacyToolAdapter(tool_cls)
                registry.register_tool(adapted)
                logger.debug(
                    "build_full_tool_registry: registered plugin tool=%s", adapted.name
                )
            except Exception:
                logger.exception(
                    "build_full_tool_registry: failed to adapt tool=%s, skipping",
                    getattr(tool_cls, "name", tool_cls.__name__),
                )

        logger.info(
            "build_full_tool_registry: total tools=%d (%d standard + %d plugin)",
            len(registry.list_tools()),
            20,  # approximate standard count
            len(host.get_tool_providers()),
        )

    return registry


def create_agent_v2(
    config: Config,
    tool_registry: ToolRegistryV2 | None = None,
    permissions: list[Ruleset] | None = None,
    mode: str | None = None,
) -> AgentV2:
    """Build an AgentV2 from a Config object.

    Steps:
      1. Resolve API key (config → env fallback → empty)
      2. Resolve provider + model → Route
      3. Create LLMClient from Route
      4. Create ToolRegistry with all standard tools
      5. Return AgentV2(llm_client, tool_registry, system_prompt)

    Args:
        config: Application configuration (provider, model, api_key, etc.).
        tool_registry: Optional pre-configured tool registry.
                       Defaults to create_tool_registry().
        permissions: Optional permission rulesets. When provided, only
                     tools matching an ALLOW rule are materialized.
        mode: Optional agent mode (build, plan, subagent).

    Returns:
        A fully configured AgentV2 instance.
    """
    from cscode.app.agent import AgentV2

    # Resolve API key with fallback to standard env vars
    api_key = _resolve_api_key(config)
    api_base = config.api_base or ""
    route = resolve_route(
        provider=ProviderID(config.provider),
        model=ModelID(config.model),
        api_key=api_key,
        api_base=api_base,
    )

    logger.info(
        "Creating AgentV2: provider=%s model=%s route=%s mode=%s",
        config.provider, config.model, route.id, mode or "default",
    )

    # Create LLM client
    llm_client = LLMClient(route=route)

    # Create or use provided tool registry
    if tool_registry is None:
        tool_registry = create_tool_registry()

    return AgentV2(
        llm_client=llm_client,
        tool_registry=tool_registry,
        system_prompt=config.system_prompt,
        permissions=permissions,
    )
