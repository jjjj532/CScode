from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BlameLine:
    """A single line from git blame."""
    commit: str
    author: str
    date: str
    line_number: int
    content: str


@dataclass
class BisectResult:
    """Result of git bisect operation."""
    bad_commit: str | None
    good_commits: list[str]
    first_bad_commit: str | None


@dataclass
class LogSearchResult:
    """Result of git log -S search."""
    commit: str
    author: str
    date: str
    message: str
    file_path: str
    add_remove: str  # "+" for added, "-" for removed


class GitReview:
    def get_head_info(self) -> dict[str, str]:
        try:
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()

            commit = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()

            msg = subprocess.run(
                ["git", "log", "-1", "--pretty=%s"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()

            return {"branch": branch, "commit": commit, "message": msg}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return {"branch": "unknown", "commit": "unknown", "message": ""}

    def get_uncommitted_changes(self) -> str:
        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def blame(self, file_path: str, options: dict[str, Any] | None = None, cwd: str | None = None) -> list[BlameLine]:
        """Run git blame on a file.

        Args:
            file_path: Path to the file to blame.
            options: Optional dict with keys:
                - line_range: tuple[int, int] to blame specific lines
                - show_email: bool to show author email
            cwd: Git working directory (defaults to cwd).

        Returns:
            List of BlameLine objects.
        """
        options = options or {}
        cmd = ["git", "blame", "--line-porcelain"]
        if options.get("show_email"):
            cmd.append("--email")
        line_range = options.get("line_range")
        if line_range:
            cmd.extend(["-L", f"{line_range[0]},{line_range[1]}"])
        cmd.append("--")
        cmd.append(file_path)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=cwd)
            if result.returncode != 0:
                logger.warning("git blame failed: %s", result.stderr)
                return []
            return self._parse_blame_output(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    def _parse_blame_output(self, output: str) -> list[BlameLine]:
        """Parse git blame --line-porcelain output."""
        lines = output.split("\n")
        blame_lines = []
        current: dict[str, str] = {}
        line_number = 0

        for line in lines:
            if line.startswith("author "):
                current["author"] = line[7:]
            elif line.startswith("author-time "):
                current["date"] = line[12:]
            elif line.startswith("committer "):
                pass  # we use author info
            elif line.startswith("summary "):
                current["message"] = line[7:]
            elif line.startswith("filename "):
                current["file"] = line[9:]
            elif line.startswith("\t"):
                current["content"] = line[1:]
                blame_lines.append(
                    BlameLine(
                        commit=current.get("commit", ""),
                        author=current.get("author", ""),
                        date=current.get("date", ""),
                        line_number=line_number + 1,
                        content=current.get("content", ""),
                    )
                )
                line_number += 1
                current = {}
            elif line.startswith("^?"):
                # Uncommitted change
                current["commit"] = "uncommitted"
                current["author"] = "local"
            elif line and not line.startswith(" "):
                current["commit"] = line

        return blame_lines

    def bisect_start(self, bad_rev: str = "HEAD", good_rev: str | None = None, cwd: str | None = None) -> bool:
        """Start git bisect with bad and good revisions.

        Args:
            bad_rev: The known bad revision (default: HEAD).
            good_rev: The known good revision.
            cwd: Git working directory (defaults to cwd).

        Returns:
            True if bisect started successfully.
        """
        try:
            subprocess.run(["git", "bisect", "start"], capture_output=True, timeout=10, cwd=cwd)
            subprocess.run(["git", "bisect", "bad", bad_rev], capture_output=True, timeout=10, cwd=cwd)
            if good_rev:
                subprocess.run(["git", "bisect", "good", good_rev], capture_output=True, timeout=10, cwd=cwd)
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def bisect_run(self) -> BisectResult | None:
        """Run git bisect and return the result."""
        try:
            # Read bisect log BEFORE reset — reset clears the state
            log_result = subprocess.run(
                ["git", "bisect", "log"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            first_bad = None
            good_commits = []
            if log_result.returncode == 0:
                for line in log_result.stdout.split("\n"):
                    if line.startswith("# first bad commit"):
                        parts = line.split(":", 1)
                        first_bad = parts[1].strip() if len(parts) > 1 else None
                    elif "good:" in line:
                        commit = line.split("good:")[1].strip() if "good:" in line else ""
                        if commit:
                            good_commits.append(commit)

            subprocess.run(
                ["git", "bisect", "reset"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            return BisectResult(
                bad_commit=None,
                good_commits=good_commits,
                first_bad_commit=first_bad,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def bisect_reset(self) -> bool:
        """Reset bisect state."""
        try:
            subprocess.run(["git", "bisect", "reset"], capture_output=True, timeout=10)
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def log_search(self, search_string: str, options: dict[str, Any] | None = None, cwd: str | None = None) -> list[LogSearchResult]:
        """Search for code changes using git log -S.

        Args:
            search_string: The string to search for.
            options: Optional dict with keys:
                - limit: int for max results
                - file_path: str to limit to specific file
                - all: bool to search all branches
            cwd: Git working directory (defaults to cwd).

        Returns:
            List of LogSearchResult objects.
        """
        options = options or {}
        cmd = ["git", "log", "-p", "-S" + search_string, "--pretty=format:%H%n%an%n%ad%n%s%n---\n"]
        if options.get("all"):
            cmd.append("--all")
        limit = options.get("limit", 50)
        cmd.extend([f"-{limit}"])
        file_path = options.get("file_path")
        if file_path:
            cmd.extend(["--", file_path])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=cwd)
            if result.returncode != 0:
                return []
            return self._parse_log_search(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    def _parse_log_search(self, output: str) -> list[LogSearchResult]:
        """Parse git log -S output."""
        commits = output.split("---")
        results = []
        for commit in commits:
            if not commit.strip():
                continue
            parts = commit.split("\n", 4)
            if len(parts) >= 4:
                results.append(
                    LogSearchResult(
                        commit=parts[0].strip(),
                        author=parts[1].strip(),
                        date=parts[2].strip(),
                        message=parts[3].strip(),
                        file_path="",
                        add_remove="+",
                    )
                )
        return results[:20]  # Limit results
