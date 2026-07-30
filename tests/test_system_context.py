"""Tests for System Context Algebra (cscode.core.system_context).

Tests verify SPEC §2.1:
- ContextKey identity and hashing
- ContextSource composition (make/combine)
- initialize() creates baseline + snapshot
- reconcile() detects changes
- replace() creates new generation
- Built-in context sources
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from cscode.core.system_context import (
    UNAVAILABLE,
    ContextGeneration,
    ContextKey,
    ContextSource,
    ReconcileResult,
    ReplaceResult,
    ReplacementBlocked,
    ReplacementReady,
    SourceSnapshot,
    SystemContext,
    Unchanged,
    Updated,
    combine,
    create_builtin_context,
    initialize,
    make,
    reconcile,
    replace,
)


# ═══════════════════════════════════════════════════════════════════
# ContextKey
# ═══════════════════════════════════════════════════════════════════

class TestContextKey:
    def test_create(self) -> None:
        k = ContextKey("core/environment")
        assert k.value == "core/environment"

    def test_equality_same_value(self) -> None:
        assert ContextKey("a/b") == ContextKey("a/b")

    def test_equality_different_value(self) -> None:
        assert ContextKey("a/b") != ContextKey("c/d")

    def test_equality_with_non_contextkey(self) -> None:
        assert ContextKey("a/b") != "a/b"

    def test_hashable(self) -> None:
        s = {ContextKey("a"), ContextKey("b"), ContextKey("a")}
        assert len(s) == 2

    def test_repr(self) -> None:
        k = ContextKey("ns/name")
        assert "ns/name" in repr(k)


# ═══════════════════════════════════════════════════════════════════
# SourceSnapshot
# ═══════════════════════════════════════════════════════════════════

class TestSourceSnapshot:
    def test_create(self) -> None:
        import datetime
        now = datetime.datetime.now()
        s = SourceSnapshot(value="hello", loaded_at=now)
        assert s.value == "hello"
        assert s.loaded_at is now


# ═══════════════════════════════════════════════════════════════════
# ContextSource
# ═══════════════════════════════════════════════════════════════════

class TestContextSource:
    @pytest.mark.asyncio
    async def test_create_and_load(self) -> None:
        async def loader() -> str:
            return "value"
        source = ContextSource(
            key=ContextKey("test/key"),
            load=loader,
            baseline=lambda v: f"Base: {v}",
            update=lambda o, n: f"Updated: {o} -> {n}",
        )
        assert source.key.value == "test/key"
        result = await source.load()
        assert result == "value"

    @pytest.mark.asyncio
    async def test_with_removed_handler(self) -> None:
        async def loader() -> str:
            return "val"
        source = ContextSource(
            key=ContextKey("test/removable"),
            load=loader,
            baseline=lambda v: f"Base: {v}",
            update=lambda o, n: f"Updated",
            removed=lambda v: f"Removed: {v}",
        )
        assert source.removed is not None
        assert source.removed("x") == "Removed: x"


# ═══════════════════════════════════════════════════════════════════
# SystemContext / make / combine
# ═══════════════════════════════════════════════════════════════════

class TestSystemContext:
    def test_make_wraps_source(self) -> None:
        async def loader() -> str:
            return "x"
        source = ContextSource(
            key=ContextKey("a"),
            load=loader,
            baseline=lambda v: v,
            update=lambda o, n: n,
        )
        ctx = make(source)
        assert isinstance(ctx, SystemContext)
        assert ContextKey("a") in ctx.sources

    def test_combine_merges(self) -> None:
        async def loader_a() -> str:
            return "a"
        async def loader_b() -> str:
            return "b"
        a = make(ContextSource(
            key=ContextKey("a"), load=loader_a,
            baseline=lambda v: v, update=lambda o, n: n,
        ))
        b = make(ContextSource(
            key=ContextKey("b"), load=loader_b,
            baseline=lambda v: v, update=lambda o, n: n,
        ))
        combined = combine([a, b])
        assert len(combined.sources) == 2

    def test_combine_rejects_duplicates(self) -> None:
        async def loader() -> str:
            return "x"
        a = make(ContextSource(
            key=ContextKey("dup"), load=loader,
            baseline=lambda v: v, update=lambda o, n: n,
        ))
        b = make(ContextSource(
            key=ContextKey("dup"), load=loader,
            baseline=lambda v: v, update=lambda o, n: n,
        ))
        with pytest.raises(ValueError, match="Duplicate key"):
            combine([a, b])

    def test_system_context_empty_sources(self) -> None:
        ctx = SystemContext()
        assert ctx.sources == {}


# ═══════════════════════════════════════════════════════════════════
# Result types
# ═══════════════════════════════════════════════════════════════════

class TestResultTypes:
    def test_unchanged_is_dataclass(self) -> None:
        u = Unchanged()
        assert isinstance(u, Unchanged)

    def test_updated_has_text(self) -> None:
        u = Updated(text="change detected")
        assert u.text == "change detected"

    def test_replacement_ready_has_generation(self) -> None:
        gen = ContextGeneration(
            baseline="base", snapshot={}, updated_keys=set()
        )
        r = ReplacementReady(generation=gen)
        assert r.generation.baseline == "base"

    def test_replacement_blocked(self) -> None:
        r = ReplacementBlocked()
        assert isinstance(r, ReplacementBlocked)

    def test_result_type_alias(self) -> None:
        """ReconcileResult should accept all variants."""
        results: list[ReconcileResult] = [
            Unchanged(),
            Updated(text="x"),
            ReplacementBlocked(),
        ]
        assert len(results) == 3

    def test_replace_result_alias(self) -> None:
        gen = ContextGeneration(
            baseline="b", snapshot={}, updated_keys=set()
        )
        results: list[ReplaceResult] = [
            ReplacementReady(generation=gen),
            ReplacementBlocked(),
        ]
        assert len(results) == 2

    def test_context_generation_fields(self) -> None:
        gen = ContextGeneration(
            baseline="baseline text",
            snapshot={"k": SourceSnapshot(value="v", loaded_at=__import__("datetime").datetime.now())},
            updated_keys={"k"},
        )
        assert gen.baseline == "baseline text"
        assert gen.snapshot["k"].value == "v"
        assert gen.updated_keys == {"k"}


# ═══════════════════════════════════════════════════════════════════
# initialize()
# ═══════════════════════════════════════════════════════════════════

class TestInitialize:
    @pytest.mark.asyncio
    async def test_single_source_initializes(self) -> None:
        async def loader() -> str:
            return "hello"
        source = ContextSource(
            key=ContextKey("greeting"),
            load=loader,
            baseline=lambda v: f"Greeting: {v}",
            update=lambda o, n: f"Changed: {o} -> {n}",
        )
        ctx = make(source)
        generation = await initialize(ctx)
        assert "Greeting: hello" in generation.baseline
        assert ContextKey("greeting").value in generation.snapshot
        assert ContextKey("greeting").value in generation.updated_keys

    @pytest.mark.asyncio
    async def test_multiple_sources(self) -> None:
        async def load_a() -> str:
            return "A"
        async def load_b() -> str:
            return "B"
        ctx = combine([
            make(ContextSource(
                key=ContextKey("a"), load=load_a,
                baseline=lambda v: v, update=lambda o, n: n,
            )),
            make(ContextSource(
                key=ContextKey("b"), load=load_b,
                baseline=lambda v: v, update=lambda o, n: n,
            )),
        ])
        generation = await initialize(ctx)
        assert "A" in generation.baseline
        assert "B" in generation.baseline
        assert len(generation.snapshot) == 2

    @pytest.mark.asyncio
    async def test_unavailable_source(self) -> None:
        async def loader() -> type[UNAVAILABLE]:  # type: ignore[valid-type]
            return UNAVAILABLE
        source = ContextSource(
            key=ContextKey("unavail"),
            load=loader,
            baseline=lambda v: "should not appear",
            update=lambda o, n: "nope",
        )
        generation = await initialize(make(source))
        snapshot = generation.snapshot[ContextKey("unavail").value]
        assert snapshot.value is UNAVAILABLE

    @pytest.mark.asyncio
    async def test_loader_error_graceful(self) -> None:
        async def loader() -> str:
            raise RuntimeError("connection failed")
        source = ContextSource(
            key=ContextKey("broken"),
            load=loader,
            baseline=lambda v: "never called",
            update=lambda o, n: "never called",
        )
        generation = await initialize(make(source))
        snapshot = generation.snapshot[ContextKey("broken").value]
        assert snapshot.value is UNAVAILABLE  # Error → UNAVAILABLE

    @pytest.mark.asyncio
    async def test_empty_context(self) -> None:
        ctx = SystemContext()
        generation = await initialize(ctx)
        assert generation.baseline == ""
        assert generation.snapshot == {}
        assert generation.updated_keys == set()


# ═══════════════════════════════════════════════════════════════════
# reconcile()
# ═══════════════════════════════════════════════════════════════════

class TestReconcile:
    @pytest.mark.asyncio
    async def test_unchanged(self) -> None:
        async def loader() -> str:
            return "stable"
        source = ContextSource(
            key=ContextKey("data"),
            load=loader,
            baseline=lambda v: f"Baseline: {v}",
            update=lambda o, n: f"Updated: {o} -> {n}",
        )
        ctx = make(source)
        prev_gen = await initialize(ctx)
        result = await reconcile(ctx, prev_gen.snapshot)
        assert isinstance(result, Unchanged)

    @pytest.mark.asyncio
    async def test_updated(self) -> None:
        call_count = 0
        async def loader() -> str:
            nonlocal call_count
            call_count += 1
            return f"v{call_count}"
        source = ContextSource(
            key=ContextKey("versioned"),
            load=loader,
            baseline=lambda v: v,
            update=lambda o, n: f"{o}->{n}",
        )
        ctx = make(source)
        prev_gen = await initialize(ctx)
        # Call again — value changes from v1 to v2
        result = await reconcile(ctx, prev_gen.snapshot)
        assert isinstance(result, Updated)
        assert "v1->v2" in result.text or "v1" in result.text

    @pytest.mark.asyncio
    async def test_new_source_in_snapshot(self) -> None:
        """If a key was not in the previous snapshot, use baseline."""
        async def loader() -> str:
            return "new"
        source = ContextSource(
            key=ContextKey("new_key"),
            load=loader,
            baseline=lambda v: f"First time: {v}",
            update=lambda o, n: f"Update: {n}",
        )
        ctx = make(source)
        result = await reconcile(ctx, {})
        assert isinstance(result, Updated)
        assert "First time" in result.text

    @pytest.mark.asyncio
    async def test_unavailable_returns_blocked(self) -> None:
        async def loader() -> type[UNAVAILABLE]:  # type: ignore[valid-type]
            return UNAVAILABLE
        source = ContextSource(
            key=ContextKey("gone"),
            load=loader,
            baseline=lambda v: "",
            update=lambda o, n: "",
        )
        ctx = make(source)
        result = await reconcile(ctx, {})
        assert isinstance(result, ReplacementBlocked)

    @pytest.mark.asyncio
    async def test_loader_error_returns_blocked(self) -> None:
        async def loader() -> str:
            raise RuntimeError("fail")
        source = ContextSource(
            key=ContextKey("err"),
            load=loader,
            baseline=lambda v: "",
            update=lambda o, n: "",
        )
        ctx = make(source)
        result = await reconcile(ctx, {})
        assert isinstance(result, ReplacementBlocked)


# ═══════════════════════════════════════════════════════════════════
# replace()
# ═══════════════════════════════════════════════════════════════════

class TestReplace:
    @pytest.mark.asyncio
    async def test_replace_ready(self) -> None:
        async def loader() -> str:
            return "data"
        source = ContextSource(
            key=ContextKey("k"),
            load=loader,
            baseline=lambda v: v,
            update=lambda o, n: n,
        )
        ctx = make(source)
        result = await replace(ctx, {})
        assert isinstance(result, ReplacementReady)
        assert result.generation.baseline == "data"

    @pytest.mark.asyncio
    async def test_replace_unavailable_blocked(self) -> None:
        async def loader() -> type[UNAVAILABLE]:  # type: ignore[valid-type]
            return UNAVAILABLE
        source = ContextSource(
            key=ContextKey("k"),
            load=loader,
            baseline=lambda v: "",
            update=lambda o, n: "",
        )
        ctx = make(source)
        result = await replace(ctx, {})
        assert isinstance(result, ReplacementBlocked)

    @pytest.mark.asyncio
    async def test_replace_loader_error_blocked(self) -> None:
        async def loader() -> str:
            raise RuntimeError("fail")
        source = ContextSource(
            key=ContextKey("k"),
            load=loader,
            baseline=lambda v: "",
            update=lambda o, n: "",
        )
        ctx = make(source)
        result = await replace(ctx, {})
        assert isinstance(result, ReplacementBlocked)


# ═══════════════════════════════════════════════════════════════════
# create_builtin_context()
# ═══════════════════════════════════════════════════════════════════

class TestCreateBuiltinContext:
    def test_returns_system_context(self) -> None:
        ctx = create_builtin_context()
        assert isinstance(ctx, SystemContext)

    def test_has_core_sources(self) -> None:
        ctx = create_builtin_context()
        keys = [k.value for k in ctx.sources]
        assert "core/environment" in keys
        assert "core/date" in keys
        assert "core/instructions" in keys

    def test_all_sources_have_load_baseline_update(self) -> None:
        ctx = create_builtin_context()
        for key, source in ctx.sources.items():
            assert source.load is not None
            assert source.baseline is not None
            assert source.update is not None

    @pytest.mark.asyncio
    async def test_initialize_works(self) -> None:
        ctx = create_builtin_context()
        gen = await initialize(ctx)
        assert gen.baseline
        assert "Environment" in gen.baseline
        assert "Current date" in gen.baseline
        assert "Instructions" in gen.baseline
        assert len(gen.snapshot) == 3


# ═══════════════════════════════════════════════════════════════════
# UNAVAILABLE sentinel
# ═══════════════════════════════════════════════════════════════════

class TestUnavailable:
    def test_is_singleton(self) -> None:
        assert UNAVAILABLE is UNAVAILABLE

    def test_repr(self) -> None:
        assert repr(UNAVAILABLE) == "UNAVAILABLE"
