from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from cscode.storage.session import SessionStore


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

    def __init__(self, max_sessions: int = 5, session_store: SessionStore | None = None):
        if max_sessions <= 0:
            raise ValueError("max_sessions must be greater than 0")
        self._sessions: dict[str, Session] = {}
        self._active_session_id: str | None = None
        self._max_sessions = max_sessions
        self._session_store = session_store

    async def _persist_create(self, session: Session) -> None:
        if self._session_store:
            await self._session_store.create(
                title=session.title,
                provider=session.provider,
                model=session.model,
                session_id=session.id,
            )

    async def _persist_delete(self, session_id: str) -> None:
        if self._session_store:
            await self._session_store.delete(session_id)

    async def create(
        self,
        title: str = "",
        provider: str = "openai",
        model: str = "gpt-4o",
    ) -> Session:
        """Create a new session.

        Args:
            title: Optional title for the session.
            provider: The provider name (e.g., "openai").
            model: The model name (e.g., "gpt-4o").

        Returns:
            The newly created Session.

        Raises:
            ValueError: If max sessions reached, or provider/model is empty.
        """
        if not provider or not provider.strip():
            raise ValueError("provider cannot be empty")
        if not model or not model.strip():
            raise ValueError("model cannot be empty")
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
        await self._persist_create(session)
        return session

    def get(self, session_id: str) -> Session | None:
        """Get a session by ID.

        Args:
            session_id: The session ID to look up.

        Returns:
            The Session if found, None otherwise.
        """
        return self._sessions.get(session_id)

    def list(self) -> list[Session]:
        """List all sessions.

        Returns:
            A list of all sessions.
        """
        return list(self._sessions.values())

    def set_active(self, session_id: str) -> bool:
        """Set the active session.

        Args:
            session_id: The session ID to set as active.

        Returns:
            True if successful, False if session not found.
        """
        if session_id not in self._sessions:
            return False
        self._active_session_id = session_id
        return True

    def get_active(self) -> Session | None:
        """Get the currently active session.

        Returns:
            The active Session, or None if no active session.
        """
        if self._active_session_id is None:
            return None
        return self._sessions.get(self._active_session_id)

    async def remove(self, session_id: str) -> bool:
        """Remove a session.

        Args:
            session_id: The session ID to remove.

        Returns:
            True if removed, False if session not found.
        """
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        if self._active_session_id == session_id:
            self._active_session_id = None
            if self._sessions:
                self._active_session_id = next(iter(self._sessions))
        await self._persist_delete(session_id)
        return True
