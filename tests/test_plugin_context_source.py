"""Tests for PluginContextSource → SystemContext conversion.

Tests cover:
1. to_system_context() with empty, single, multiple sources
2. Duplicate key detection via combine()
3. Custom renderers (baseline, update) preserved
4. Removed callback preserved
"""

from __future__ import annotations

import pytest

from cscode.core.system_context import (
    ContextKey,
    SystemContext,
)
from cscode.plugins.context_source import PluginContextSource, to_system_context


class TestToSystemContext:
    async def test_empty_list_returns_empty_context(self) -> None:
        ctx = await to_system_context([])
        assert isinstance(ctx, SystemContext)
        assert len(ctx.sources) == 0

    async def test_single_source(self) -> None:
        async def load_fn() -> str:
            return "running"

        sources = [
            PluginContextSource(
                key="plugin/status",
                load=load_fn,
                baseline=lambda v: f"Status: {v}",
                update=lambda old, new: f"Status: {old} -> {new}",
            )
        ]
        ctx = await to_system_context(sources)
        assert len(ctx.sources) == 1
        assert ContextKey("plugin/status") in ctx.sources

    async def test_multiple_sources(self) -> None:
        async def load_a() -> str:
            return "a"

        async def load_b() -> str:
            return "b"

        sources = [
            PluginContextSource(
                key="plugin/a",
                load=load_a,
                baseline=lambda v: f"a: {v}",
                update=lambda old, new: f"a: {old} -> {new}",
            ),
            PluginContextSource(
                key="plugin/b",
                load=load_b,
                baseline=lambda v: f"b: {v}",
                update=lambda old, new: f"b: {old} -> {new}",
            ),
        ]
        ctx = await to_system_context(sources)
        assert len(ctx.sources) == 2
        assert ContextKey("plugin/a") in ctx.sources
        assert ContextKey("plugin/b") in ctx.sources

    async def test_duplicate_key_raises_value_error(self) -> None:
        async def load_fn() -> str:
            return "v"

        sources = [
            PluginContextSource(
                key="plugin/dup",
                load=load_fn,
                baseline=lambda v: f"v: {v}",
                update=lambda old, new: f"v: {old} -> {new}",
            ),
            PluginContextSource(
                key="plugin/dup",
                load=load_fn,
                baseline=lambda v: f"v: {v}",
                update=lambda old, new: f"v: {old} -> {new}",
            ),
        ]
        with pytest.raises(ValueError, match="Duplicate key"):
            await to_system_context(sources)

    async def test_custom_renderers_preserved(self) -> None:
        async def load_fn() -> str:
            return "ready"

        sources = [
            PluginContextSource(
                key="plugin/custom",
                load=load_fn,
                baseline=lambda v: f"[{v}]",
                update=lambda old, new: f"{old}->{new}",
            ),
        ]
        ctx = await to_system_context(sources)
        src = ctx.sources[ContextKey("plugin/custom")]
        assert src.baseline("ready") == "[ready]"
        assert src.update("a", "b") == "a->b"

    async def test_removed_callback_preserved(self) -> None:
        async def load_fn() -> str:
            return "v"

        removed_called = False

        def removed_fn(v: str) -> str:
            nonlocal removed_called
            removed_called = True
            return f"removed: {v}"

        sources = [
            PluginContextSource(
                key="plugin/temp",
                load=load_fn,
                baseline=lambda v: f"v: {v}",
                update=lambda old, new: f"v: {old} -> {new}",
                removed=removed_fn,
            ),
        ]
        ctx = await to_system_context(sources)
        src = ctx.sources[ContextKey("plugin/temp")]
        assert src.removed is not None
        assert src.removed("x") == "removed: x"
        assert removed_called is True

    async def test_load_function_called_correctly(self) -> None:
        """Verify the async load function still works after conversion."""

        async def load_status() -> str:
            return "active"

        sources = [
            PluginContextSource(
                key="plugin/load-test",
                load=load_status,
                baseline=lambda v: f"load: {v}",
                update=lambda old, new: f"load: {old} -> {new}",
            ),
        ]
        ctx = await to_system_context(sources)
        src = ctx.sources[ContextKey("plugin/load-test")]
        value = await src.load()
        assert value == "active"
