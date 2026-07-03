"""Filesystem Ignore — Respect .gitignore / .opencodeignore rules.

P0-5 alignment: prevents file tools from accessing ignored paths.
Follows gitignore-style pattern syntax.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


# ─── Internal helpers ───────────────────────────────────────────────


def _pattern_matches(pattern: str, path: str) -> bool:
    """Check if a single gitignore-style pattern matches *path*.

    Supports ``*``, ``**``, ``?``, ``[chars]``, ``!`` negation,
    ``#`` comments, and trailing ``/`` (directory-only).
    """
    # Normalise — strip trailing whitespace
    pattern = pattern.rstrip()

    # Empty or comment = no match
    if not pattern or pattern.startswith("#"):
        return False

    # Split into body + directory-only flag
    dir_only = pattern.endswith("/")
    if dir_only:
        pattern = pattern.rstrip("/")

    # If pattern has a leading / or / inside, it's anchored to the root
    anchored = pattern.startswith("/") or "/" in pattern.lstrip("!")
    if pattern.startswith("/"):
        pattern = pattern[1:]

    # For ** patterns, convert to fnmatch-style
    if "**" in pattern:
        return _globstar_match(pattern, path, dir_only, anchored)

    # Directory prefix match: "build" → "build/", "build/file.o" etc.
    if dir_only:
        if path == pattern or path.startswith(pattern + "/"):
            return True

    # Simple fnmatch match (handles *, ?, [chars])
    base = os.path.basename(path) if not anchored else path
    if fnmatch.fnmatch(base, pattern):
        if dir_only and not (path.endswith("/") or os.path.isdir(path)):
            return False
        return True

    # If pattern doesn't contain /, it might match at any level
    if not anchored and "/" not in pattern:
        for part in path.split("/"):
            if fnmatch.fnmatch(part, pattern):
                if dir_only and not (path.endswith("/") or os.path.isdir(path)):
                    continue
                return True

    # Full path match
    if anchored or "/" in pattern:
        if fnmatch.fnmatch(path, pattern):
            if dir_only and not (path.endswith("/") or os.path.isdir(path)):
                return False
            return True

    return False


def _globstar_match(pattern: str, path: str, dir_only: bool, anchored: bool) -> bool:
    """Match patterns containing ``**`` (globstar)."""
    parts = pattern.split("**")
    # If ** is at the end, match everything
    if len(parts) == 2 and parts[1] == "":
        prefix = parts[0].lstrip("/")
        if path.startswith(prefix) or prefix == "":
            if dir_only and not (path.endswith("/") or os.path.isdir(path)):
                return False
            return True
    # If ** is in the middle, check prefix and suffix
    if len(parts) == 2:
        prefix = parts[0].lstrip("/")
        suffix = parts[1]
        if path.startswith(prefix) and path.endswith(suffix):
            middle = path[len(prefix):-len(suffix)] if suffix else path[len(prefix):]
            # ** matches zero or more directory levels
            if "/" not in middle or middle.count("/") >= 0:
                if dir_only and not (path.endswith("/") or os.path.isdir(path)):
                    return False
                return True
    return False


# ─── Public API ─────────────────────────────────────────────────────


@dataclass
class IgnoreRules:
    """A compiled set of gitignore-style rules.

    Usage::

        rules = IgnoreRules(["node_modules/", "*.pyc"])
        rules.is_ignored("src/file.py")          # False
        rules.is_ignored("node_modules/pkg.js")  # True
    """

    patterns: list[str] = field(default_factory=list)
    _compiled: list[tuple[str, bool]] = field(init=False)

    def __post_init__(self) -> None:
        compiled: list[tuple[str, bool]] = []
        for p in self.patterns:
            p_stripped = p.strip()
            if not p_stripped or p_stripped.startswith("#"):
                continue
            is_negation = p_stripped.startswith("!")
            body = p_stripped[1:] if is_negation else p_stripped
            compiled.append((body, is_negation))
        self._compiled = compiled

    def is_ignored(self, path: str) -> bool:
        """Return ``True`` if *path* matches any ignore rule.

        Negation patterns (``!pattern``) override — the last matching
        pattern wins.
        """
        # Normalise
        path = path.lstrip("/")
        ignored = False

        for pattern, is_negation in self._compiled:
            if _pattern_matches(pattern, path):
                ignored = not is_negation  # negation → un-ignore

        return ignored

    def filter(self, paths: list[str]) -> list[str]:
        """Return only paths that are NOT ignored."""
        return [p for p in paths if not self.is_ignored(p)]


def load_ignore_file(filepath: str) -> IgnoreRules:
    """Load an ``IgnoreRules`` from a single ignore-file path.

    Raises ``FileNotFoundError`` if *filepath* does not exist.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Ignore file not found: {filepath}")

    with open(filepath) as f:
        lines = f.readlines()

    patterns = [line.rstrip("\n") for line in lines]
    return IgnoreRules(patterns)


def load_gitignore(root_path: str) -> IgnoreRules:
    """Load ignore rules from ``.gitignore`` + ``.opencodeignore``.

    If neither file exists, returns an empty ``IgnoreRules``.
    """
    all_patterns: list[str] = []

    gitignore_path = os.path.join(root_path, ".gitignore")
    if os.path.isfile(gitignore_path):
        with open(gitignore_path) as f:
            all_patterns.extend(line.rstrip("\n") for line in f)

    opencode_ignore = os.path.join(root_path, ".opencodeignore")
    if os.path.isfile(opencode_ignore):
        with open(opencode_ignore) as f:
            all_patterns.extend(line.rstrip("\n") for line in f)

    return IgnoreRules(all_patterns)
