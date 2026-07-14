"""PluginAPI — public API surface visible to plugins during lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cscode.core.events import EventBus
from cscode.core.plugin.hooks import HookPoint, HookRegistry
from cscode.tools.base import BaseTool


@dataclass
class CommandDef:
    """CLI command definition registered by a plugin."""

    name: str
    description: str
    plugin_id: str = ""


@dataclass
class UIExtension:
    """UI extension point registered by a plugin."""

    layer: str  # "tui", "cli", "web"
    extension_id: str
    title: str = ""
    plugin_id: str = ""


@dataclass
class SkillDef:
    """Skill definition registered by a plugin."""

    name: str
    description: str
    plugin_id: str = ""


@dataclass
class ProviderDef:
    """LLM provider definition registered by a plugin."""

    name: str
    plugin_id: str = ""


class PluginAPI:
    """Public API that plugins call during activation.

    Provides registration methods for tools, commands, providers, skills,
    UI extensions, and hook handlers.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._event_bus = event_bus
        self._hook_registry = HookRegistry(event_bus) if event_bus else None

        # Registration stores
        self._tools: dict[str, type[BaseTool]] = {}
        self._commands: dict[str, CommandDef] = {}
        self._providers: dict[str, ProviderDef] = {}
        self._skills: dict[str, SkillDef] = {}
        self._ui_extensions: dict[str, UIExtension] = {}

    # ── Registration ──────────────────────────────────────────────────

    def register_tool(self, tool: type[BaseTool]) -> None:
        """Register a tool class."""
        name = getattr(tool, "name", tool.__name__.lower())
        if name in self._tools:
            msg = f"Tool '{name}' already registered"
            raise ValueError(msg)
        self._tools[name] = tool

    def register_command(self, cmd: CommandDef) -> None:
        """Register a CLI command."""
        if cmd.name in self._commands:
            msg = f"Command '{cmd.name}' already registered"
            raise ValueError(msg)
        self._commands[cmd.name] = cmd

    def register_provider(self, provider: ProviderDef) -> None:
        """Register an LLM provider."""
        if provider.name in self._providers:
            msg = f"Provider '{provider.name}' already registered"
            raise ValueError(msg)
        self._providers[provider.name] = provider

    def register_skill(self, skill: SkillDef) -> None:
        """Register a skill."""
        if skill.name in self._skills:
            msg = f"Skill '{skill.name}' already registered"
            raise ValueError(msg)
        self._skills[skill.name] = skill

    # ── UI Extensions ─────────────────────────────────────────────────

    def add_tui_panel(self, panel: UIExtension) -> None:
        """Register a TUI panel extension."""
        panel.layer = "tui"
        key = f"tui:{panel.extension_id}"
        if key in self._ui_extensions:
            msg = f"TUI panel '{panel.extension_id}' already registered"
            raise ValueError(msg)
        self._ui_extensions[key] = panel

    def add_web_route(self, route: UIExtension) -> None:
        """Register a web route extension."""
        route.layer = "web"
        key = f"web:{route.extension_id}"
        if key in self._ui_extensions:
            msg = f"Web route '{route.extension_id}' already registered"
            raise ValueError(msg)
        self._ui_extensions[key] = route

    def add_cli_group(self, group: UIExtension) -> None:
        """Register a CLI command group extension."""
        group.layer = "cli"
        key = f"cli:{group.extension_id}"
        if key in self._ui_extensions:
            msg = f"CLI group '{group.extension_id}' already registered"
            raise ValueError(msg)
        self._ui_extensions[key] = group

    # ── Hook Handlers ─────────────────────────────────────────────────

    def on_session_start(self, handler: Callable[..., Any]) -> None:
        """Register a handler for session start events."""
        if self._hook_registry:
            self._hook_registry.register(HookPoint.SESSION_START, handler)

    def on_tool_call(self, handler: Callable[..., Any]) -> None:
        """Register a handler for tool call events."""
        if self._hook_registry:
            self._hook_registry.register(HookPoint.TOOL_CALL, handler)

    def on_message(self, handler: Callable[..., Any]) -> None:
        """Register a handler for message events."""
        if self._hook_registry:
            self._hook_registry.register(HookPoint.MESSAGE, handler)

    # ── Queries ───────────────────────────────────────────────────────

    def get_tools(self) -> list[type[BaseTool]]:
        """Return all registered tool classes."""
        return list(self._tools.values())

    def get_commands(self) -> list[CommandDef]:
        """Return all registered command definitions."""
        return list(self._commands.values())

    def get_providers(self) -> list[ProviderDef]:
        """Return all registered provider definitions."""
        return list(self._providers.values())

    def get_skills(self) -> list[SkillDef]:
        """Return all registered skill definitions."""
        return list(self._skills.values())

    def get_ui_extensions(self, layer: str | None = None) -> list[UIExtension]:
        """Return UI extensions, optionally filtered by layer."""
        if layer is None:
            return list(self._ui_extensions.values())
        return [e for e in self._ui_extensions.values() if e.layer == layer]
