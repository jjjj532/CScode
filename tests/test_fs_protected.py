"""TDD tests for Filesystem Protected (P0-6).

RED phase: these tests MUST fail initially.
GREEN phase: implementation makes them pass.
"""

from __future__ import annotations

import pytest

from cscode.core.fs_protected import (
    ProtectedPaths,
    default_protected_paths,
)


class TestProtectedDefaults:
    def test_system_dirs_are_protected(self) -> None:
        p = ProtectedPaths(default_protected_paths())
        assert p.is_protected("/usr/bin/python") is True
        assert p.is_protected("/etc/hosts") is True
        assert p.is_protected("/System/Library/CoreServices") is True

    def test_user_project_files_are_not_protected(self) -> None:
        p = ProtectedPaths(default_protected_paths())
        assert p.is_protected("/home/user/project/main.py") is False
        assert p.is_protected("/tmp/build/output.o") is False
        assert p.is_protected("/Users/mac/AI/CScode/src/main.py") is False

    def test_home_dotfiles_are_protected(self) -> None:
        p = ProtectedPaths(default_protected_paths())
        assert p.is_protected("/Users/test/.ssh/id_rsa") is True
        assert p.is_protected("/home/user/.env") is True
        assert p.is_protected("/Users/test/.gnupg/pubring.kbx") is True


class TestProtectedCustom:
    def test_allowlist_overrides(self) -> None:
        p = ProtectedPaths(
            protected=["/etc/", "/usr/"],
            allowlist=["/etc/opt/app/custom.conf"],
        )
        assert p.is_protected("/etc/hosts") is True
        assert p.is_protected("/etc/opt/app/custom.conf") is False

    def test_blocklist_adds(self) -> None:
        p = ProtectedPaths(
            protected=["/etc/"],
            blocklist=["/var/db/"],
        )
        assert p.is_protected("/var/db/system.sqlite") is True
        assert p.is_protected("/etc/hosts") is True

    def test_wildcard_pattern(self) -> None:
        p = ProtectedPaths(
            protected=["/opt/*/secrets/"],
        )
        assert p.is_protected("/opt/app/secrets/key.txt") is True
        assert p.is_protected("/opt/app/config.yaml") is False

    def test_allowlist_takes_priority(self) -> None:
        p = ProtectedPaths(
            protected=["/data/**"],
            allowlist=["/data/shared/**"],
        )
        assert p.is_protected("/data/private/key.txt") is True
        assert p.is_protected("/data/shared/public.txt") is False


class TestProtectedEdgeCases:
    def test_relative_paths_not_protected(self) -> None:
        p = ProtectedPaths(default_protected_paths())
        assert p.is_protected("etc/hosts") is False
        assert p.is_protected("usr/bin/python") is False

    def test_deeply_nested_system_path(self) -> None:
        p = ProtectedPaths(default_protected_paths())
        assert p.is_protected("/usr/local/lib/node_modules/npm/bin/npm") is True

    def test_empty_protected(self) -> None:
        p = ProtectedPaths([])
        assert p.is_protected("/etc/hosts") is False
        assert p.is_protected("/usr/bin/python") is False

    def test_subpath_not_protected(self) -> None:
        p = ProtectedPaths(protected=["/usr/local"])
        assert p.is_protected("/usr/local/bin/node") is True
        assert p.is_protected("/usr/not_local/file") is False


class TestProtectedPathsFilter:
    def test_filter_removes_protected(self) -> None:
        p = ProtectedPaths(["/etc/"])
        paths = ["/etc/hosts", "/home/user/file.py", "/usr/bin/python"]
        result = p.filter(paths)
        assert result == ["/home/user/file.py", "/usr/bin/python"]

    def test_filter_empty(self) -> None:
        p = ProtectedPaths(default_protected_paths())
        assert p.filter([]) == []
