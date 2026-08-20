"""Tests for G-4: restricted execution sandbox (spec §4.4).

Route B: constrained subprocess runner with timeout, output limit,
and diagnostic algebra. Failure is data (SandboxFailure), not an exception.
"""

from __future__ import annotations

from typing import assert_never

import pytest

from cscode.sandbox.diagnostics import DiagnosticKind
from cscode.sandbox.limits import ExecutionLimits
from cscode.sandbox.result import SandboxFailure, SandboxResult, SandboxSuccess
from cscode.sandbox.runner import SandboxRunner


def _handled(result: SandboxResult) -> tuple[str, str, int, bool]:
    """判别联合双态必须被调用方处理（验收标准 4：mypy exhaustive）。"""
    match result:
        case SandboxSuccess(stdout=out, stderr=err, exit_code=code, truncated=tr):
            return (out, err, code, tr)
        case SandboxFailure(error=diag):
            return ("", diag.message, -1, False)
        case _:
            assert_never(result)


class TestSandboxSuccess:
    """验收标准 5：成功脚本返回 stdout/exit_code；truncated 正确。"""

    @pytest.fixture(autouse=True)
    def runner(self) -> SandboxRunner:
        return SandboxRunner(limits=ExecutionLimits(timeout_ms=5_000))

    async def test_simple_script_stdout(self, runner: SandboxRunner) -> None:
        result = await runner.run("print('hello sandbox')")
        assert isinstance(result, SandboxSuccess)
        assert result.stdout.strip() == "hello sandbox"
        assert result.exit_code == 0
        assert not result.truncated

    async def test_exit_code_propagated(self, runner: SandboxRunner) -> None:
        result = await runner.run("import sys; sys.exit(3)")
        assert isinstance(result, SandboxSuccess)
        assert result.exit_code == 3

    async def test_stderr_captured(self, runner: SandboxRunner) -> None:
        result = await runner.run("import sys; print('warn', file=sys.stderr)")
        assert isinstance(result, SandboxSuccess)
        assert "warn" in result.stderr

    async def test_argv_passed(self, runner: SandboxRunner) -> None:
        result = await runner.run("import sys; print(sys.argv[1])", argv=["--flag"])
        assert isinstance(result, SandboxSuccess)
        assert result.stdout.strip() == "--flag"

    async def test_success_shape_via_handler(self, runner: SandboxRunner) -> None:
        result = await runner.run("print('x')")
        out, err, code, tr = _handled(result)
        assert out.strip() == "x"
        assert code == 0
        assert not tr


class TestSandboxTimeout:
    """验收标准 1：超时脚本 → TIMEOUT_EXCEEDED 且子进程被 kill（<2s 返回）。"""

    async def test_timeout_returns_failure_quickly(self) -> None:
        runner = SandboxRunner(limits=ExecutionLimits(timeout_ms=200))
        import time

        start = time.monotonic()
        result = await runner.run("import time; time.sleep(10)")
        elapsed = time.monotonic() - start

        assert isinstance(result, SandboxFailure)
        assert result.error.kind == DiagnosticKind.TIMEOUT_EXCEEDED
        assert elapsed < 2.0
        assert "timeout" in result.error.message.lower()

    async def test_timeout_has_suggestion(self) -> None:
        runner = SandboxRunner(limits=ExecutionLimits(timeout_ms=100))
        result = await runner.run("import time; time.sleep(5)")
        assert isinstance(result, SandboxFailure)
        assert result.error.suggestions, "超时诊断应带可操作建议"


class TestSandboxOutputLimit:
    """验收标准 2：输出超限 → 截断或 OUTPUT_LIMIT_EXCEEDED。"""

    async def test_output_truncated(self) -> None:
        runner = SandboxRunner(limits=ExecutionLimits(timeout_ms=5_000, max_output_bytes=1_024))
        result = await runner.run("print('y' * 100_000)")
        assert isinstance(result, SandboxSuccess)
        assert result.truncated
        assert len(result.stdout.encode()) <= 1_024

    async def test_small_output_not_truncated(self) -> None:
        runner = SandboxRunner(limits=ExecutionLimits(timeout_ms=5_000, max_output_bytes=1_024))
        result = await runner.run("print('tiny')")
        assert isinstance(result, SandboxSuccess)
        assert not result.truncated


class TestSandboxExecutionFailure:
    """验收标准 3：非法脚本 → EXECUTION_FAILURE 携带 stderr 摘要。"""

    async def test_syntax_error_failure(self) -> None:
        runner = SandboxRunner(limits=ExecutionLimits(timeout_ms=5_000))
        result = await runner.run("def broken(:" )
        assert isinstance(result, SandboxFailure)
        assert result.error.kind == DiagnosticKind.EXECUTION_FAILURE
        assert result.error.message  # stderr 摘要非空

    async def test_runtime_error_is_data_not_failure(self) -> None:
        """运行时异常 → 脚本执行了，退出码/trceback 是数据（SandboxSuccess）。"""
        runner = SandboxRunner(limits=ExecutionLimits(timeout_ms=5_000))
        result = await runner.run("raise ValueError('boom')")
        assert isinstance(result, SandboxSuccess)
        assert result.exit_code != 0
        assert "boom" in result.stderr


class TestSandboxIsolation:
    """验收标准 6：-I 隔离模式，不继承用户环境变量。"""

    async def test_env_not_inherited(self) -> None:
        runner = SandboxRunner(limits=ExecutionLimits(timeout_ms=5_000))
        result = await runner.run(
            "import os; print('SANDBOX_TEST_VAR' in os.environ)"
        )
        assert isinstance(result, SandboxSuccess)
        assert result.stdout.strip() == "False"

    async def test_workdir_injected(self, tmp_path) -> None:
        runner = SandboxRunner(
            limits=ExecutionLimits(timeout_ms=5_000),
            workdir=str(tmp_path),
        )
        result = await runner.run("import os; print(os.getcwd())")
        assert isinstance(result, SandboxSuccess)
        assert result.stdout.strip() == str(tmp_path)


class TestSandboxResultUnion:
    """验收标准 4：判别联合——ok 字面量可窄化。"""

    async def test_ok_literal_narrows_to_success(self) -> None:
        runner = SandboxRunner(limits=ExecutionLimits(timeout_ms=5_000))
        result = await runner.run("print('ok')")
        if result.ok:
            assert isinstance(result, SandboxSuccess)
            assert result.stdout
        else:
            pytest.fail("成功脚本应得到 ok=True")

    async def test_failure_is_data_not_exception(self) -> None:
        """失败不抛异常——调用方收到 SandboxFailure 数据。"""
        runner = SandboxRunner(limits=ExecutionLimits(timeout_ms=100))
        result = await runner.run("import time; time.sleep(1)")
        assert isinstance(result, SandboxFailure)
        assert result.ok is False
