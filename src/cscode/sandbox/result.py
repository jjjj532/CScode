"""SandboxResult discriminated union (spec §4.4.3).

Failure is data, not an exception: callers receive SandboxFailure with a
structured Diagnostic and must handle both states (exhaustive match).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cscode.sandbox.diagnostics import Diagnostic


@dataclass(frozen=True, slots=True)
class SandboxSuccess:
    ok: Literal[True] = True
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class SandboxFailure:
    ok: Literal[False] = False
    error: Diagnostic = None  # type: ignore[assignment]  # required field, no default


SandboxResult = SandboxSuccess | SandboxFailure
"""Discriminated union; narrow via ``ok`` or match/case + assert_never."""
