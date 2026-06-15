from __future__ import annotations

import subprocess

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


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
