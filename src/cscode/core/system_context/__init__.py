# System Context Algebra System
# Task 1.1: P0.1 - System Context 代数系统
# Based on SPEC.md 2.1.x

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, TypeVar, Union

# === SPEC 2.1.1: UNAVAILABLE Sentinel ===

@dataclass(frozen=True)
class _UnavailableType:
    """Sentinel value indicating context is unavailable"""
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNAVAILABLE"

UNAVAILABLE = _UnavailableType()


# === SPEC 2.1.2: Core Types ===

@dataclass(frozen=True)
class ContextKey:
    """Unique identifier for a context source (namespace/name)"""
    __slots__ = ("_value",)
    _value: str

    def __init__(self, value: str) -> None:
        object.__setattr__(self, "_value", value)

    @property
    def value(self) -> str:
        return self._value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ContextKey):
            return self._value == other._value
        return False

    def __hash__(self) -> int:
        return hash(self._value)

    def __repr__(self) -> str:
        return f"ContextKey({self._value!r})"


@dataclass
class SourceSnapshot:
    """Snapshot of a source's current value"""
    __slots__ = ("value", "loaded_at")
    value: Any
    loaded_at: datetime.datetime


# ContextSource load function type
ContextLoader = Callable[[], Awaitable[Any]]
# Baseline transform function
BaselineFn = Callable[[Any], str]
# Update transform function
UpdateFn = Callable[[Any, Any], str]
# Removed handler function
RemovedFn = Callable[[Any], str]


@dataclass
class ContextSource:
    """A single context source with load/baseline/update logic"""
    key: ContextKey
    load: ContextLoader
    baseline: BaselineFn
    update: UpdateFn
    removed: RemovedFn | None = None


@dataclass
class SystemContext:
    """Container for one or more context sources"""
    __slots__ = ("sources",)
    sources: dict[ContextKey, ContextSource]

    def __init__(
        self,
        sources: dict[ContextKey, ContextSource] | None = None
    ) -> None:
        object.__setattr__(self, "sources", sources or {})


# === SPEC 2.1.3: Factory Functions ===

def make(source: ContextSource) -> SystemContext:
    """Wrap a single source into a SystemContext"""
    return SystemContext({source.key: source})


def combine(contexts: list[SystemContext]) -> SystemContext:
    """Merge multiple SystemContexts, rejecting duplicate keys"""
    merged: dict[ContextKey, ContextSource] = {}

    for ctx in contexts:
        for key, source in ctx.sources.items():
            if key in merged:
                raise ValueError(f"Duplicate key: {key.value}")
            merged[key] = source

    return SystemContext(merged)


# === SPEC 2.1.3: Reconciliation Results ===

@dataclass
class ContextGeneration:
    """Result of initialization: baseline text + snapshot"""
    __slots__ = ("baseline", "snapshot", "updated_keys")
    baseline: str
    snapshot: dict[str, SourceSnapshot]
    updated_keys: set[str]


@dataclass
class Unchanged:
    """No changes detected"""
    __slots__ = ()


@dataclass
class Updated:
    """Value changed, contains update text"""
    __slots__ = ("text",)
    text: str


@dataclass
class ReplacementReady:
    """Ready for replacement with new generation"""
    __slots__ = ("generation",)
    generation: ContextGeneration


@dataclass
class ReplacementBlocked:
    """Replacement blocked (source unavailable)"""
    __slots__ = ()


ReconcileResult = Union[Unchanged, Updated, ReplacementBlocked]
ReplaceResult = Union[ReplacementReady, ReplacementBlocked]


# === SPEC 2.1.3: Core Functions ===

async def initialize(ctx: SystemContext) -> ContextGeneration:
    """Initialize all sources, creating baseline and snapshot"""
    baseline_parts: list[str] = []
    snapshot: dict[str, SourceSnapshot] = {}
    updated_keys: set[str] = set()

    for key, source in ctx.sources.items():
        try:
            value = await source.load()

            # Handle UNAVAILABLE
            if value is UNAVAILABLE:
                baseline_parts.append("")
                snapshot[key.value] = SourceSnapshot(
                    value=UNAVAILABLE,
                    loaded_at=datetime.datetime.now()
                )
            else:
                text = source.baseline(value)
                baseline_parts.append(text)
                snapshot[key.value] = SourceSnapshot(
                    value=value,
                    loaded_at=datetime.datetime.now()
                )
                updated_keys.add(key.value)
        except Exception:
            # On error, use empty baseline but still record
            baseline_parts.append("")
            snapshot[key.value] = SourceSnapshot(
                value=UNAVAILABLE,
                loaded_at=datetime.datetime.now()
            )

    return ContextGeneration(
        baseline="\n".join(baseline_parts),
        snapshot=snapshot,
        updated_keys=updated_keys,
    )


async def reconcile(
    ctx: SystemContext,
    previous_snapshot: dict[str, SourceSnapshot]
) -> ReconcileResult:
    """Compare current values with previous snapshot"""
    for key, source in ctx.sources.items():
        try:
            value = await source.load()

            # Check for UNAVAILABLE
            if value is UNAVAILABLE:
                return ReplacementBlocked()

            prev = previous_snapshot.get(key.value)
            if prev is None or prev.value is UNAVAILABLE:
                # New or was unavailable - use baseline
                text = source.baseline(value)
                return Updated(text=text)

            if prev.value != value:
                # Changed - use update function
                text = source.update(prev.value, value)
                return Updated(text=text)
            # Otherwise unchanged - continue checking

        except Exception:
            return ReplacementBlocked()

    return Unchanged()


async def replace(
    ctx: SystemContext,
    previous_snapshot: dict[str, SourceSnapshot]
) -> ReplaceResult:
    """Create new generation for replacement"""
    for key, source in ctx.sources.items():
        try:
            value = await source.load()

            if value is UNAVAILABLE:
                return ReplacementBlocked()

        except Exception:
            return ReplacementBlocked()

    # All sources available - create new generation
    generation = await initialize(ctx)
    return ReplacementReady(generation=generation)


# === SPEC 2.1.4: Built-in Sources ===

def create_builtin_context() -> SystemContext:
    """Create context with built-in sources: environment, date, instructions"""

    async def load_environment() -> dict[str, str]:
        import platform
        return {
            "os": os.name,
            "platform": platform.system(),
            "cwd": os.getcwd(),
        }

    def baseline_env(env: dict[str, str]) -> str:
        return f"Environment: {env.get('os', 'unknown')}/{env.get('platform', 'unknown')}"

    def update_env(old: dict, new: dict) -> str:
        changes = []
        for k in set(old.keys()) | set(new.keys()):
            if old.get(k) != new.get(k):
                changes.append(f"{k}: {old.get(k)} -> {new.get(k)}")
        return f"Environment changed: {', '.join(changes) if changes else 'none'}"

    env_source = ContextSource(
        key=ContextKey("core/environment"),
        load=load_environment,
        baseline=baseline_env,
        update=update_env,
    )

    async def load_date() -> str:
        return datetime.datetime.now().isoformat()

    def baseline_date(dt: str) -> str:
        return f"Current date: {dt}"

    def update_date(old: str, new: str) -> str:
        return f"Date changed: {old} -> {new}"

    date_source = ContextSource(
        key=ContextKey("core/date"),
        load=load_date,
        baseline=baseline_date,
        update=update_date,
    )

    async def load_instructions() -> str:
        # Could load from config or files
        return "You are a helpful coding assistant."

    def baseline_instructions(text: str) -> str:
        return f"Instructions: {text}"

    def update_instructions(old: str, new: str) -> str:
        return "Instructions updated"

    instructions_source = ContextSource(
        key=ContextKey("core/instructions"),
        load=load_instructions,
        baseline=baseline_instructions,
        update=update_instructions,
    )

    return combine([
        make(env_source),
        make(date_source),
        make(instructions_source),
    ])
