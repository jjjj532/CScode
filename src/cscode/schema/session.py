"""Session domain model types — pure data definitions with zero runtime dependencies.

These types are the canonical schema for session metadata in the CScode
architecture. They contain NO business logic, NO event sourcing, and NO
dependencies on cscode.core or cscode.server.

    SessionInfo    — Lightweight summary for list/detail API responses.
    SessionState   — Full session metadata (without message content).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """Lightweight session summary for API list/detail responses.

    Does NOT include messages — those are fetched separately via the
    session messages endpoint.
    """

    id: str
    """Unique session identifier."""

    title: str
    """Human-readable session title."""

    provider: str
    """LLM provider name (e.g. 'openai', 'anthropic')."""

    model: str
    """Model identifier (e.g. 'gpt-4o', 'claude-3-5-sonnet')."""

    status: str
    """Session status ('active', 'archived', 'deleted')."""

    created_at: float
    """Unix timestamp when the session was created."""

    updated_at: float
    """Unix timestamp when the session was last updated."""

    message_count: int = 0
    """Number of messages in the session."""

    event_count: int = 0
    """Number of events persisted for the session."""


@dataclass(frozen=True, slots=True)
class SessionState:
    """Full session metadata state, projected from the event stream.

    This is the metadata portion only — message content lives in
    ``schema/messages.py`` as ``Message`` objects.

    Fields match the projection in ``core/session.py::SessionState``
    but are frozen and dependency-free.
    """

    session_id: str
    """Unique session identifier."""

    title: str = ""
    """Human-readable session title."""

    provider: str = "openai"
    """LLM provider name."""

    model: str = "gpt-4o"
    """Model identifier."""

    agent: str = "auto"
    """Agent mode ('auto', 'general', or a named agent)."""

    status: str = "active"
    """Session status."""

    created_at: float = 0.0
    """Unix timestamp of creation."""

    updated_at: float = 0.0
    """Unix timestamp of last update."""

    seq: int = 0
    """Latest event sequence number applied to this state."""

    workspace_id: str = ""
    """Associated workspace ID (empty = not associated)."""

    instruction: str = ""
    """Per-session custom instruction injected into the system prompt."""

    run_status: str = "idle"
    """Execution run status: idle, running, stopped, errored, completed."""

    run_error: str = ""
    """Error message from the last failed run (empty if no error)."""

    tool_rounds: int = 0
    """Number of tool-call rounds completed in this session."""
