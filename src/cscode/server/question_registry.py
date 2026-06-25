from __future__ import annotations

import asyncio
import uuid
from typing import Any

import logging
logger = logging.getLogger(__name__)


class QuestionRegistry:
    """
    Per-server registry of pending question tool calls.

    Analogous to opencode's QuestionV2 layer with Deferred-based blocking.
    When a tool calls question.ask(), it awaits a Future in this registry.
    When the user replies via API, the Future resolves and the tool resumes.
    """

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        session_id: str,
        tool_call_id: str,
        questions: list[dict[str, Any]],
    ) -> list[str]:
        """
        Register a pending question and await the answer.

        Returns the list of answers once `resolve()` is called.
        """
        request_id = str(uuid.uuid4())
        future: asyncio.Future[list[str]] = asyncio.get_running_loop().create_future()

        async with self._lock:
            self._pending[request_id] = {
                "session_id": session_id,
                "tool_call_id": tool_call_id,
                "questions": questions,
                "future": future,
            }

        logger.info(
            "Question registered: request_id=%s session=%s tool_call=%s",
            request_id, session_id, tool_call_id,
        )

        try:
            answers = await future
            logger.info("Question answered: request_id=%s", request_id)
            return answers
        except asyncio.CancelledError:
            logger.info("Question cancelled: request_id=%s", request_id)
            async with self._lock:
                self._pending.pop(request_id, None)
            raise

    async def resolve(self, request_id: str, answers: list[str]) -> bool:
        """Resolve a pending question with answers. Returns True if found."""
        async with self._lock:
            entry = self._pending.pop(request_id, None)
        if entry is None:
            logger.warning("Question not found for resolve: request_id=%s", request_id)
            return False
        future: asyncio.Future = entry["future"]
        if not future.done():
            future.set_result(answers)
            return True
        return False

    async def reject(self, request_id: str) -> bool:
        """Reject/cancel a pending question. Returns True if found."""
        async with self._lock:
            entry = self._pending.pop(request_id, None)
        if entry is None:
            return False
        future: asyncio.Future = entry["future"]
        if not future.done():
            future.set_exception(asyncio.CancelledError("Question rejected by user"))
            return True
        return False

    async def list_pending(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """List all pending questions, optionally filtered by session_id."""
        async with self._lock:
            entries = []
            for req_id, entry in self._pending.items():
                if session_id is None or entry["session_id"] == session_id:
                    entries.append({
                        "request_id": req_id,
                        "session_id": entry["session_id"],
                        "tool_call_id": entry["tool_call_id"],
                        "questions": entry["questions"],
                    })
            return entries

    async def cancel_session(self, session_id: str) -> None:
        """Cancel all pending questions for a session."""
        async with self._lock:
            to_cancel = [
                req_id for req_id, entry in self._pending.items()
                if entry["session_id"] == session_id
            ]
            for req_id in to_cancel:
                entry = self._pending.pop(req_id)
                future: asyncio.Future = entry["future"]
                if not future.done():
                    future.set_exception(asyncio.CancelledError("Session interrupted"))
