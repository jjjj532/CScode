"""Tests for P2-4: WorktreeManager — git worktree management.

Tests cover:
1. WorktreeInfo dataclass creation
2. Porcelain output parsing (normal, detached, bare, prunable)
3. WorktreeManager.list() integration test
4. WorktreeManager.create() / remove() integration test
5. Error cases: non-git repo, already exists, non-existent removal
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from cscode.core.worktree import WorktreeInfo, WorktreeManager

# ── Helpers ──────────────────────────────────────────────────────────

def _git(*args: str, cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def git_repo() -> str:
    """Create a temporary git repository for testing."""
    tmp = tempfile.mkdtemp()
    _git("init", "--initial-branch=main", cwd=tmp)
    _git("config", "user.email", "test@test.com", cwd=tmp)
    _git("config", "user.name", "Test", cwd=tmp)
    # Create an initial commit so HEAD is valid
    (Path(tmp) / "README.md").write_text("# test")
    _git("add", ".", cwd=tmp)
    _git("commit", "-m", "initial", cwd=tmp)
    return tmp


@pytest.fixture
def manager(git_repo: str) -> WorktreeManager:
    return WorktreeManager(repo_path=git_repo)


# ── WorktreeInfo ─────────────────────────────────────────────────────


class TestWorktreeInfo:
    def test_create_basic(self) -> None:
        info = WorktreeInfo(
            path="/repo",
            branch="main",
            hash="abc123",
            bare=False,
            detached=False,
        )
        assert info.path == "/repo"
        assert info.branch == "main"
        assert info.hash == "abc123"
        assert not info.bare
        assert not info.detached

    def test_create_detached(self) -> None:
        info = WorktreeInfo(
            path="/repo",
            branch="",
            hash="abc123",
            bare=False,
            detached=True,
        )
        assert info.detached
        assert info.branch == ""

    def test_create_bare(self) -> None:
        info = WorktreeInfo(
            path="/repo",
            branch="main",
            hash="abc123",
            bare=True,
            detached=False,
        )
        assert info.bare


# ── Porcelain Parsing ────────────────────────────────────────────────


class TestParsePorcelain:
    def test_normal_entry(self) -> None:
        """Parse a standard worktree entry with a branch."""
        output = """worktree /Users/test/project
HEAD abc123def456
branch refs/heads/feature-x
"""
        results = WorktreeManager._parse_output(output)
        assert len(results) == 1
        w = results[0]
        assert w.path == "/Users/test/project"
        assert w.hash == "abc123def456"
        assert w.branch == "feature-x"
        assert not w.bare
        assert not w.detached

    def test_detached_entry(self) -> None:
        """Parse a detached HEAD entry (no branch line)."""
        output = """worktree /Users/test/project
HEAD abc123def456
detached
"""
        results = WorktreeManager._parse_output(output)
        assert len(results) == 1
        w = results[0]
        assert w.hash == "abc123def456"
        assert w.branch == ""
        assert w.detached

    def test_bare_entry(self) -> None:
        """Parse a bare repository entry."""
        output = """worktree /Users/test/project
HEAD abc123def456
branch refs/heads/main
bare
"""
        results = WorktreeManager._parse_output(output)
        assert len(results) == 1
        w = results[0]
        assert w.bare
        assert w.branch == "main"

    def test_prunable_ignored(self) -> None:
        """Prunable status line is present but does not affect main fields."""
        output = """worktree /tmp/wt-add
HEAD de35da5b
branch refs/heads/wt-add
prunable gitdir file points to non-existent location
"""
        results = WorktreeManager._parse_output(output)
        assert len(results) == 1
        w = results[0]
        assert w.path == "/tmp/wt-add"
        assert w.branch == "wt-add"
        assert w.hash == "de35da5b"
        assert not w.bare
        assert not w.detached

    def test_multiple_entries(self) -> None:
        """Parse multiple worktree entries separated by blank lines."""
        output = """worktree /repo/main
HEAD aaa
branch refs/heads/main

worktree /repo/feature
HEAD bbb
branch refs/heads/feature-x
detached

worktree /bare-repo
HEAD ccc
bare
"""
        results = WorktreeManager._parse_output(output)
        assert len(results) == 3

        assert results[0].path == "/repo/main"
        assert results[0].branch == "main"
        assert not results[0].detached

        assert results[1].path == "/repo/feature"
        assert results[1].branch == "feature-x"
        assert results[1].detached

        assert results[2].path == "/bare-repo"
        assert results[2].bare

    def test_empty_output(self) -> None:
        """Empty output produces an empty list."""
        results = WorktreeManager._parse_output("")
        assert results == []

    def test_whitespace_only(self) -> None:
        """Whitespace-only output produces an empty list."""
        results = WorktreeManager._parse_output("   \n\n  \n")
        assert results == []


# ── Integration Tests ────────────────────────────────────────────────


class TestWorktreeManagerIntegration:
    def test_list_returns_main_worktree(self, manager: WorktreeManager) -> None:
        """list() returns at least the main worktree."""
        trees = manager.list()
        assert len(trees) >= 1
        # The main worktree has the repo path
        main = [w for w in trees if w.path == manager._repo_path]
        assert len(main) == 1
        assert main[0].branch == "main"

    def test_create_and_list(self, manager: WorktreeManager) -> None:
        """Creating a worktree makes it appear in list()."""
        wt_path = os.path.join(manager._repo_path, "..", "wt-feature")
        wt_path = os.path.abspath(wt_path)
        try:
            info = manager.create(branch="feature-x", path=wt_path)
            assert os.path.isdir(wt_path)
            assert info.path == wt_path
            assert info.branch == "feature-x"

            # list should now include it
            trees = manager.list()
            created = [w for w in trees if w.path == wt_path]
            assert len(created) == 1
            assert created[0].branch == "feature-x"
        finally:
            # Cleanup
            if os.path.isdir(wt_path):
                subprocess.run(
                    ["git", "worktree", "remove", "--force", wt_path],
                    cwd=manager._repo_path,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "branch", "-D", "feature-x"],
                    cwd=manager._repo_path,
                    capture_output=True,
                )

    def test_remove_worktree(self, manager: WorktreeManager) -> None:
        """Creating then removing a worktree removes it from list()."""
        wt_path = os.path.join(manager._repo_path, "..", "wt-to-remove")
        wt_path = os.path.abspath(wt_path)
        try:
            manager.create(branch="to-remove", path=wt_path)
            assert os.path.isdir(wt_path)

            manager.remove(wt_path)
            assert not os.path.isdir(wt_path)

            trees = manager.list()
            removed = [w for w in trees if w.path == wt_path]
            assert len(removed) == 0
        finally:
            # Extra cleanup in case test failed
            if os.path.isdir(wt_path):
                subprocess.run(
                    ["git", "worktree", "remove", "--force", wt_path],
                    cwd=manager._repo_path,
                    capture_output=True,
                )
            subprocess.run(
                ["git", "branch", "-D", "to-remove"],
                cwd=manager._repo_path,
                capture_output=True,
            )

    def test_remove_nonexistent_raises(self, manager: WorktreeManager) -> None:
        """Removing a non-existent worktree path raises an error."""
        with pytest.raises(RuntimeError, match="not a working tree"):
            manager.remove("/tmp/nonexistent-worktree-path-abc123")

    def test_create_existing_branch_raises(self, manager: WorktreeManager) -> None:
        """Creating a worktree with a branch name that already exists."""
        wt_path = os.path.join(manager._repo_path, "..", "wt-duplicate")
        wt_path = os.path.abspath(wt_path)
        try:
            # 'main' branch already exists
            with pytest.raises(RuntimeError):
                manager.create(branch="main", path=wt_path)
        finally:
            if os.path.isdir(wt_path):
                subprocess.run(
                    ["git", "worktree", "remove", "--force", wt_path],
                    cwd=manager._repo_path,
                    capture_output=True,
                )

    def test_create_without_path_creates_in_parent(self, manager: WorktreeManager) -> None:
        """When path is None, branch name is used as dir name in parent."""
        wt_dir = os.path.join(manager._repo_path, "..", "auto-named-wt")
        wt_dir = os.path.abspath(wt_dir)
        try:
            info = manager.create(branch="auto-named-wt", path=None)
            assert os.path.isdir(info.path)
            # The path should contain the branch name by default
            assert "auto-named-wt" in info.path
        finally:
            if os.path.isdir(wt_dir):
                subprocess.run(
                    ["git", "worktree", "remove", "--force", wt_dir],
                    cwd=manager._repo_path,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "branch", "-D", "auto-named-wt"],
                    cwd=manager._repo_path,
                    capture_output=True,
                )


# ── Git Error Cases ──────────────────────────────────────────────────


class TestWorktreeManagerErrors:
    def test_non_git_repo_raises(self) -> None:
        """WorktreeManager on a non-git directory raises on list()."""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorktreeManager(repo_path=tmp)
            with pytest.raises(RuntimeError, match="not a git repository|fatal"):
                mgr.list()

    def test_init_nonexistent_path_raises(self) -> None:
        """WorktreeManager with non-existent path raises."""
        with pytest.raises(NotADirectoryError):
            WorktreeManager(repo_path="/tmp/nonexistent-xyz-98765")
