from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class TuiSession:
    id: str
    title: str
    provider: str
    model: str
    status: str = "active"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class TuiSessionManager:
    def __init__(self, max_sessions: int = 5) -> None:
        self._sessions: dict[str, TuiSession] = {}
        self._active_id: str | None = None
        self._max_sessions = max_sessions

    def create(self, title: str = "", provider: str = "openai", model: str = "gpt-4o") -> TuiSession:
        if len(self._sessions) >= self._max_sessions:
            raise ValueError(f"Maximum sessions ({self._max_sessions}) reached")

        session = TuiSession(
            id=str(uuid.uuid4()),
            title=title or f"Session {len(self._sessions) + 1}",
            provider=provider,
            model=model,
        )
        self._sessions[session.id] = session
        self._active_id = session.id
        return session

    def get(self, session_id: str) -> TuiSession | None:
        return self._sessions.get(session_id)

    def list(self) -> list[TuiSession]:
        return list(self._sessions.values())

    def set_active(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        self._active_id = session_id
        return True

    def get_active(self) -> TuiSession | None:
        if self._active_id is None:
            return None
        return self._sessions.get(self._active_id)

    def remove(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        if self._active_id == session_id:
            self._active_id = None
            if self._sessions:
                self._active_id = next(iter(self._sessions))
        return True
