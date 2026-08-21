"""Python subset interpreter — restricted execution without subprocess (spec §6.5).

Runs model-generated Python scripts in-process via AST walking, with:
- Step-budget enforcement (max_steps)
- Forbidden-operation static analysis (import/async/class/with/try/exec/eval/open/globals/locals)
- Tool call bridge (tools_ns.tool(...))
- Output capture (print → stdout)
"""

from __future__ import annotations

import ast
import io
from dataclasses import dataclass, field
from typing import Any

from cscode.sandbox.diagnostics import Diagnostic, DiagnosticKind
from cscode.sandbox.limits import ExecutionLimits
from cscode.sandbox.result import SandboxFailure, SandboxResult, SandboxSuccess


class BudgetExceeded(Exception):
    """Raised when the interpreter exceeds max_steps."""


# Forbidden AST node types (static analysis)
_FORBIDDEN节点 = (
    ast.Import,
    ast.ImportFrom,
    ast.AsyncFunctionDef,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.ClassDef,
    ast.With,
    ast.Try,
    ast.Raise,
    ast.Global,
    ast.Nonlocal,
)

# Forbidden function names (detected in Call nodes)
_FORBIDDEN函数 = frozenset({"exec", "eval", "open", "__import__", "globals", "locals", "compile", "getattr", "setattr", "delattr"})


_BUILTINS: dict[str, Any] = {
    "print": print,
    "len": len,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "reversed": reversed,
    "type": type,
    "isinstance": isinstance,
    "hasattr": hasattr,
    "chr": chr,
    "ord": ord,
    "hex": hex,
    "oct": oct,
    "bin": bin,
    "True": True,
    "False": False,
    "None": None,
}


@dataclass
class InterpreterContext:
    """Execution context with variables, scope chain, and step counter."""

    variables: dict[str, Any] = field(default_factory=dict)
    parent: InterpreterContext | None = None
    steps: int = 0
    max_steps: int = 1_000
    output: list[str] = field(default_factory=list)
    tools_ns: dict[str, Any] | None = None

    def get(self, name: str) -> Any:
        if name in self.variables:
            return self.variables[name]
        if self.parent is not None:
            return self.parent.get(name)
        if name in _BUILTINS:
            return _BUILTINS[name]
        raise NameError(f"name '{name}' is not defined")

    def set(self, name: str, value: Any) -> None:
        self.variables[name] = value

    def increment_steps(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise BudgetExceeded(f"exceeded {self.max_steps} step limit")


class PythonInterpreter:
    """Execute a restricted Python subset via AST walking.

    Args:
        limits: Execution limits (max_steps enforced; timeout_ms ignored for in-process).
        tools_ns: Optional tool namespace dict (e.g. {"tool": tool_callback}).
    """

    def __init__(self, limits: ExecutionLimits, tools_ns: dict[str, Any] | None = None) -> None:
        self._limits = limits
        self._tools_ns = tools_ns

    async def run(self, script: str, argv: list[str] | None = None) -> SandboxResult:
        """Run ``script`` through the interpreter, returning a SandboxResult."""
        # Step 1: Syntax check
        try:
            tree = compile(script, "<script>", "exec", flags=ast.PyCF_ONLY_AST)
        except SyntaxError as e:
            return SandboxFailure(
                error=Diagnostic(
                    kind=DiagnosticKind.EXECUTION_FAILURE,
                    message=f"script failed to compile: {e.msg} (line {e.lineno})",
                    location="<script>",
                    suggestions=["fix the syntax error and retry"],
                )
            )

        assert isinstance(tree, ast.Module)  # compile(..., ast.PyCF_ONLY_AST) always returns Module

        # Step 2: Forbidden operation check
        forbidden = self._check_forbidden(tree)
        if forbidden is not None:
            return SandboxFailure(
                error=Diagnostic(
                    kind=DiagnosticKind.EXECUTION_FAILURE,
                    message=forbidden,
                    location="<script>",
                    suggestions=["remove the forbidden operation"],
                )
            )

        # Step 3: Execute via AST walker
        ctx = InterpreterContext(
            max_steps=self._limits.max_steps,
            tools_ns=self._tools_ns,
        )
        if self._tools_ns:
            for k, v in self._tools_ns.items():
                ctx.set(k, v)
        # Inject argv if provided
        if argv:
            ctx.set("argv", argv)

        try:
            self._exec_module(tree, ctx)
        except BudgetExceeded as e:
            return SandboxFailure(
                error=Diagnostic(
                    kind=DiagnosticKind.TIMEOUT_EXCEEDED,
                    message=str(e),
                    location="<script>",
                    suggestions=[
                        "reduce the script's work or iterations",
                        "check for accidental infinite loops",
                    ],
                )
            )
        except _RuntimeError as e:
            # Runtime error → SandboxSuccess with non-zero exit and stderr
            return SandboxSuccess(
                stdout="".join(ctx.output),
                stderr=str(e),
                exit_code=1,
                truncated=False,
            )
        except Exception as e:
            return SandboxSuccess(
                stdout="".join(ctx.output),
                stderr=f"{type(e).__name__}: {e}",
                exit_code=1,
                truncated=False,
            )

        stdout = "".join(ctx.output)
        truncated = len(stdout) > self._limits.max_output_bytes
        if truncated:
            stdout = stdout[: self._limits.max_output_bytes]

        return SandboxSuccess(
            stdout=stdout,
            stderr="",
            exit_code=0,
            truncated=truncated,
        )

    def _check_forbidden(self, tree: ast.Module) -> str | None:
        """Static analysis: return error message if forbidden operation found, else None."""
        for node in ast.walk(tree):
            # Check node type
            if isinstance(node, _FORBIDDEN节点):
                return f"forbidden operation: {type(node).__name__}"
            # Check function calls
            if isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name in _FORBIDDEN函数:
                    return f"forbidden function call: {func_name}()"
        return None

    def _get_call_name(self, node: ast.Call) -> str | None:
        """Extract function name from a Call node (handles attribute access)."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return None

    def _exec_module(self, tree: ast.Module, ctx: InterpreterContext) -> None:
        """Execute a Module AST node."""
        for stmt in tree.body:
            self._exec_stmt(stmt, ctx)

    def _exec_stmt(self, node: ast.stmt, ctx: InterpreterContext) -> None:
        """Execute a single statement."""
        ctx.increment_steps()

        if isinstance(node, ast.Assign):
            value = self._eval_expr(node.value, ctx)
            for target in node.targets:
                self._assign(target, value, ctx)

        elif isinstance(node, ast.AugAssign):
            value = self._eval_expr(node.value, ctx)
            old = self._eval_expr(node.target, ctx)
            new = self._binop(old, node.op, value)
            self._assign(node.target, new, ctx)

        elif isinstance(node, ast.Expr):
            self._eval_expr(node.value, ctx)

        elif isinstance(node, ast.If):
            cond = self._eval_expr(node.test, ctx)
            if cond:
                for stmt in node.body:
                    self._exec_stmt(stmt, ctx)
            else:
                for stmt in node.orelse:
                    self._exec_stmt(stmt, ctx)

        elif isinstance(node, ast.While):
            while True:
                cond = self._eval_expr(node.test, ctx)
                if not cond:
                    break
                for stmt in node.body:
                    self._exec_stmt(stmt, ctx)

        elif isinstance(node, ast.For):
            iterable = self._eval_expr(node.iter, ctx)
            for item in iterable:
                self._assign(node.target, item, ctx)
                for stmt in node.body:
                    self._exec_stmt(stmt, ctx)

        elif isinstance(node, ast.FunctionDef):
            ctx.set(node.name, _Function(node, ctx))

        elif isinstance(node, ast.Return):
            value = self._eval_expr(node.value, ctx) if node.value is not None else None
            raise _Return(value)

        elif isinstance(node, ast.Break):
            raise _Break()

        elif isinstance(node, ast.Continue):
            raise _Continue()

        elif isinstance(node, (ast.Pass,)):
            pass

        else:
            # Unsupported statement → skip (conservative)
            pass

    def _assign(self, target: ast.expr, value: Any, ctx: InterpreterContext) -> None:
        """Assign a value to a target (Name, Subscript, or Attribute)."""
        if isinstance(target, ast.Name):
            ctx.set(target.id, value)
        elif isinstance(target, ast.Subscript):
            obj = self._eval_expr(target.value, ctx)
            key = self._eval_expr(target.slice, ctx)
            obj[key] = value
        elif isinstance(target, ast.Attribute):
            obj = self._eval_expr(target.value, ctx)
            setattr(obj, target.attr, value)
        else:
            raise _RuntimeError(f"unsupported assignment target: {type(target).__name__}")

    def _eval_expr(self, node: ast.expr, ctx: InterpreterContext) -> Any:
        """Evaluate an expression node and return its value."""
        ctx.increment_steps()

        if isinstance(node, ast.Constant):
            return node.value

        elif isinstance(node, ast.Name):
            return ctx.get(node.id)

        elif isinstance(node, ast.List):
            return [self._eval_expr(e, ctx) for e in node.elts]

        elif isinstance(node, ast.Dict):
            # node.keys can contain None for **kwargs unpacking; filter those out
            keys = [self._eval_expr(k, ctx) for k in node.keys if k is not None]
            values = [self._eval_expr(v, ctx) for v in node.values[:len(keys)]]
            return dict(zip(keys, values))

        elif isinstance(node, ast.Tuple):
            return tuple(self._eval_expr(e, ctx) for e in node.elts)

        elif isinstance(node, ast.Set):
            return {self._eval_expr(e, ctx) for e in node.elts}

        elif isinstance(node, ast.BinOp):
            left = self._eval_expr(node.left, ctx)
            right = self._eval_expr(node.right, ctx)
            return self._binop(left, node.op, right)

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_expr(node.operand, ctx)
            return self._unaryop(node.op, operand)

        elif isinstance(node, ast.BoolOp):
            values = [self._eval_expr(v, ctx) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            else:  # Or
                return any(values)

        elif isinstance(node, ast.Compare):
            return self._eval_compare(node, ctx)

        elif isinstance(node, ast.IfExp):
            cond = self._eval_expr(node.test, ctx)
            return self._eval_expr(node.body if cond else node.orelse, ctx)

        elif isinstance(node, ast.Call):
            return self._eval_call(node, ctx)

        elif isinstance(node, ast.Subscript):
            obj = self._eval_expr(node.value, ctx)
            key = self._eval_expr(node.slice, ctx)
            return obj[key]

        elif isinstance(node, ast.Attribute):
            obj = self._eval_expr(node.value, ctx)
            return getattr(obj, node.attr)

        elif isinstance(node, ast.ListComp):
            return self._eval_listcomp(node, ctx)

        else:
            raise _RuntimeError(f"unsupported expression: {type(node).__name__}")

    def _binop(self, left: Any, op: ast.operator, right: Any) -> Any:
        """Apply a binary operator."""
        if isinstance(op, ast.Add):
            return left + right
        elif isinstance(op, ast.Sub):
            return left - right
        elif isinstance(op, ast.Mult):
            return left * right
        elif isinstance(op, ast.Div):
            return left / right
        elif isinstance(op, ast.FloorDiv):
            return left // right
        elif isinstance(op, ast.Mod):
            return left % right
        elif isinstance(op, ast.Pow):
            return left ** right
        elif isinstance(op, ast.LShift):
            return left << right
        elif isinstance(op, ast.RShift):
            return left >> right
        elif isinstance(op, ast.BitAnd):
            return left & right
        elif isinstance(op, ast.BitOr):
            return left | right
        elif isinstance(op, ast.BitXor):
            return left ^ right
        else:
            raise _RuntimeError(f"unsupported operator: {type(op).__name__}")

    def _unaryop(self, op: ast.unaryop, operand: Any) -> Any:
        """Apply a unary operator."""
        if isinstance(op, ast.USub):
            return -operand
        elif isinstance(op, ast.UAdd):
            return +operand
        elif isinstance(op, ast.Not):
            return not operand
        elif isinstance(op, ast.Invert):
            return ~operand
        else:
            raise _RuntimeError(f"unsupported unary operator: {type(op).__name__}")

    def _eval_compare(self, node: ast.Compare, ctx: InterpreterContext) -> bool:
        """Evaluate chained comparisons (e.g. a < b < c)."""
        left = self._eval_expr(node.left, ctx)
        for op, comparator in zip(node.ops, node.comparators):
            right = self._eval_expr(comparator, ctx)
            if not self._cmpop(left, op, right):
                return False
            left = right
        return True

    def _cmpop(self, left: Any, op: ast.cmpop, right: Any) -> bool:
        if isinstance(op, ast.Eq):
            return bool(left == right)
        elif isinstance(op, ast.NotEq):
            return bool(left != right)
        elif isinstance(op, ast.Lt):
            return bool(left < right)
        elif isinstance(op, ast.LtE):
            return bool(left <= right)
        elif isinstance(op, ast.Gt):
            return bool(left > right)
        elif isinstance(op, ast.GtE):
            return bool(left >= right)
        elif isinstance(op, ast.Is):
            return bool(left is right)
        elif isinstance(op, ast.IsNot):
            return bool(left is not right)
        elif isinstance(op, ast.In):
            return bool(left in right)
        elif isinstance(op, ast.NotIn):
            return bool(left not in right)
        else:
            raise _RuntimeError(f"unsupported comparison: {type(op).__name__}")

    def _eval_call(self, node: ast.Call, ctx: InterpreterContext) -> Any:
        """Evaluate a function call."""
        func = self._eval_expr(node.func, ctx)
        args = [self._eval_expr(a, ctx) for a in node.args]
        kwargs = {kw.arg: self._eval_expr(kw.value, ctx) for kw in node.keywords if kw.arg is not None}

        # Handle built-in print
        if func is print:
            output = io.StringIO()
            print(*args, file=output, **kwargs)
            ctx.output.append(output.getvalue())
            return None

        # Handle tools_ns.tool(...)
        if callable(func):
            return func(*args, **kwargs)

        # Handle _Function (user-defined)
        if isinstance(func, _Function):
            return self._call_function(func, args, kwargs, ctx)

        raise _RuntimeError(f"unsupported callable: {type(func).__name__}")

    def _call_function(self, func: _Function, args: list[Any], kwargs: dict[str, Any], ctx: InterpreterContext) -> Any:
        """Call a user-defined function with a new scope."""
        child_ctx = InterpreterContext(
            parent=func.closure,
            max_steps=ctx.max_steps,
            tools_ns=ctx.tools_ns,
        )
        child_ctx.steps = ctx.steps  # share step counter

        # Bind positional args with defaults
        params = func.node.args.args
        defaults = func.node.args.defaults
        n_defaults = len(defaults)
        for i, param in enumerate(params):
            if i < len(args):
                child_ctx.set(param.arg, args[i])
            else:
                default_idx = i - (len(params) - n_defaults)
                if default_idx >= 0:
                    child_ctx.set(param.arg, self._eval_expr(defaults[default_idx], func.closure))
                else:
                    raise _RuntimeError(f"missing required argument: {param.arg}")
        # Bind keyword args
        for kwarg, value in kwargs.items():
            child_ctx.set(kwarg, value)

        # Execute function body
        try:
            for stmt in func.node.body:
                self._exec_stmt(stmt, child_ctx)
        except _Return as r:
            ctx.steps = child_ctx.steps
            ctx.output.extend(child_ctx.output)
            return r.value

        ctx.steps = child_ctx.steps
        ctx.output.extend(child_ctx.output)
        return None

    def _eval_listcomp(self, node: ast.ListComp, ctx: InterpreterContext) -> list[Any]:
        """Evaluate a list comprehension."""
        result = []
        for generator in node.generators:
            iterable = self._eval_expr(generator.iter, ctx)
            for item in iterable:
                self._assign(generator.target, item, ctx)
                if generator.ifs:
                    cond = all(self._eval_expr(if_node, ctx) for if_node in generator.ifs)
                    if not cond:
                        continue
                result.append(self._eval_expr(node.elt, ctx))
        return result


class _Function:
    """Wrapper for user-defined functions (closes over definition-time scope)."""

    def __init__(self, node: ast.FunctionDef, closure: InterpreterContext) -> None:
        self.node = node
        self.closure = closure


class _RuntimeError(Exception):
    """Internal runtime error (distinct from built-in RuntimeError)."""


class _Return(Exception):
    """Internal signal for return statements."""

    def __init__(self, value: Any = None) -> None:
        self.value = value


class _Break(Exception):
    """Internal signal for break statements."""


class _Continue(Exception):
    """Internal signal for continue statements."""
