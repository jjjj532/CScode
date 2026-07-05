"""P2-16: External Directory — approved external directory permission registry.

Allows users to approve specific directories outside the workspace
for tool file access. The registry stores approved paths and provides
lookup methods for the tool permission system.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field


def _normalize_path(path: str) -> str:
    """Normalize a filesystem path for consistent matching.

    - Resolves to absolute
    - Removes trailing slash (except root '/')
    """
    abs_path = os.path.abspath(path)
    if abs_path != "/":
        abs_path = abs_path.rstrip("/")
    return abs_path


@dataclass
class ExternalDirectory:
    """An approved external directory entry."""

    path: str
    id: str = ""
    created_at: int = 0

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"extdir_{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = int(time.time() * 1000)


@dataclass
class ExternalDirectoryStore:
    """In-memory store for approved external directories.

    Provides add/list/remove/check operations for managing
    directories that tools are allowed to access outside the workspace.
    """

    _directories: dict[str, ExternalDirectory] = field(default_factory=dict)

    def add(self, path: str) -> ExternalDirectory:
        """Register a directory as approved for external tool access.

        Raises ValueError if the path is already registered.
        """
        normalized = _normalize_path(path)
        for entry in self._directories.values():
            if entry.path == normalized:
                msg = f"Directory '{normalized}' is already registered"
                raise ValueError(msg)
        entry = ExternalDirectory(path=normalized)
        self._directories[entry.id] = entry
        return entry

    def remove(self, dir_id: str) -> bool:
        """Remove a directory by its ID. Returns True if removed, False if not found."""
        if dir_id in self._directories:
            del self._directories[dir_id]
            return True
        return False

    def list(self) -> list[ExternalDirectory]:
        """Return all approved directories in insertion order."""
        return list(self._directories.values())

    def clear(self) -> None:
        """Remove all approved directories."""
        self._directories.clear()

    def is_approved(self, path: str) -> bool:
        """Check if a path is within an approved external directory.

        Returns True if the path equals or starts with any approved
        directory path (ensuring directory boundary with '/' separator).
        """
        if not self._directories:
            return False
        normalized = _normalize_path(path)
        for entry in self._directories.values():
            approved_path = entry.path
            if normalized == approved_path:
                return True
            if approved_path == "/":
                return True
            prefix = approved_path + "/"
            if normalized.startswith(prefix):
                return True
        return False
