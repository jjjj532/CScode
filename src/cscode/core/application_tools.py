"""P2-11: Application Tools — tools that bypass permission prompts.

Application tools are safe, read-only tools (like read, grep, glob, ls)
that do not require user permission confirmation.
"""

from __future__ import annotations

from typing import Final

_APPLICATION_TOOLS: set[str] = {
    "read",
    "grep",
    "glob",
    "ls",
    "search",
    "websearch",
    "webfetch",
    "lsp",
    "lsp_diagnostics",
    "lsp_symbols",
    "lsp_find_references",
    "lsp_goto_definition",
}

# Public API
APPLICATION_TOOLS: Final[set[str]] = _APPLICATION_TOOLS


def is_application_tool(name: str) -> bool:
    """Check if a tool name is an application-level (safe) tool."""
    return name in _APPLICATION_TOOLS


def register_application_tool(name: str) -> None:
    """Register a new tool as an application-level tool."""
    _APPLICATION_TOOLS.add(name)


def get_application_tools() -> list[str]:
    """Return sorted list of all registered application-level tools."""
    return sorted(_APPLICATION_TOOLS)
