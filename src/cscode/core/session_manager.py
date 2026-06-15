from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SessionStatus(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    TERMINATED = "terminated"


@dataclass
class Session:
    id: str
    title: str
    provider: str
    model: str
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SessionManager:
    """Manage multiple parallel sessions."""

    def __init__(self, max_sessions: int = 5):
        self._sessions: dict[str, Session] = {}
        self._active_session_id: str | None = None
        self._max_sessions = max_sessions

    def create(
        self,
        title: str = "",
        provider: str = "openai",
        model: str = "gpt-4o",
    ) -> Session:
        if len(self._sessions) >= self._max_sessions:
            raise ValueError(f"Maximum sessions ({self._max_sessions}) reached")

        session = Session(
            id=str(uuid.uuid4()),
            title=title or f"Session {len(self._sessions) + 1}",
            provider=provider,
            model=model,
        )
        self._sessions[session.id] = session
        self._active_session_id = session.id
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def list(self) -> list[Session]:
        return list(self._sessions.values())

    def set_active(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        self._active_session_id = session_id
        return True

    def get_active(self) -> Session | None:
        if self._active_session_id is None:
            return None
        return self._sessions.get(self._active_session_id)

    def remove(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        if self._active_session_id == session_id:
            self._active_session_id = None
            if self._sessions:
                self._active_session_id = next(iter(self._sessions))
        return True
