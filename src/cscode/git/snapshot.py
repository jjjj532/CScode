from __future__ import annotations

import subprocess

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class GitSnapshot:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def snapshot(self, message: str = "auto-snapshot") -> bool:
        if not self.enabled:
            return True
        if not self._is_git_repo():
            return True
        try:
            result = subprocess.run(
                ["git", "stash", "push", "-m", message, "--include-untracked"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                logger.info("Git snapshot: %s", message)
                subprocess.run(
                    ["git", "stash", "pop"],
                    capture_output=True, text=True, timeout=30,
                )
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Git snapshot skipped (timeout or git not found)")
            return True

    def _is_git_repo(self) -> bool:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
