"""Session endpoint contracts — typed API shapes for session CRUD + run-state.

These types define the request/response shapes for all /api/sessions/* endpoints.
No FastAPI dependency — pure contract definitions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionListParams:
    """Query parameters for GET /api/sessions."""

    limit: int = 50
    """Maximum number of sessions to return."""
    offset: int = 0
    """Number of sessions to skip (for pagination)."""


@dataclass(frozen=True, slots=True)
class CreateSessionRequest:
    """Request body for POST /api/sessions."""

    title: str = "New Session"
    """Human-readable session title."""


@dataclass(frozen=True, slots=True)
class SessionResponse:
    """Response shape for a single session (list/detail)."""

    id: str
    """Unique session identifier."""
    title: str
    """Session title."""
    provider: str
    """LLM provider name."""
    model: str
    """Model identifier."""
    status: str
    """Session status."""
    created_at: float
    """Unix timestamp of creation."""
    updated_at: float
    """Unix timestamp of last update."""
    message_count: int = 0
    """Number of messages in the session."""
    event_count: int = 0
    """Number of persisted events."""


@dataclass(frozen=True, slots=True)
class RunStateRequest:
    """Request body for PUT /api/sessions/{id}/run-state."""

    status: str
    """Run status to set (running, stopped, errored, completed)."""
    error: str = ""
    """Error message (only for errored status)."""


@dataclass(frozen=True, slots=True)
class RunStateResponse:
    """Response body for GET/PUT /api/sessions/{id}/run-state."""

    status: str
    """Current run status."""
    error: str = ""
    """Current run error (empty if no error)."""
