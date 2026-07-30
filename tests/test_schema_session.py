"""Tests for Schema Session types — SessionInfo, SessionState.

These types are pure frozen dataclasses in the schema layer.
They must have zero runtime dependencies on cscode.core or cscode.server.
"""

from __future__ import annotations

from cscode.schema.session import SessionInfo, SessionState


class TestSessionInfo:
    """SessionInfo — lightweight session summary for list endpoints."""

    def test_minimal_construction(self) -> None:
        """SessionInfo requires only id, title, provider, model."""
        info = SessionInfo(
            id="sess_abc",
            title="My Session",
            provider="openai",
            model="gpt-4o",
            status="active",
            created_at=1000.0,
            updated_at=2000.0,
        )
        assert info.id == "sess_abc"
        assert info.title == "My Session"
        assert info.provider == "openai"
        assert info.model == "gpt-4o"
        assert info.status == "active"
        assert info.created_at == 1000.0
        assert info.updated_at == 2000.0

    def test_default_counts(self) -> None:
        """message_count and event_count default to 0."""
        info = SessionInfo(
            id="s1", title="T", provider="p", model="m",
            status="active", created_at=0.0, updated_at=0.0,
        )
        assert info.message_count == 0
        assert info.event_count == 0

    def test_custom_counts(self) -> None:
        """message_count and event_count can be set."""
        info = SessionInfo(
            id="s1", title="T", provider="p", model="m",
            status="active", created_at=0.0, updated_at=0.0,
            message_count=5, event_count=42,
        )
        assert info.message_count == 5
        assert info.event_count == 42

    def test_immutable(self) -> None:
        """SessionInfo is frozen — cannot mutate fields."""
        info = SessionInfo(
            id="s1", title="T", provider="p", model="m",
            status="active", created_at=0.0, updated_at=0.0,
        )
        import dataclasses
        assert dataclasses.fields(info)  # is a dataclass
        assert info.__dataclass_params__.frozen  # is frozen  # type: ignore[attr-defined]

    def test_slots(self) -> None:
        """SessionInfo uses __slots__ for memory efficiency."""
        info = SessionInfo(
            id="s1", title="T", provider="p", model="m",
            status="active", created_at=0.0, updated_at=0.0,
        )
        assert not hasattr(info, "__dict__")


class TestSessionState:
    """SessionState — full session metadata state (without messages)."""

    def test_minimal_construction(self) -> None:
        """SessionState requires only session_id."""
        state = SessionState(session_id="sess_123")
        assert state.session_id == "sess_123"
        assert state.title == ""
        assert state.provider == "openai"
        assert state.model == "gpt-4o"
        assert state.status == "active"

    def test_full_construction(self) -> None:
        """SessionState accepts all fields."""
        state = SessionState(
            session_id="sess_456",
            title="My Chat",
            provider="anthropic",
            model="claude-3-5-sonnet",
            agent="auto",
            status="active",
            created_at=1000.0,
            updated_at=2000.0,
            seq=42,
            workspace_id="ws_1",
            instruction="Be helpful",
            run_status="completed",
            run_error="",
            tool_rounds=3,
        )
        assert state.session_id == "sess_456"
        assert state.title == "My Chat"
        assert state.provider == "anthropic"
        assert state.model == "claude-3-5-sonnet"
        assert state.agent == "auto"
        assert state.status == "active"
        assert state.created_at == 1000.0
        assert state.updated_at == 2000.0
        assert state.seq == 42
        assert state.workspace_id == "ws_1"
        assert state.instruction == "Be helpful"
        assert state.run_status == "completed"
        assert state.run_error == ""
        assert state.tool_rounds == 3

    def test_defaults(self) -> None:
        """Optional fields have sensible defaults."""
        state = SessionState(session_id="sess_789")
        assert state.seq == 0
        assert state.workspace_id == ""
        assert state.instruction == ""
        assert state.run_status == "idle"
        assert state.run_error == ""
        assert state.tool_rounds == 0
        assert state.created_at == 0.0
        assert state.updated_at == 0.0

    def test_immutable(self) -> None:
        """SessionState is frozen."""
        state = SessionState(session_id="sess_immutable")
        import dataclasses
        assert state.__dataclass_params__.frozen  # type: ignore[attr-defined]

    def test_slots(self) -> None:
        """SessionState uses __slots__."""
        state = SessionState(session_id="sess_slots")
        assert not hasattr(state, "__dict__")

    def test_no_runtime_deps(self) -> None:
        """SessionState does not import from cscode.core or cscode.server."""
        import inspect
        source = inspect.getsource(SessionState)
        assert "cscode.core" not in source
        assert "cscode.server" not in source
