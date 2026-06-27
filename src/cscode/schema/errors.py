"""Typed error model for LLM interactions and tool execution.

Mirrors OpenCode's LLMError hierarchy:
  - LLMErrorReason: 10-class taxonomy with retryability
  - LLMError: structured exception with module/method/reason
  - ToolFailure: tool-level execution failure (not network/API error)

Usage:
    raise LLMError(module="LLM", method="stream",
                   reason=LLMErrorReason.RATE_LIMIT,
                   message="429 Too Many Requests",
                   retryable=True, retry_after_ms=5000)

    raise ToolFailure("File not found: /tmp/x")
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class LLMErrorReason(StrEnum):
    """Ten-class error taxonomy for LLM provider interactions.

    Each reason explicitly states whether the operation is retryable.
    """

    INVALID_REQUEST = "InvalidRequest"
    """Malformed request parameters. NOT retryable — fix the request."""

    NO_ROUTE = "NoRoute"
    """No Route definition matches the requested provider/model. NOT retryable."""

    AUTHENTICATION = "Authentication"
    """Missing, invalid, or expired credentials. NOT retryable."""

    RATE_LIMIT = "RateLimit"
    """Provider rate limit exceeded. Retryable — use retry_after_ms."""

    QUOTA_EXCEEDED = "QuotaExceeded"
    """Provider quota exhausted. NOT retryable — wait for reset."""

    CONTENT_POLICY = "ContentPolicy"
    """Content rejected by provider safety filters. NOT retryable."""

    PROVIDER_INTERNAL = "ProviderInternal"
    """Provider server error (5xx). Retryable with backoff."""

    TRANSPORT = "Transport"
    """Network-level failure (DNS, connection refused, TLS). NOT retryable
    at the application level — underlying transport handles retry."""

    INVALID_PROVIDER_OUTPUT = "InvalidProviderOutput"
    """Provider returned unparseable or structurally invalid response.
    NOT retryable — likely a bug in the provider adapter."""

    UNKNOWN_PROVIDER = "UnknownProvider"
    """Provider ID does not match any configured provider.
    NOT retryable — fix the configuration."""


# Static lookup for retryability. Kept as module-level mapping rather than
# a method on the enum so match/case on reason stays pure.
_RETRYABLE: Final[set[LLMErrorReason]] = {
    LLMErrorReason.RATE_LIMIT,
    LLMErrorReason.PROVIDER_INTERNAL,
}


def is_retryable(reason: LLMErrorReason) -> bool:
    """Return True if operations with this reason should be retried."""
    return reason in _RETRYABLE


class LLMError(Exception):
    """Structured exception for LLM provider errors.

    Fields:
        module: Source module name (e.g. 'LLM', 'SessionRunner')
        method: Method name (e.g. 'generate', 'stream')
        reason: Error classification from LLMErrorReason
        message: Human-readable description
        retryable: Whether the operation can be retried
        retry_after_ms: Optional backoff hint (only for RATE_LIMIT)
    """

    def __init__(
        self,
        *,
        module: str,
        method: str,
        reason: LLMErrorReason,
        message: str,
        retryable: bool | None = None,
        retry_after_ms: int | None = None,
    ) -> None:
        self.module = module
        self.method = method
        self.reason = reason
        self.message = message
        self.retryable = is_retryable(reason) if retryable is None else retryable
        self.retry_after_ms = retry_after_ms
        super().__init__(self._format())

    def _format(self) -> str:
        parts = [
            f"[{self.reason.value}]",
            f"{self.module}.{self.method}",
            self.message,
        ]
        if self.retry_after_ms is not None:
            parts.append(f"(retry after {self.retry_after_ms}ms)")
        return " — ".join(parts)

    @staticmethod
    def _pickle_reconstruct(
        module: str,
        method: str,
        reason: str,
        message: str,
        retryable: bool,
        retry_after_ms: int | None,
    ) -> LLMError:
        """Reconstruct an LLMError from pickled fields."""
        return LLMError(
            module=module,
            method=method,
            reason=LLMErrorReason(reason),
            message=message,
            retryable=retryable,
            retry_after_ms=retry_after_ms,
        )

    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        """Pickling support keeps structured fields intact."""
        return (
            LLMError._pickle_reconstruct,
            (self.module, self.method, self.reason.value, self.message, self.retryable, self.retry_after_ms),
        )


class ToolFailure(Exception):
    """Tool-level execution failure.

    Raised when a tool's execute handler encounters an error
    (file not found, command timeout, permission denied, etc).
    This is NOT a network/API error — those use LLMError.
    """

    def __init__(self, message: str, /) -> None:
        self.message = message
        super().__init__(message)
