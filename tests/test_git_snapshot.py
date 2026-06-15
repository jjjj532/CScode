from __future__ import annotations

import pytest

from cscode.git.snapshot import GitSnapshot


class TestGitSnapshot:
    def test_init_snapshot(self) -> None:
        snap = GitSnapshot()
        assert snap.enabled is True

    def test_init_disabled(self) -> None:
        snap = GitSnapshot(enabled=False)
        assert not snap.enabled

    def test_snapshot_no_git_repo(self) -> None:
        snap = GitSnapshot()
        result = snap.snapshot("test message")
        assert result is True
