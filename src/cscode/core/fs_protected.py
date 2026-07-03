"""Filesystem Protected — Prevent accidental modification of critical files.

P0-6 alignment: protects system directories and sensitive user files
from being modified by write/edit/bash tools.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


def default_protected_paths() -> list[str]:
    """Return the default list of protected path patterns.

    Includes system directories and sensitive user dot-files.
    """
    return [
        # macOS / Linux system directories
        "/usr/",
        "/System/",
        "/etc/",
        "/bin/",
        "/sbin/",
        "/var/",
        "/boot/",
        "/lib/",
        "/lib64/",
        "/opt/",
        "/root/",
        # Sensitive user files
        "**/.ssh/",
        "**/.env",
        "**/.env.local",
        "**/.env.production",
        "**/.gnupg/",
        "**/.git/config",
        "**/.git/credentials",
        "**/.config/",
    ]


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert a protected-path pattern to a compiled regex.

    - ``*`` matches any characters except ``/``
    - ``**`` matches any characters including ``/``
    - ``?`` matches any single char
    - trailing ``/``: pattern must match a directory prefix
    - bare path (no wildcards, contains ``/``): treated as directory prefix
    """
    dir_only = pattern.endswith("/")
    body = pattern.rstrip("/")

    has_glob = "*" in body or "?" in body

    # Escape special regex chars, then expand glob tokens
    parts: list[str] = []
    i = 0
    while i < len(body):
        if body[i : i + 2] == "**":
            parts.append(".*")
            i += 2
        elif body[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif body[i] == "?":
            parts.append(".")
            i += 1
        else:
            parts.append(re.escape(body[i]))
            i += 1

    regex_body = "".join(parts)

    # Bare path with / (e.g., /usr/local) is treated as directory prefix
    treat_as_dir = dir_only or ("/" in body and not has_glob)

    if treat_as_dir:
        return re.compile(rf"\A{regex_body}(?:/.*)?\Z")
    else:
        return re.compile(rf"\A{regex_body}\Z")


def _path_matches_protected(pattern: str, path: str) -> bool:
    """Check if *path* matches a protected-path pattern."""
    if not path.startswith("/"):
        return False

    regex = _pattern_to_regex(pattern)
    return bool(regex.match(path))


@dataclass
class ProtectedPaths:
    """A set of protected path patterns with allow/block overrides.

    Usage::

        p = ProtectedPaths(default_protected_paths())
        p.is_protected("/etc/hosts")       # True
        p.is_protected("/home/user/src")   # False
    """

    protected: list[str] = field(default_factory=list)
    allowlist: list[str] = field(default_factory=list)
    blocklist: list[str] = field(default_factory=list)

    def is_protected(self, path: str) -> bool:
        """Return ``True`` if *path* is protected from modification."""
        # Allowlist takes priority
        for pattern in self.allowlist:
            if _path_matches_protected(pattern, path):
                return False

        # Check protected + blocklist
        for pattern in list(self.protected) + self.blocklist:
            if _path_matches_protected(pattern, path):
                return True

        return False

    def filter(self, paths: list[str]) -> list[str]:
        """Return only paths that are NOT protected."""
        return [p for p in paths if not self.is_protected(p)]
