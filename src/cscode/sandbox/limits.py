"""Execution limits for the restricted sandbox (spec §4.4.3)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Resource limits applied to every sandboxed script run.

    Attributes:
        timeout_ms: Hard wall-clock budget; exceeded → TIMEOUT_EXCEEDED.
        max_output_bytes: Cap on captured stdout; exceeded → truncated.
    """

    timeout_ms: int = 5_000
    max_output_bytes: int = 1_000_000
