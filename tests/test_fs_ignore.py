"""TDD tests for Filesystem Ignore (P0-5).

RED phase: these tests MUST fail initially.
GREEN phase: implementation makes them pass.
"""

from __future__ import annotations

import pytest

from cscode.core.fs_ignore import IgnoreRules, load_gitignore, load_ignore_file


# ─── Single pattern matching ────────────────────────────────────────


class TestIgnoreRulesBasic:
    def test_empty_rules_allows_all(self) -> None:
        rules = IgnoreRules([])
        assert rules.is_ignored("any/file.py") is False

    def test_exact_filename(self) -> None:
        rules = IgnoreRules(["node_modules"])
        assert rules.is_ignored("node_modules") is True
        assert rules.is_ignored("src/file.py") is False

    def test_glob_star(self) -> None:
        rules = IgnoreRules(["*.pyc"])
        assert rules.is_ignored("foo.pyc") is True
        assert rules.is_ignored("foo.py") is False

    def test_directory_globstar(self) -> None:
        rules = IgnoreRules(["node_modules/**"])
        assert rules.is_ignored("node_modules/foo/bar.js") is True
        assert rules.is_ignored("src/file.py") is False

    def test_negation_overrides(self) -> None:
        rules = IgnoreRules(["*.log", "!important.log"])
        assert rules.is_ignored("debug.log") is True
        assert rules.is_ignored("important.log") is False

    def test_comment_line_is_ignored(self) -> None:
        rules = IgnoreRules(["# this is a comment", "*.tmp"])
        assert rules.is_ignored("file.tmp") is True
        assert rules.is_ignored("file.py") is False

    def test_trailing_slash_matches_directory(self) -> None:
        rules = IgnoreRules(["build/"])
        assert rules.is_ignored("build/") is True
        assert rules.is_ignored("build/file.o") is True
        assert rules.is_ignored("src/build.py") is False


class TestIgnoreRulesMultiLayer:
    def test_multiple_patterns(self) -> None:
        rules = IgnoreRules(["__pycache__/", "*.egg-info", ".git/"])
        assert rules.is_ignored("__pycache__/foo.py") is True
        assert rules.is_ignored("pkg.egg-info/PKG-INFO") is True
        assert rules.is_ignored(".git/HEAD") is True
        assert rules.is_ignored("src/main.py") is False

    def test_subdirectory_ignore(self) -> None:
        rules = IgnoreRules(["node_modules"])
        assert rules.is_ignored("node_modules/pkg/index.js") is True
        assert rules.is_ignored("other/pkg/node_modules/tool.js") is True

    def test_dot_files(self) -> None:
        rules = IgnoreRules([".env", ".DS_Store"])
        assert rules.is_ignored(".env") is True
        assert rules.is_ignored("src/.env") is True
        assert rules.is_ignored(".DS_Store") is True


# ─── load_gitignore — loading from project root ─────────────────────


class TestLoadGitignore:
    def test_load_from_existing_file(self, tmp_path) -> None:
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("node_modules/\n*.pyc\n")
        rules = load_gitignore(str(tmp_path))
        assert rules.is_ignored("node_modules/pkg.js") is True
        assert rules.is_ignored("test.pyc") is True
        assert rules.is_ignored("main.py") is False

    def test_no_gitignore_returns_empty(self, tmp_path) -> None:
        rules = load_gitignore(str(tmp_path))
        assert rules.is_ignored("any/file.py") is False

    def test_opencodeignore_merged(self, tmp_path) -> None:
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n")
        ocignore = tmp_path / ".opencodeignore"
        ocignore.write_text("secrets/\n")
        rules = load_gitignore(str(tmp_path))
        assert rules.is_ignored("debug.log") is True
        assert rules.is_ignored("secrets/key.txt") is True
        assert rules.is_ignored("main.py") is False


# ─── load_ignore_file — direct file reading ─────────────────────


class TestLoadIgnoreFile:
    def test_parse_valid_file(self, tmp_path) -> None:
        f = tmp_path / ".customignore"
        f.write_text("*.o\n*.exe\n")
        rules = load_ignore_file(str(f))
        assert rules.is_ignored("main.o") is True
        assert rules.is_ignored("main.exe") is True
        assert rules.is_ignored("main.c") is False

    def test_empty_file(self, tmp_path) -> None:
        f = tmp_path / ".emptyignore"
        f.write_text("")
        rules = load_ignore_file(str(f))
        assert rules.is_ignored("anything") is False

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_ignore_file("/nonexistent/.ignore")
