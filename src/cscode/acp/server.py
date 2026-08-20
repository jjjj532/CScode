"""ACPServer — protocol endpoints bridged to SessionRunner (spec §5.1).

All endpoints reuse SessionRunner — no new execution path. Errors are
structured (LLMError from schema/errors.py), never bare exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cscode.schema.errors import LLMError, LLMErrorReason
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ACPResponse:
    """Structured response for an ACP request."""

    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: LLMError | None = None


class ACPServer:
    """Bridges ACP protocol endpoints to SessionRunner + session factory.

    Endpoints: session / load_session / resume_session / fork_session /
    prompt / cancel.
    """

    def __init__(self, runner: Any, session_factory: Any) -> None:
        self._runner = runner
        self._factory = session_factory

    async def handle(self, request: dict[str, Any]) -> ACPResponse:
        """Dispatch an ACP request to the matching endpoint."""
        method = str(request.get("method", ""))
        session_id = request.get("session_id")
        payload = request.get("payload") or {}

        try:
            if method == "session":
                return await self._create_session(payload)
            if method in ("load_session", "resume_session"):
                return await self._load_session(str(session_id))
            if method == "fork_session":
                return await self._fork_session(str(session_id))
            if method == "prompt":
                return await self._prompt(str(session_id), payload)
            if method == "cancel":
                return await self._cancel(str(session_id))
        except LLMError as e:
            logger.warning("ACP %s failed: %s", method, e)
            return ACPResponse(ok=False, error=e)

        return ACPResponse(
            ok=False,
            error=LLMError(
                module="ACP",
                method="handle",
                reason=LLMErrorReason.INVALID_REQUEST,
                message=f"unknown ACP method: {method}",
            ),
        )

    async def _create_session(self, payload: dict[str, Any]) -> ACPResponse:
        session = await self._factory.create(
            model=str(payload.get("model", "gpt-4o")),
            provider=str(payload.get("provider", "openai")),
            title=str(payload.get("title", "")),
            agent=str(payload.get("agent", "auto")),
            workspace_id=str(payload.get("workspace_id", "")),
        )
        logger.info("ACP session created: %s", session.session_id)
        return ACPResponse(ok=True, data={"session_id": str(session.session_id)})

    async def _load_session(self, session_id: str) -> ACPResponse:
        session = await self._factory.load(session_id)
        if not session.state.session_id:
            return self._no_route(session_id)
        return ACPResponse(ok=True, data={"session_id": str(session.session_id)})

    async def _fork_session(self, source_id: str) -> ACPResponse:
        """Create a new session replaying the source session's events.

        Event isolation: all forked events are appended under the NEW
        aggregate id; the source session is never mutated.
        """
        source = await self._factory.load(source_id)
        if not source.state.session_id:
            return self._no_route(source_id)

        store = source._event_store
        events = await store.read(source_id)
        forked = await self._factory.create(
            model=source.state.model,
            title=source.state.title,
            provider=source.state.provider,
            agent=source.state.agent,
        )
        replay = [{"type": e.type, "data": e.data} for e in events]
        await store.append(str(forked.session_id), replay)
        logger.info(
            "ACP forked session %s -> %s (%d events)",
            source_id, forked.session_id, len(replay),
        )
        return ACPResponse(ok=True, data={"session_id": str(forked.session_id)})

    async def _prompt(self, session_id: str, payload: dict[str, Any]) -> ACPResponse:
        session = await self._factory.load(session_id)
        if not session.state.session_id:
            return self._no_route(session_id)

        prompt_text = str(payload.get("prompt", ""))
        output = await self._runner.run(session, prompt_text)
        return ACPResponse(ok=True, data={"output": output})

    async def _cancel(self, session_id: str) -> ACPResponse:
        session = await self._factory.load(session_id)
        if not session.state.session_id:
            return self._no_route(session_id)
        return ACPResponse(ok=True, data={"status": "cancelled"})

    @staticmethod
    def _no_route(session_id: str) -> ACPResponse:
        return ACPResponse(
            ok=False,
            error=LLMError(
                module="ACP",
                method="handle",
                reason=LLMErrorReason.NO_ROUTE,
                message=f"session not found: {session_id}",
            ),
        )
