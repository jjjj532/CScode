"""Unified API error contract types.

Every API endpoint returns errors in the same shape:
    {"error": {"code": "...", "message": "...", "details": ...}}

This is the single source of truth for error response structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    """An individual error description.

    Fields:
        code: Machine-readable error code (e.g. "NOT_FOUND", "VALIDATION_ERROR").
        message: Human-readable error description.
        details: Optional structured details for validation errors, etc.
    """

    code: str
    message: str
    details: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ErrorResponse:
    """Standard API error response body.

    Every error endpoint returns:
        {"error": {"code": "...", "message": "...", "details": ...}}
    """

    error: ErrorDetail

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Serialize to the standard error response dict format."""
        result: dict[str, Any] = {
            "code": self.error.code,
            "message": self.error.message,
            "details": self.error.details,
        }
        return {"error": result}
