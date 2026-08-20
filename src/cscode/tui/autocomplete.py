from __future__ import annotations

_COMMANDS: list[str] = [
    "/sessions",
    "/s",
    "/new",
    "/n",
    "/switch",
    "/kill",
    "/delete",
    "/tab",
    "/help",
    "/h",
    "/quit",
    "/exit",
    "/q",
]


class CommandCompleter:
    """Tab-completion engine for TUI chat commands.

    Maintains a list of known commands and provides prefix matching
    with cycle support for repeated Tab presses.

    Usage::

        cc = CommandCompleter()
        cc.find_matches("/s")      # → ["/sessions", "/switch", "/s"]
        cc.next_match()            # → "/sessions"
        cc.next_match()            # → "/switch"
        cc.next_match()            # → "/s"
        cc.next_match()            # → "/sessions" (wraps)
        cc.reset()                 # clear state
    """

    def __init__(self) -> None:
        self._matches: list[str] = []
        self._index: int = -1
        self._extra_commands: list[str] = []

    def set_extra_commands(self, commands: list[str]) -> None:
        """Extend the command list with plugin-registered commands."""
        self._extra_commands = list(commands)

    @staticmethod
    def known_commands() -> list[str]:
        """Return the full list of known commands (including aliases)."""
        return list(_COMMANDS)

    def _all_commands(self) -> list[str]:
        return _COMMANDS + self._extra_commands

    def find_matches(self, prefix: str) -> list[str]:
        """Return commands matching the given prefix and reset cycle state.

        If prefix is empty or does not start with ``/``, returns [].
        """
        self._index = -1
        if not prefix or not prefix.startswith("/"):
            self._matches = []
            return []

        self._matches = sorted(
            cmd for cmd in self._all_commands() if cmd.startswith(prefix)
        )
        return list(self._matches)

    def next_match(self) -> str | None:
        """Return the next match, cycling when reaching the end.

        Returns ``None`` if there are no matches or if ``find_matches``
        has not been called.
        """
        if not self._matches:
            return None

        self._index = (self._index + 1) % len(self._matches)
        return self._matches[self._index]

    def reset(self) -> None:
        """Clear all state. Next ``find_matches`` starts fresh."""
        self._matches = []
        self._index = -1
