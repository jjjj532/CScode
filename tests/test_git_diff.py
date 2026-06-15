from __future__ import annotations

import pytest

from cscode.git.diff import GitDiff


class TestGitDiff:
    def test_init(self) -> None:
        diff = GitDiff()
        assert diff is not None
