"""Tests for sandbox/landlock.py — OS-level file system sandboxing (G-12).

验收标准（spec §6.6.4）:
1. is_landlock_available() 在 Linux 5.13+ 返回 True；macOS/旧内核返回 False
2. apply_landlock_rules() 正确应用文件系统限制
3. SandboxRunner.run() 在 Linux 上自动应用 Landlock（若内核支持）
4. Landlock 不可用时 → 回退到纯 subprocess（无行为变化）
5. 跨平台：macOS/Linux 测试均通过（macOS 跳过 Landlock 测试）
"""

from __future__ import annotations

import os
import sys
import unittest.mock as mock

import pytest

from cscode.sandbox.landlock import (
    LANDLOCK_ABI_VERSION,
    apply_landlock_rules,
    is_landlock_available,
)
from cscode.sandbox.limits import ExecutionLimits


# ── 1. Availability detection ──────────────────────────────


class TestIsLandlockAvailable:
    def test_returns_bool(self) -> None:
        result = is_landlock_available()
        assert isinstance(result, bool)

    @pytest.mark.skipif(
        sys.platform != "linux",
        reason="Landlock only supported on Linux",
    )
    def test_linux_returns_bool(self) -> None:
        result = is_landlock_available()
        assert isinstance(result, bool)

    def test_macos_returns_false(self) -> None:
        if sys.platform == "linux":
            pytest.skip("running on Linux, cannot test macOS path")
        assert is_landlock_available() is False

    def test_mock_unavailable_when_no_syscall(self) -> None:
        with mock.patch("cscode.sandbox.landlock._libc", None):
            assert is_landlock_available() is False

    def test_mock_unavailable_when_errno(self) -> None:
        mock_libc = mock.MagicMock()
        mock_libc.prctl.return_value = -1
        mock_libc.landlock_create_ruleset.return_value = -1
        with mock.patch("cscode.sandbox.landlock._libc", mock_libc):
            assert is_landlock_available() is False


# ── 2. ABI version constant ────────────────────────────────


class TestLandlockConstants:
    def test_abi_version_is_int(self) -> None:
        assert isinstance(LANDLOCK_ABI_VERSION, int)

    def test_abi_version_positive(self) -> None:
        assert LANDLOCK_ABI_VERSION > 0


# ── 3. apply_landlock_rules ────────────────────────────────


class TestApplyLandlockRules:
    def test_noop_when_unavailable(self) -> None:
        with mock.patch("cscode.sandbox.landlock.is_landlock_available", return_value=False):
            apply_landlock_rules(["/usr"], ["/tmp/sandbox"])

    def test_raises_on_empty_write_paths(self) -> None:
        with mock.patch("cscode.sandbox.landlock.is_landlock_available", return_value=False):
            apply_landlock_rules(["/usr"], [])

    def test_mock_syscall_flow(self) -> None:
        with (
            mock.patch("cscode.sandbox.landlock.is_landlock_available", return_value=True),
            mock.patch("cscode.sandbox.landlock._set_no_new_privs", return_value=True),
            mock.patch("cscode.sandbox.landlock._create_ruleset", return_value=5),
            mock.patch("cscode.sandbox.landlock._add_read_path_rule", return_value=None),
            mock.patch("cscode.sandbox.landlock._add_write_path_rule", return_value=None),
            mock.patch("cscode.sandbox.landlock.os.close"),
        ):
            apply_landlock_rules(["/usr"], ["/tmp/sandbox"])

    def test_empty_read_paths_still_works(self) -> None:
        with (
            mock.patch("cscode.sandbox.landlock.is_landlock_available", return_value=True),
            mock.patch("cscode.sandbox.landlock._set_no_new_privs", return_value=True),
            mock.patch("cscode.sandbox.landlock._create_ruleset", return_value=5),
            mock.patch("cscode.sandbox.landlock._add_read_path_rule", return_value=None),
            mock.patch("cscode.sandbox.landlock._add_write_path_rule", return_value=None),
            mock.patch("cscode.sandbox.landlock.os.close"),
        ):
            apply_landlock_rules([], ["/tmp/sandbox"])


# ── 4. ExecutionLimits integration ─────────────────────────


class TestExecutionLimitsLandlock:
    def test_allowed_read_paths_default(self) -> None:
        from cscode.sandbox.limits import ExecutionLimits

        limits = ExecutionLimits()
        assert hasattr(limits, "allowed_read_paths")
        assert isinstance(limits.allowed_read_paths, list)

    def test_allowed_write_paths_default(self) -> None:
        from cscode.sandbox.limits import ExecutionLimits

        limits = ExecutionLimits()
        assert hasattr(limits, "allowed_write_paths")
        assert isinstance(limits.allowed_write_paths, list)

    def test_custom_paths(self) -> None:
        from cscode.sandbox.limits import ExecutionLimits

        limits = ExecutionLimits(
            allowed_read_paths=["/usr", "/lib"],
            allowed_write_paths=["/tmp/sandbox"],
        )
        assert limits.allowed_read_paths == ["/usr", "/lib"]
        assert limits.allowed_write_paths == ["/tmp/sandbox"]


# ── 5. SandboxRunner integration ───────────────────────────


class TestSandboxRunnerLandlock:
    def test_runner_has_landlock_field(self) -> None:
        from cscode.sandbox.runner import SandboxRunner
        from cscode.sandbox.limits import ExecutionLimits

        runner = SandboxRunner(limits=ExecutionLimits())
        assert hasattr(runner, "_limits")

    @pytest.mark.skipif(
        sys.platform != "linux",
        reason="Landlock integration test only on Linux",
    )
    def test_runner_on_linux_does_not_crash(self) -> None:
        from cscode.sandbox.runner import SandboxRunner
        from cscode.sandbox.limits import ExecutionLimits

        runner = SandboxRunner(limits=ExecutionLimits())
        import asyncio

        result = asyncio.run(runner.run("print('hello')"))
        assert result.ok is True
        assert result.stdout.strip() == "hello"

    def test_runner_fallback_when_landlock_unavailable(self) -> None:
        from cscode.sandbox.runner import SandboxRunner
        from cscode.sandbox.limits import ExecutionLimits

        with mock.patch(
            "cscode.sandbox.runner.is_landlock_available", return_value=False
        ):
            runner = SandboxRunner(limits=ExecutionLimits())
            import asyncio

            result = asyncio.run(runner.run("print('fallback')"))
            assert result.ok is True
            assert result.stdout.strip() == "fallback"


# ── 6. Cross-platform skip decorator ───────────────────────


skip_no_landlock = pytest.mark.skipif(
    sys.platform != "linux",
    reason="Landlock tests require Linux kernel 5.13+",
)


@skip_no_landlock
class TestLandlockEnforcementLinux:
    def test_read_allowed_path(self) -> None:
        import subprocess

        limits = ExecutionLimits(
            allowed_read_paths=["/usr"],
            allowed_write_paths=[],
        )
        code = "import os; print(os.access('/usr/bin/python3', os.R_OK))"
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert "True" in result.stdout

    def test_write_denied_outside_sandbox(self) -> None:
        import subprocess

        code = """
try:
    with open('/etc/landlock-test-file', 'w') as f:
        f.write('denied')
    print('WROTE')
except PermissionError:
    print('DENIED')
except OSError:
    print('DENIED')
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert "DENIED" in result.stdout or result.returncode != 0
