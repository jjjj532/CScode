"""P2-4: Control-Plane — Worktree management and session routing.

Provides:
- WorktreeManager: git worktree list/add/remove/prune
- WorktreeInfo: parsed worktree metadata
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WorktreeInfo:
    """Parsed git worktree information."""

    path: str = ""
    """Absolute path to the worktree."""
    hash: str = ""
    """HEAD commit hash."""
    branch: str = ""
    """Branch name (empty if detached)."""
    bare: bool = False
    """Whether this is a bare repository."""
    detached: bool = False
    """Whether HEAD is detached."""


class WorktreeManager:
    """Git worktree management utility.

    All operations delegate to ``git worktree`` subcommands.
    """

    @staticmethod
    def list_worktrees(work_dir: str | None = None) -> list[WorktreeInfo]:
        """List all git worktrees.

        Args:
            work_dir: Git working directory (defaults to cwd).

        Returns:
            A list of WorktreeInfo for each worktree.
            Empty list if ``git worktree list`` fails or is not in a git repo.
        """
        try:
            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                capture_output=True, text=True, timeout=10, cwd=work_dir,
            )
            if result.returncode != 0:
                logger.warning("git worktree list failed: %s", result.stderr.strip())
                return []
            return WorktreeManager._parse_output(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("Failed to list worktrees: %s", e)
            return []

    @staticmethod
    def _parse_output(output: str) -> list[WorktreeInfo]:
        """Parse ``--porcelain`` format output into WorktreeInfo list."""
        worktrees: list[WorktreeInfo] = []
        current: WorktreeInfo | None = None

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("worktree "):
                if current is not None:
                    worktrees.append(current)
                current = WorktreeInfo(path=line[9:])
            elif line.startswith("HEAD "):
                if current is not None:
                    current.hash = line[5:]
            elif line.startswith("branch "):
                if current is not None:
                    ref = line[7:]
                    # refs/heads/branch-name → branch-name
                    if ref.startswith("refs/heads/"):
                        current.branch = ref[11:]
                    else:
                        current.branch = ref
            elif line == "bare":
                if current is not None:
                    current.bare = True
            elif line == "detached":
                if current is not None:
                    current.detached = True

        if current is not None:
            worktrees.append(current)

        return worktrees

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
    def add_worktree(path: str, branch: str | None = None, work_dir: str | None = None) -> tuple[bool, str]:
        """Create a new git worktree.

        Args:
            path: Path where the worktree should be created.
            branch: Branch to check out (None = new branch from HEAD).
            work_dir: Git working directory (defaults to cwd).

        Returns:
            Tuple of (success, message).
        """
        cmd = ["git", "worktree", "add"]
        if branch:
            cmd += ["-b", branch]
        cmd.append(path)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=work_dir)
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, result.stderr.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return False, str(e)

    @staticmethod
    def remove_worktree(path: str, work_dir: str | None = None) -> tuple[bool, str]:
        """Remove a git worktree.

        Args:
            path: Path to the worktree to remove.
            work_dir: Git working directory (defaults to cwd).

        Returns:
            Tuple of (success, message).
        """
        try:
            result = subprocess.run(
                ["git", "worktree", "remove", path],
                capture_output=True, text=True, timeout=30, cwd=work_dir,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, result.stderr.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return False, str(e)
