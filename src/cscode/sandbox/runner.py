"""SandboxRunner — restricted subprocess execution (spec §4.4.3, route B).

Runs model-generated Python scripts with hard safety boundaries:

- ``sys.executable -I`` (isolated mode): no user site-packages, no
  PYTHONPATH, empty environment — no network/env leakage.
- ``asyncio.wait_for`` hard timeout; on expiry the child is killed and a
  TIMEOUT_EXCEEDED diagnostic is returned.
- stdout capped at ``max_output_bytes``; overflow → ``truncated=True``.
- Syntax errors are caught by a parent-side ``compile()`` pre-check and
  reported as EXECUTION_FAILURE (the script never ran).
- A script that runs and exits non-zero is still a SandboxSuccess — the
  exit code and stderr traceback are data, not diagnostics.
- ``shell=True`` is never used; the interpreter path is the whitelisted
  sys.executable; scripts run inside an injected temporary workdir.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from cscode.sandbox.diagnostics import Diagnostic, DiagnosticKind
from cscode.sandbox.limits import ExecutionLimits
from cscode.sandbox.result import SandboxFailure, SandboxResult, SandboxSuccess
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class SandboxRunner:
    """Execute a script under resource limits, returning a SandboxResult."""

    def __init__(self, limits: ExecutionLimits, workdir: str | None = None) -> None:
        self._limits = limits
        self._workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="cscode-sandbox-"))

    async def run(self, script: str, argv: list[str] | None = None) -> SandboxResult:
        """Run ``script`` in a fresh subprocess under configured limits."""
        script_path = self._workdir / "script.py"
        script_path.write_text(script, encoding="utf-8")

        # Pre-check: syntax errors mean the script can never execute.
        try:
            compile(script, str(script_path), "exec")
        except SyntaxError as e:
            return SandboxFailure(
                error=Diagnostic(
                    kind=DiagnosticKind.EXECUTION_FAILURE,
                    message=f"script failed to compile: {e.msg} (line {e.lineno})",
                    location=str(script_path),
                    suggestions=["fix the syntax error and retry"],
                )
            )

        timeout_s = self._limits.timeout_ms / 1000.0
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",
                str(script_path),
                *(argv or []),
                cwd=str(self._workdir),
                env={},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as e:
            logger.error("SandboxRunner: failed to start subprocess: %s", e)
            return SandboxFailure(
                error=Diagnostic(
                    kind=DiagnosticKind.EXECUTION_FAILURE,
                    message=f"failed to start interpreter: {e}",
                    suggestions=["check the Python interpreter installation"],
                )
            )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            return await self._handle_timeout(proc, script_path)

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        truncated = len(stdout_b) > self._limits.max_output_bytes
        if truncated:
            stdout = stdout[: self._limits.max_output_bytes]

        return SandboxSuccess(
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode or 0,
            truncated=truncated,
        )

    async def _handle_timeout(self, proc: asyncio.subprocess.Process, script_path: Path) -> SandboxResult:
        """Kill the child after timeout and return a TIMEOUT_EXCEEDED failure."""
        logger.warning(
            "SandboxRunner: timeout after %d ms killing %s",
            self._limits.timeout_ms,
            script_path.name,
        )
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        return SandboxFailure(
            error=Diagnostic(
                kind=DiagnosticKind.TIMEOUT_EXCEEDED,
                message=(
                    f"script exceeded {self._limits.timeout_ms} ms timeout and was killed"
                ),
                location=str(script_path),
                suggestions=[
                    "reduce the script's work or iterations",
                    "check for accidental infinite loops",
                ],
            )
        )
