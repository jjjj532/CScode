from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cscode.schema.ids import SessionID
from cscode.core.session import SessionProjector, SessionV2
from cscode.server.state import state
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


class CreateSessionRequest(BaseModel):
    title: str = "New Session"


@router.get("/sessions")
async def list_sessions(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    if state.event_store is None or state.projector is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    if state.db is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    cursor = await state.db.conn.execute(
        "SELECT aggregate_id FROM event_sequences ORDER BY aggregate_id LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()
    sessions = []
    for row in rows:
        aggregate_id = row["aggregate_id"]
        try:
            session_v2 = await SessionV2.load(state.event_store, aggregate_id)
            s = session_v2.state
            sessions.append({
                "id": str(s.session_id) if s.session_id else aggregate_id,
                "title": s.title,
                "provider": s.provider,
                "model": s.model,
                "status": s.status,
                "message_count": len(s.messages),
                "event_count": s.seq,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            })
        except Exception:
            continue
    return sessions


@router.post("/sessions")
async def create_session(req: CreateSessionRequest) -> dict[str, Any]:
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    from cscode.core.config import load_config
    config = load_config()
    session_v2 = await SessionV2.create(
        state.event_store,
        model=config.model,
        provider=config.provider,
        title=req.title,
    )
    return {"id": str(session_v2.session_id), "title": session_v2.state.title}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    await session_v2.delete()
    return {"status": "ok"}


@router.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str) -> dict[str, str]:
    if state.question_registry is not None:
        await state.question_registry.cancel_session(session_id)
    queue = state.session_queues.get(session_id)
    if queue is not None:
        await queue.put({"type": "step.ended", "data": {}, "session_id": session_id})
    task = state.active_agent_tasks.get(session_id)
    if task and not task.done():
        task.cancel()
        import asyncio
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    return {"status": "ok"}


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, title: str = "") -> dict[str, str]:
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    await session_v2.update_metadata(title=title if title else None)
    return {"status": "ok"}
