"""Tests for PluginAPI — registration, UI extensions, and hooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from cscode.core.events import Event, EventBus
from cscode.core.plugin.api import (
    CommandDef,
    PluginAPI,
    ProviderDef,
    SkillDef,
    UIExtension,
)
from cscode.schema.tool import ToolResult
from cscode.tools.base import BaseTool

# ── Helper: minimal tool for testing ──────────────────────────────────


@dataclass
class _DummyResult:
    success: bool = True
    data: str = ""


class _DummyTool(BaseTool):
    name = "dummy"
    description = "A dummy tool for testing"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data="ok")


class _OtherTool(BaseTool):
    name = "other"
    description = "Another dummy tool"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data="ok")


# ── Tests ─────────────────────────────────────────────────────────────


class TestPluginAPIRegistration:
    def test_register_tool(self) -> None:
        api = PluginAPI()
        api.register_tool(_DummyTool)
        tools = api.get_tools()
        assert len(tools) == 1
        assert tools[0] is _DummyTool

    def test_register_tool_duplicate_raises(self) -> None:
        api = PluginAPI()
        api.register_tool(_DummyTool)
        with pytest.raises(ValueError, match="already registered"):
            api.register_tool(_DummyTool)

    def test_multiple_tools(self) -> None:
        api = PluginAPI()
        api.register_tool(_DummyTool)
        api.register_tool(_OtherTool)
        assert len(api.get_tools()) == 2

    def test_register_command(self) -> None:
        api = PluginAPI()
        cmd = CommandDef(name="deploy", description="Deploy the app")
        api.register_command(cmd)
        commands = api.get_commands()
        assert len(commands) == 1
        assert commands[0].name == "deploy"

    def test_register_command_duplicate_raises(self) -> None:
        api = PluginAPI()
        api.register_command(CommandDef(name="deploy", description=""))
        with pytest.raises(ValueError, match="already registered"):
            api.register_command(CommandDef(name="deploy", description="dup"))

    def test_register_provider(self) -> None:
        api = PluginAPI()
        api.register_provider(ProviderDef(name="my-provider"))
        providers = api.get_providers()
        assert len(providers) == 1
        assert providers[0].name == "my-provider"

    def test_register_provider_duplicate_raises(self) -> None:
        api = PluginAPI()
        api.register_provider(ProviderDef(name="p1"))
        with pytest.raises(ValueError, match="already registered"):
            api.register_provider(ProviderDef(name="p1"))

    def test_register_skill(self) -> None:
        api = PluginAPI()
        api.register_skill(SkillDef(name="my-skill", description="A skill"))
        skills = api.get_skills()
        assert len(skills) == 1
        assert skills[0].name == "my-skill"

    def test_register_skill_duplicate_raises(self) -> None:
        api = PluginAPI()
        api.register_skill(SkillDef(name="s1", description=""))
        with pytest.raises(ValueError, match="already registered"):
            api.register_skill(SkillDef(name="s1", description="dup"))


class TestPluginAPIUIExtensions:
    def test_add_tui_panel(self) -> None:
        api = PluginAPI()
        panel = UIExtension(layer="tui", extension_id="my-panel", title="My Panel")
        api.add_tui_panel(panel)
        extensions = api.get_ui_extensions()
        assert len(extensions) == 1
        assert extensions[0].layer == "tui"
        assert extensions[0].extension_id == "my-panel"

    def test_add_web_route(self) -> None:
        api = PluginAPI()
        route = UIExtension(layer="web", extension_id="my-route")
        api.add_web_route(route)
        extensions = api.get_ui_extensions("web")
        assert len(extensions) == 1
        assert extensions[0].layer == "web"

    def test_add_cli_group(self) -> None:
        api = PluginAPI()
        group = UIExtension(layer="cli", extension_id="my-group")
        api.add_cli_group(group)
        extensions = api.get_ui_extensions("cli")
        assert len(extensions) == 1

    def test_get_extensions_filtered_by_layer(self) -> None:
        api = PluginAPI()
        api.add_tui_panel(UIExtension(layer="tui", extension_id="p1"))
        api.add_web_route(UIExtension(layer="web", extension_id="r1"))
        api.add_cli_group(UIExtension(layer="cli", extension_id="g1"))

        assert len(api.get_ui_extensions("tui")) == 1
        assert len(api.get_ui_extensions("web")) == 1
        assert len(api.get_ui_extensions("cli")) == 1
        assert len(api.get_ui_extensions()) == 3

    def test_add_tui_panel_duplicate_raises(self) -> None:
        api = PluginAPI()
        api.add_tui_panel(UIExtension(layer="tui", extension_id="p1"))
        with pytest.raises(ValueError, match="already registered"):
            api.add_tui_panel(UIExtension(layer="tui", extension_id="p1"))


class TestPluginAPIHooks:
    @pytest.mark.asyncio
    async def test_on_session_start(self) -> None:
        bus = EventBus()
        api = PluginAPI(event_bus=bus)
        received: list[str] = []

        async def handler(event: object) -> None:
            received.append("called")

        api.on_session_start(handler)
        await bus.emit("session.start", Event(type="session.start"))

        assert received == ["called"]

    @pytest.mark.asyncio
    async def test_on_tool_call(self) -> None:
        bus = EventBus()
        api = PluginAPI(event_bus=bus)
        received: list[str] = []

        async def handler(event: object) -> None:
            received.append("tool_call")

        api.on_tool_call(handler)
        await bus.emit("tool.call", Event(type="tool.call"))

        assert received == ["tool_call"]

    @pytest.mark.asyncio
    async def test_on_message(self) -> None:
        bus = EventBus()
        api = PluginAPI(event_bus=bus)
        received: list[str] = []

        async def handler(event: object) -> None:
            received.append("message")

        api.on_message(handler)
        await bus.emit("message", Event(type="message"))  # type: ignore[arg-type]

        assert received == ["message"]

    @pytest.mark.asyncio
    async def test_no_event_bus_no_crash(self) -> None:
        """Without an event bus, hook registration is a no-op."""
        api = PluginAPI(event_bus=None)

        async def handler(event: object) -> None:
            pass

        # Should not raise
        api.on_session_start(handler)
        api.on_tool_call(handler)
        api.on_message(handler)

    def test_empty_stores(self) -> None:
        api = PluginAPI()
        assert api.get_tools() == []
        assert api.get_commands() == []
        assert api.get_providers() == []
        assert api.get_skills() == []
        assert api.get_ui_extensions() == []
