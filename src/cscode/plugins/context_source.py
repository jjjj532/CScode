"""PluginContextSource — plugin-defined system context sources.

These integrate with the System Context algebra (core/system_context/)
to allow plugins to contribute dynamic context.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from cscode.core.system_context import (
    ContextKey,
    ContextSource,
    SystemContext,
    combine,
    make,
)


@dataclass
class PluginContextSource:
    """A system context source defined by a plugin.

    Follows the same pattern as ContextSource from core/system_context/
    but uses string keys (namespace/name) instead of ContextKey objects.
    """

    key: str
    """Context key identifier, e.g. 'plugin/my-feature'."""

    load: Callable[[], Awaitable[str]]
    """Async loader that returns the current value."""

    baseline: Callable[[str], str]
    """Render the value for the first time (baseline)."""

    update: Callable[[str, str], str]
    """Render an updated value given (previous, current)."""

    removed: Callable[[str], str] | None = None
    """Optional render when the source is removed."""


async def to_system_context(sources: list[PluginContextSource]) -> SystemContext:
    """Convert plugin context sources into a SystemContext.

    Each PluginContextSource is mapped to a ContextSource with:
    - ContextKey derived from the string key
    - Same load/baseline/update/removed functions preserved

    Args:
        sources: List of plugin context sources to convert.

    Returns:
        A SystemContext containing all converted sources.

    Raises:
        ValueError: If duplicate keys are encountered (via combine()).
    """
    contexts: list[SystemContext] = []
    for src in sources:
        ctx_source = ContextSource(
            key=ContextKey(src.key),
            load=src.load,
            baseline=src.baseline,
            update=src.update,
            removed=src.removed,
        )
        contexts.append(make(ctx_source))
    return combine(contexts)
