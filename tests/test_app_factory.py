"""Tests for app factory — create_tool_registry, build_full_tool_registry.

RED phase: build_full_tool_registry doesn't exist in factory.py yet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cscode.schema.tool import ToolResult as V1ToolResult
from cscode.tools.base import BaseTool


# ── Helper: create a minimal plugin directory ──────────────────────────


def _create_plugin_dir(tmp_path: Path, name: str) -> Path:
    """Create a minimal plugin dir with a single tool (PluginHost-compatible)."""
    plugin_dir = tmp_path / name
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text(f"""
from cscode.tools.base import BaseTool, ToolResult

class {name}Tool(BaseTool):
    name = "{name}"
    description = "A test plugin tool"
    parameters = {{
        "type": "object",
        "properties": {{
            "msg": {{"type": "string", "description": "A message"}},
        }},
        "required": ["msg"],
    }}

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data=f"{{args['msg']}} from {{self.name}}")

def activate(api):
    api.register_tool({name}Tool)
""")
    return plugin_dir


# ── Tests ──────────────────────────────────────────────────────────────


class TestBuildFullToolRegistry:
    """Tests for factory.build_full_tool_registry()."""

    async def test_returns_tool_registry_v2(self) -> None:
        """Returns a ToolRegistryV2 instance."""
        from cscode.app.factory import build_full_tool_registry
        from cscode.core.tool_registry import ToolRegistryV2

        registry = await build_full_tool_registry()
        assert isinstance(registry, ToolRegistryV2)

    async def test_contains_standard_tools(self) -> None:
        """Registry contains standard v2 tools (read, write, bash, etc.)."""
        from cscode.app.factory import build_full_tool_registry

        registry = await build_full_tool_registry()
        names = registry.list_tools()
        assert "read" in names
        assert "write" in names
        assert "bash" in names
        assert "edit" in names
        assert "grep" in names

    async def test_no_plugin_dir_adds_no_plugin_tools(self) -> None:
        """Without plugin_dirs, registry has only standard tools."""
        from cscode.app.factory import build_full_tool_registry, create_tool_registry

        with_plugins = await build_full_tool_registry()
        without_plugins = create_tool_registry()

        # Should have at least as many tools as the standard registry
        assert len(with_plugins.list_tools()) >= len(without_plugins.list_tools())

    async def test_plugin_tool_is_wrapped_in_registry(self, tmp_path: Path) -> None:
        """Plugin tool from a directory appears in the registry."""
        _create_plugin_dir(tmp_path, "greeter")
        from cscode.app.factory import build_full_tool_registry

        registry = await build_full_tool_registry(plugin_dirs=[str(tmp_path)])
        names = registry.list_tools()
        assert "greeter" in names

    async def test_plugin_tool_executes_through_settle(self, tmp_path: Path) -> None:
        """Plugin tool can be executed via registry.materialize().settle()."""
        _create_plugin_dir(tmp_path, "greeter")
        from cscode.app.factory import build_full_tool_registry

        registry = await build_full_tool_registry(plugin_dirs=[str(tmp_path)])
        mat = registry.materialize()

        result = await mat.settle("greeter", {"msg": "hello"})
        assert result.success
        assert result.data is not None
        assert "hello from greeter" in str(result.data)

    async def test_multiple_plugin_tools(self, tmp_path: Path) -> None:
        """Multiple plugin directories each contribute their tools."""
        _create_plugin_dir(tmp_path, "alpha")
        _create_plugin_dir(tmp_path, "beta")
        from cscode.app.factory import build_full_tool_registry

        registry = await build_full_tool_registry(plugin_dirs=[str(tmp_path)])
        names = registry.list_tools()
        assert "alpha" in names
        assert "beta" in names

    async def test_invalid_plugin_dir_does_not_crash(self) -> None:
        """Non-existent plugin dir is silently skipped."""
        from cscode.app.factory import build_full_tool_registry

        registry = await build_full_tool_registry(
            plugin_dirs=["/tmp/nonexistent_plugins_xyz"]
        )
        assert registry is not None
        assert len(registry.list_tools()) > 0

    async def test_plugin_activation_failure_does_not_block(self, tmp_path: Path) -> None:
        """A plugin that fails to activate still allows other plugins."""
        _create_plugin_dir(tmp_path, "working")
        broken_plugin = tmp_path / "broken"
        broken_plugin.mkdir()
        (broken_plugin / "__init__.py").write_text("raise ImportError('broken!')")

        from cscode.app.factory import build_full_tool_registry

        registry = await build_full_tool_registry(plugin_dirs=[str(tmp_path)])
        names = registry.list_tools()
        assert "working" in names
