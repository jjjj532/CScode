"""Tests for Protocol error types — unified API error contract.

The protocol layer is a dependency-free contract layer between
schema (pure types) and server/routes (FastAPI implementation).
"""

from __future__ import annotations

from cscode.protocol.errors import ErrorDetail, ErrorResponse


class TestErrorDetail:
    """ErrorDetail — an individual error description."""

    def test_minimal_construction(self) -> None:
        detail = ErrorDetail(code="NOT_FOUND", message="Session not found")
        assert detail.code == "NOT_FOUND"
        assert detail.message == "Session not found"
        assert detail.details is None

    def test_with_details(self) -> None:
        detail = ErrorDetail(
            code="VALIDATION_ERROR",
            message="Invalid input",
            details={"field": "title", "reason": "too short"},
        )
        assert detail.details == {"field": "title", "reason": "too short"}

    def test_immutable(self) -> None:
        import dataclasses
        detail = ErrorDetail(code="ERR", message="test")
        assert detail.__dataclass_params__.frozen  # type: ignore[attr-defined]

    def test_no_runtime_deps(self) -> None:
        import inspect
        source = inspect.getsource(ErrorDetail)
        assert "cscode.core" not in source
        assert "cscode.server" not in source


class TestErrorResponse:
    """ErrorResponse — standard API error response body."""

    def test_construction(self) -> None:
        detail = ErrorDetail(code="NOT_FOUND", message="Session not found")
        resp = ErrorResponse(error=detail)
        assert resp.error.code == "NOT_FOUND"
        assert resp.error.message == "Session not found"

    def test_to_dict(self) -> None:
        detail = ErrorDetail(code="ERR", message="fail")
        resp = ErrorResponse(error=detail)
        d = resp.to_dict()
        assert d == {"error": {"code": "ERR", "message": "fail", "details": None}}

    def test_with_details_dict(self) -> None:
        detail = ErrorDetail(code="VALIDATION", message="bad", details={"x": "y"})
        resp = ErrorResponse(error=detail)
        d = resp.to_dict()
        assert d["error"]["details"] == {"x": "y"}
