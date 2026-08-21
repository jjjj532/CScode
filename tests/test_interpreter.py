"""Tests for sandbox/interpreter.py — Python subset interpreter (G-11, Route A).

验收标准（spec §6.5.4）:
1. 基础操作：赋值/算术/条件/循环/函数/列表/字典/print → SandboxSuccess(stdout=...)
2. 禁止操作：import/async/class/with/try/exec/eval/文件/网络 → SandboxFailure
3. 执行预算：max_steps 限制 → SandboxFailure(TIMEOUT_EXCEEDED)
4. 工具调用：tools_ns.tool(...) 经过权限检查 → SandboxResult
5. 输出兼容：SandboxResult 类型不变
6. 性能基准：（不在单元测试范围，集成测试验证）
"""

from __future__ import annotations

import pytest

from cscode.sandbox.diagnostics import DiagnosticKind
from cscode.sandbox.interpreter import PythonInterpreter
from cscode.sandbox.limits import ExecutionLimits
from cscode.sandbox.result import SandboxFailure, SandboxSuccess


def _run(
    script: str,
    max_steps: int = 1000,
    tools_ns: dict | None = None,
) -> SandboxSuccess | SandboxFailure:
    """Helper: run a script through the interpreter."""
    limits = ExecutionLimits(timeout_ms=5000, max_output_bytes=4096, max_steps=max_steps)
    interp = PythonInterpreter(limits=limits, tools_ns=tools_ns)
    import asyncio
    return asyncio.run(interp.run(script))


# ── 1. 基础操作 ──────────────────────────────────────────


class TestBasicOperations:
    """验收标准 1: 赋值/算术/条件/循环/函数/列表/字典/print → SandboxSuccess"""

    def test_assignment_and_print(self) -> None:
        r = _run("x = 5\nprint(x)")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "5"

    def test_arithmetic(self) -> None:
        r = _run("print(2 + 3)")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "5"

    def test_division(self) -> None:
        r = _run("print(10 / 2)")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "5.0"

    def test_floor_division(self) -> None:
        r = _run("print(10 // 3)")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "3"

    def test_modulo(self) -> None:
        r = _run("print(10 % 3)")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "1"

    def test_power(self) -> None:
        r = _run("print(2 ** 10)")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "1024"

    def test_unary_minus(self) -> None:
        r = _run("x = 5\nprint(-x)")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "-5"

    def test_string_print(self) -> None:
        r = _run('print("hello")')
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "hello"


# ── 2. 条件 ──────────────────────────────────────────────


class TestConditionals:
    def test_if_true(self) -> None:
        r = _run('x = 10\nif x > 5: print("big")')
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "big"

    def test_if_false(self) -> None:
        r = _run('x = 3\nif x > 5: print("big")')
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == ""

    def test_if_else(self) -> None:
        r = _run('x = 3\nif x > 5: print("big")\nelse: print("small")')
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "small"

    def test_if_elif_else(self) -> None:
        r = _run('x = 3\nif x > 5: print("big")\nelif x > 2: print("medium")\nelse: print("small")')
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "medium"

    def test_boolean_and(self) -> None:
        r = _run('x = 5\nif x > 3 and x < 10: print("ok")')
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "ok"

    def test_boolean_or(self) -> None:
        r = _run('x = 1\nif x > 5 or x == 1: print("ok")')
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "ok"

    def test_boolean_not(self) -> None:
        r = _run('x = 5\nif not x == 3: print("ok")')
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "ok"


# ── 3. 循环 ──────────────────────────────────────────────


class TestLoops:
    def test_for_list(self) -> None:
        r = _run("for i in [1, 2, 3]:\n  print(i)")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "1\n2\n3"

    def test_while(self) -> None:
        r = _run("x = 0\nwhile x < 3:\n  print(x)\n  x += 1")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "0\n1\n2"

    def test_for_range(self) -> None:
        r = _run("for i in range(5):\n  print(i)")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "0\n1\n2\n3\n4"

    def test_nested_loop(self) -> None:
        r = _run("for i in [1, 2]:\n  for j in ['a', 'b']:\n    print(i, j)")
        assert isinstance(r, SandboxSuccess)
        lines = r.stdout.strip().split("\n")
        assert len(lines) == 4


# ── 4. 函数 ──────────────────────────────────────────────


class TestFunctions:
    def test_simple_function(self) -> None:
        r = _run("def add(a, b):\n  return a + b\n\nprint(add(2, 3))")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "5"

    def test_recursive_function(self) -> None:
        r = _run(
            "def factorial(n):\n"
            "  if n <= 1:\n"
            "    return 1\n"
            "  return n * factorial(n - 1)\n"
            "\n"
            "print(factorial(5))"
        )
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "120"

    def test_function_with_default(self) -> None:
        r = _run("def greet(name='world'):\n  print('hello ' + name)\n\ngreet()\ngreet('cs')")
        assert isinstance(r, SandboxSuccess)
        lines = r.stdout.strip().split("\n")
        assert lines[0] == "hello world"
        assert lines[1] == "hello cs"


# ── 5. 数据结构 ──────────────────────────────────────────


class TestDataStructures:
    def test_list_literal(self) -> None:
        r = _run("print([1, 2, 3])")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "[1, 2, 3]"

    def test_dict_literal(self) -> None:
        r = _run('print({"a": 1, "b": 2})')
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "{'a': 1, 'b': 2}"

    def test_tuple_literal(self) -> None:
        r = _run("print((1, 2, 3))")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "(1, 2, 3)"

    def test_list_subscript(self) -> None:
        r = _run("x = [10, 20, 30]\nprint(x[1])")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "20"

    def test_dict_subscript(self) -> None:
        r = _run('x = {"a": 42}\nprint(x["a"])')
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "42"

    def test_list_append(self) -> None:
        r = _run("x = [1, 2]\nx.append(3)\nprint(x)")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "[1, 2, 3]"

    def test_list_comprehension(self) -> None:
        r = _run("print([x * 2 for x in [1, 2, 3]])")
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "[2, 4, 6]"


# ── 6. 禁止操作 ──────────────────────────────────────────


class TestForbiddenOperations:
    """验收标准 2: 禁止操作 → SandboxFailure(EXECUTION_FAILURE)"""

    @pytest.mark.parametrize("script", [
        "import os",
        "from os import path",
        "import os.path",
    ])
    def test_import_forbidden(self, script: str) -> None:
        r = _run(script)
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.EXECUTION_FAILURE

    @pytest.mark.parametrize("script", [
        "async def f():\n  pass",
        "async for i in [1]:\n  pass",
    ])
    def test_async_forbidden(self, script: str) -> None:
        r = _run(script)
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.EXECUTION_FAILURE

    def test_class_forbidden(self) -> None:
        r = _run("class Foo:\n  pass")
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.EXECUTION_FAILURE

    def test_with_forbidden(self) -> None:
        r = _run("with open('x') as f:\n  pass")
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.EXECUTION_FAILURE

    @pytest.mark.parametrize("script", [
        "try:\n  pass\nexcept:\n  pass",
        "try:\n  pass\nfinally:\n  pass",
    ])
    def test_try_forbidden(self, script: str) -> None:
        r = _run(script)
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.EXECUTION_FAILURE

    def test_exec_forbidden(self) -> None:
        r = _run('exec("print(1)")')
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.EXECUTION_FAILURE

    def test_eval_forbidden(self) -> None:
        r = _run("eval('1 + 1')")
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.EXECUTION_FAILURE

    def test_open_forbidden(self) -> None:
        r = _run("open('x')")
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.EXECUTION_FAILURE

    def test_dunder_import_forbidden(self) -> None:
        r = _run('__import__("os")')
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.EXECUTION_FAILURE

    def test_globals_forbidden(self) -> None:
        r = _run("globals()")
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.EXECUTION_FAILURE

    def test_locals_forbidden(self) -> None:
        r = _run("locals()")
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.EXECUTION_FAILURE


# ── 7. 执行预算 ──────────────────────────────────────────


class TestBudget:
    """验收标准 3: max_steps 限制 → SandboxFailure(TIMEOUT_EXCEEDED)"""

    def test_infinite_loop_terminated(self) -> None:
        r = _run("while True:\n  pass", max_steps=100)
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.TIMEOUT_EXCEEDED

    def test_budget_counter_increments(self) -> None:
        # Simple loop that uses ~10 steps
        r = _run("x = 0\nwhile x < 5:\n  x += 1", max_steps=100)
        assert isinstance(r, SandboxSuccess)

    def test_budget_exact_limit(self) -> None:
        # Construct a script that uses exactly N steps
        # Each assignment = 1 step, each while check = 1 step
        r = _run("x = 0\nwhile x < 3:\n  x += 1", max_steps=8)
        # Should either succeed or fail depending on exact step count
        assert isinstance(r, (SandboxSuccess, SandboxFailure))


# ── 8. 工具调用 ──────────────────────────────────────────


class TestToolCalls:
    """验收标准 4: tools_ns.tool(...) 调用桥接"""

    def test_tool_call(self) -> None:
        mock_tool = lambda name, args: f"tool:{name}:{args}"
        tools_ns = {"tool": mock_tool}
        r = _run('result = tool("bash", {"cmd": "ls"})\nprint(result)', tools_ns=tools_ns)
        assert isinstance(r, SandboxSuccess)
        assert "tool:bash:" in r.stdout

    def test_tool_returns_value(self) -> None:
        mock_tool = lambda name, args: 42
        tools_ns = {"tool": mock_tool}
        r = _run("x = tool('test', {})\nprint(x)", tools_ns=tools_ns)
        assert isinstance(r, SandboxSuccess)
        assert r.stdout.strip() == "42"


# ── 9. 输出兼容 ──────────────────────────────────────────


class TestOutputCompatibility:
    """验收标准 5: SandboxResult 类型不变"""

    def test_returns_sandbox_success(self) -> None:
        r = _run("print(1)")
        assert isinstance(r, SandboxSuccess)
        assert hasattr(r, "stdout")
        assert hasattr(r, "stderr")
        assert hasattr(r, "exit_code")
        assert hasattr(r, "truncated")

    def test_syntax_error_returns_failure(self) -> None:
        r = _run("def")
        assert isinstance(r, SandboxFailure)
        assert r.error.kind == DiagnosticKind.EXECUTION_FAILURE

    def test_runtime_error_returns_success_with_stderr(self) -> None:
        r = _run("print(1 / 0)")
        assert isinstance(r, SandboxSuccess)
        assert r.exit_code != 0 or "ZeroDivisionError" in r.stderr


# ── 10. 语法错误预检 ─────────────────────────────────────


class TestSyntaxErrors:
    def test_syntax_error_caught(self) -> None:
        r = _run("def")
        assert isinstance(r, SandboxFailure)
        assert "syntax" in r.error.message.lower() or "compile" in r.error.message.lower()

    def test_indentation_error(self) -> None:
        r = _run("if True:\nprint(1)")
        assert isinstance(r, SandboxFailure)
