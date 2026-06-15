from __future__ import annotations

import subprocess

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class GitDiff:
    def diff(self, path: str | None = None, staged: bool = False) -> str:
        try:
            cmd = ["git", "diff"]
            if staged:
                cmd.append("--cached")
            if path:
                cmd.append(path)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.stdout if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def diff_files(self) -> list[str]:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return []
            return [f for f in result.stdout.splitlines() if f.strip()]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    def changed_files(self) -> list[str]:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return []
            return [f for f in result.stdout.splitlines() if f.strip()]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []
