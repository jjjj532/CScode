"""Execution limits for the restricted sandbox (spec §4.4.3 + §6.6 G-12)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Resource limits applied to every sandboxed script run.

    Attributes:
        timeout_ms: Hard wall-clock budget; exceeded → TIMEOUT_EXCEEDED.
        max_output_bytes: Cap on captured stdout; exceeded → truncated.
        max_steps: Interpreter step budget (Route A).
        allowed_read_paths: FS paths readable by the subprocess (Landlock, Linux only).
        allowed_write_paths: FS paths writable by the subprocess (Landlock, Linux only).
    """

    timeout_ms: int = 5_000
    max_output_bytes: int = 1_000_000
    max_steps: int = 1_000
    allowed_read_paths: list[str] = field(default_factory=list)
    allowed_write_paths: list[str] = field(default_factory=list)
