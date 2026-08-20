"""Restricted execution sandbox (spec §4.4).

Route B: constrained subprocess runner with timeout, output limits, and
diagnostic algebra. Failure is data (SandboxFailure), not an exception.
"""

from cscode.sandbox.diagnostics import Diagnostic, DiagnosticKind
from cscode.sandbox.limits import ExecutionLimits
from cscode.sandbox.result import SandboxFailure, SandboxResult, SandboxSuccess
from cscode.sandbox.runner import SandboxRunner

__all__ = [
    "SandboxRunner",
    "ExecutionLimits",
    "Diagnostic",
    "DiagnosticKind",
    "SandboxResult",
    "SandboxSuccess",
    "SandboxFailure",
]
