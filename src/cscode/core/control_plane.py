"""P2-4: Control-Plane — Worktree management and session routing.

Provides:
- WorktreeManager: git worktree list/add/remove/prune (static-method API)
- WorktreeInfo: parsed worktree metadata

This module delegates internal logic to :mod:`cscode.core.worktree` for the
instance-based implementation; the static-method API here exists for backward
compatibility with existing endpoint imports.
"""

from __future__ import annotations

import logging
import subprocess

from cscode.core.worktree import WorktreeInfo
from cscode.core.worktree import WorktreeManager as _WorktreeManagerImpl

logger = logging.getLogger(__name__)


class WorktreeManager:
    """Git worktree management utility (static-method API).

    All operations delegate to the instance-based implementation in
    :mod:`cscode.core.worktree`.
    """

    @staticmethod
    def list_worktrees(work_dir: str | None = None) -> list[WorktreeInfo]:
        """List all git worktrees.

        Args:
            work_dir: Git working directory (defaults to cwd).

        Returns:
            A list of WorktreeInfo for each worktree.
            Empty list if the command fails or the directory is not a git repo.
        """
        if work_dir is None:
            import os
            work_dir = os.getcwd()

        mgr = _WorktreeManagerImpl(repo_path=work_dir)
        try:
            return mgr.list()
        except (RuntimeError, NotADirectoryError):
            return []

    @staticmethod
    def _parse_output(output: str) -> list[WorktreeInfo]:
        """Parse ``--porcelain`` format output into WorktreeInfo list."""
        return _WorktreeManagerImpl._parse_output(output)

    @staticmethod
    def _parse_line(line: str) -> WorktreeInfo | None:
        """Parse a single ``git worktree list`` (non-porcelain) output line.

        Format: ``<path> <hash> [<branch>]``
        Example: ``/Users/user/project  abc1234 [main]``
        """
        line = line.strip()
        if not line:
            return None
        parts = line.split()
        if len(parts) < 2:
            return None

        info = WorktreeInfo(path=parts[0])

        # Bare repos have no hash; second field is "(bare)"
        if parts[1] == "(bare)":
            info.bare = True
            return info

        info.hash = parts[1]

        if len(parts) >= 3:
            branch_str = parts[2]
            if branch_str == "(bare)":
                info.bare = True
            elif branch_str == "(detached" and "HEAD)" in line:
                info.detached = True
            elif branch_str.startswith("[") and branch_str.endswith("]"):
                info.branch = branch_str[1:-1]

        # Check for detached in remaining parts
        if "(detached" in line:
            info.detached = True

        return info

    @staticmethod
    def add_worktree(
        path: str, branch: str | None = None, work_dir: str | None = None
    ) -> tuple[bool, str]:
        """Create a new git worktree.

        Args:
            path: Path where the worktree should be created.
            branch: Branch to check out (None = new branch from HEAD).
            work_dir: Git working directory (defaults to cwd).

        Returns:
            Tuple of (success, message).
        """
        if work_dir is None:
            import os
            work_dir = os.getcwd()

        mgr = _WorktreeManagerImpl(repo_path=work_dir)
        try:
            if branch:
                mgr.create(branch=branch, path=path)
            else:
                # When no branch is specified, create a detached-HEAD worktree.
                # This differs from mgr.create() which always uses -b.
                result = subprocess.run(
                    ["git", "worktree", "add", path],
                    capture_output=True, text=True, timeout=30, cwd=work_dir,
                )
                if result.returncode != 0:
                    return False, result.stderr.strip()
            return True, ""
        except (RuntimeError, subprocess.TimeoutExpired, FileNotFoundError, NotADirectoryError) as e:
            return False, str(e)

    @staticmethod
    def remove_worktree(
        path: str, work_dir: str | None = None
    ) -> tuple[bool, str]:
        """Remove a git worktree.

        Args:
            path: Path to the worktree to remove.
            work_dir: Git working directory (defaults to cwd).

        Returns:
            Tuple of (success, message).
        """
        if work_dir is None:
            import os
            work_dir = os.getcwd()

        mgr = _WorktreeManagerImpl(repo_path=work_dir)
        try:
            mgr.remove(path)
            return True, ""
        except (RuntimeError, NotADirectoryError) as e:
            return False, str(e)
