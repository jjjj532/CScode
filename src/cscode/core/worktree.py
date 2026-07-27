"""P2-4: Worktree management — git worktree operations.

Provides a WorktreeInfo dataclass and WorktreeManager utility class
that shells out to ``git worktree`` commands. No persistence layer;
all state is on-disk via git.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import List

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WorktreeInfo:
    """Information about a single git worktree.

    Attributes:
        path: Absolute filesystem path of the worktree.
        branch: Branch name (empty if detached HEAD).
        hash: HEAD commit hash (full SHA).
        bare: Whether the worktree is a bare repository.
        detached: Whether HEAD is detached.
    """

    path: str = ""
    branch: str = ""
    hash: str = ""
    bare: bool = False
    detached: bool = False


class WorktreeManager:
    """Git worktree management utility class.

    All operations shell out to ``git worktree`` subcommands.
    """

    def __init__(self, repo_path: str) -> None:
        """Initialize the manager for the given repository.

        Args:
            repo_path: Absolute path to the git repository.

        Raises:
            NotADirectoryError: If the path does not exist.
        """
        if not os.path.isdir(repo_path):
            raise NotADirectoryError(
                f"Repository path does not exist: {repo_path}"
            )
        self._repo_path = os.path.realpath(repo_path)

    # ── Public API ─────────────────────────────────────────────────

    def list(self) -> List[WorktreeInfo]:
        """List all worktrees in the repository.

        Returns:
            List of WorktreeInfo for each worktree (including the main one).

        Raises:
            RuntimeError: If the git command fails (e.g. not a git repo).
        """
        output = self._git("worktree", "list", "--porcelain")
        return self._parse_output(output)

    def create(
        self,
        branch: str,
        path: str | None = None,
    ) -> WorktreeInfo:
        """Create a new worktree with the given branch.

        Args:
            branch: Branch name to create and check out.
            path: Target directory for the worktree.
                  If None, defaults to ``../<branch>`` relative to repo root.

        Returns:
            WorktreeInfo for the newly created worktree.

        Raises:
            RuntimeError: If the git worktree add command fails.
        """
        if path is None:
            path = os.path.join(os.path.dirname(self._repo_path), branch)

        # Use -b to create a new branch; if branch already exists
        # git will error, which is the desired behavior.
        args = ["worktree", "add", "-b", branch, path]
        self._git(*args)

        # Re-parse the porcelain output for the new worktree
        trees = self.list()
        for w in trees:
            if w.path == os.path.abspath(path):
                return w

        # Fallback: construct from what we know
        return WorktreeInfo(
            path=os.path.abspath(path),
            branch=branch,
            hash="",
            bare=False,
            detached=False,
        )

    def remove(self, path: str) -> None:
        """Remove a worktree by its filesystem path.

        Args:
            path: Absolute path to the worktree to remove.

        Raises:
            RuntimeError: If the git worktree remove command fails.
        """
        self._git("worktree", "remove", "--force", path)

    # ── Internal Helpers ───────────────────────────────────────────

    def _git(self, *args: str) -> str:
        """Run a git command in the repository.

        Args:
            *args: Git subcommand and arguments.

        Returns:
            Standard output of the command.

        Raises:
            RuntimeError: If the command exits with a non-zero code.
        """
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip()
            logger.error(
                "git %s failed (exit %d): %s",
                " ".join(args), exc.returncode, stderr,
            )
            raise RuntimeError(
                f"git {' '.join(args)} failed: {stderr}"
            ) from exc

    @staticmethod
    def _parse_output(output: str) -> List[WorktreeInfo]:
        """Parse ``git worktree list --porcelain`` output.

        Porcelain format (blank-line separated entries)::

            worktree /path/to/worktree
            HEAD <sha>
            branch refs/heads/<name>   # optional: present for non-detached
            detached                    # optional flag
            bare                        # optional flag
            prunable ...               # optional, ignored

        Args:
            output: Raw stdout from ``git worktree list --porcelain``.

        Returns:
            List of parsed WorktreeInfo instances.
        """
        results: List[WorktreeInfo] = []
        # Split on blank lines
        blocks = output.strip().split("\n\n")
        for block in blocks:
            block = block.strip()
            if not block:
                continue

            lines = block.split("\n")
            info = WorktreeInfo()

            for line in lines:
                line = line.strip()
                if line.startswith("worktree "):
                    info.path = line[len("worktree "):]
                elif line.startswith("HEAD "):
                    info.hash = line[len("HEAD "):]
                elif line.startswith("branch "):
                    branch_ref = line[len("branch "):]
                    # Parse "refs/heads/<name>"
                    if branch_ref.startswith("refs/heads/"):
                        info.branch = branch_ref[len("refs/heads/"):]
                    else:
                        info.branch = branch_ref
                elif line == "detached":
                    info.detached = True
                elif line == "bare":
                    info.bare = True
                elif line.startswith("prunable "):
                    # Prunable status — no fields to set, just informational
                    pass
                # Unknown/ignored fields are skipped

            if info.path:
                results.append(info)

        return results
