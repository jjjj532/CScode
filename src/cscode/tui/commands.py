"""CommandRegistry — TUI 命令面板注册表（spec §5.2）。

内置命令与插件命令统一注册，按类别分组，支持别名。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True, slots=True)
class CommandDef:
    """A registered TUI command."""

    name: str
    handler: Callable[[str], Coroutine[object, object, None] | None]
    category: str = "general"
    aliases: tuple[str, ...] = ()
    plugin_id: str = ""


class CommandRegistry:
    """Name → CommandDef registry with category grouping and dispatch."""

    def __init__(self) -> None:
        self._commands: dict[str, CommandDef] = {}

    def register(
        self,
        name: str,
        handler: Callable[[str], Coroutine[object, object, None] | None],
        category: str = "general",
        aliases: list[str] | None = None,
        plugin_id: str = "",
    ) -> CommandDef:
        """Register a command. Names are normalized to start with ``/``."""
        cmd = CommandDef(
            name=_normalize(name),
            handler=handler,
            category=category,
            aliases=tuple(_normalize(a) for a in (aliases or [])),
            plugin_id=plugin_id,
        )
        for key in (cmd.name, *cmd.aliases):
            self._commands[key] = cmd
        return cmd

    def unregister(self, name: str) -> None:
        """Remove a command (and its aliases) by its canonical name."""
        cmd = self._commands.pop(_normalize(name), None)
        if cmd is None:
            return
        for alias in cmd.aliases:
            self._commands.pop(alias, None)

    def dispatch(self, raw_name: str, args: str = "") -> bool:
        """Dispatch a raw input token (e.g. ``/hello``) to its handler.

        Async handlers are scheduled on the running event loop.
        Returns True if a handler ran, False if unknown.
        """
        cmd = self._commands.get(_normalize(raw_name))
        if cmd is None:
            return False
        result = cmd.handler(args)
        if result is not None:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                asyncio.create_task(result)
        return True

    def list(self) -> List[CommandDef]:
        """Return canonical commands (deduplicated by first registration)."""
        seen: set[str] = set()
        out: list[CommandDef] = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                out.append(cmd)
        return sorted(out, key=lambda c: c.name)

    def by_category(self, category: str) -> List[CommandDef]:
        return [c for c in self.list() if c.category == category]

    def completion_commands(self) -> List[str]:
        """All names + aliases for autocomplete, sorted."""
        out = sorted(self._commands.keys())
        return out


def _normalize(name: str) -> str:
    return name if name.startswith("/") else f"/{name}"
