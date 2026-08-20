"""Diagnostic algebra for the sandbox (spec §4.4.3).

Aligned with OpenCode's DiagnosticKind, trimmed to the Python subprocess
scenario: timeout, output overflow, execution failure, internal error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DiagnosticKind(str, Enum):
    TIMEOUT_EXCEEDED = "timeout_exceeded"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    EXECUTION_FAILURE = "execution_failure"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Structured failure description.

    Attributes:
        kind: Which failure class occurred.
        message: Human-readable summary (for EXECUTION_FAILURE: stderr digest).
        location: Optional source location hint (file:line).
        suggestions: Actionable recovery hints for the caller/model.
    """

    kind: DiagnosticKind
    message: str
    location: str | None = None
    suggestions: list[str] = field(default_factory=list)
