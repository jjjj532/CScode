from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cscode.core.session import SessionV2
from cscode.schema.ids import SessionID
from cscode.server.state import state
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


class CreateSessionRequest(BaseModel):
    title: str = "New Session"


class RunStateRequest(BaseModel):
    status: str
    error: str = ""


@router.get("/sessions")
async def list_sessions(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    if state.event_store is None or state.projector is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    if state.db is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    cursor = await state.db.conn.execute(
        "SELECT aggregate_id FROM event_sequences ORDER BY aggregate_id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()
    sessions = []
    for row in rows:
        aggregate_id = row["aggregate_id"]
        try:
            session_v2 = await SessionV2.load(state.event_store, aggregate_id)
            s = session_v2.state
            if s.status == "deleted":
                continue
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


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    if state.event_store is None or state.projector is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    try:
        session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
        s = session_v2.state
        if s.status == "deleted":
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "id": str(s.session_id) if s.session_id else session_id,
            "title": s.title,
            "provider": s.provider,
            "model": s.model,
            "status": s.status,
            "message_count": len(s.messages),
            "event_count": s.seq,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Session not found")


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
    if state.audit_log:
        await state.audit_log.record(
            action_type="session.create",
            resource_type="session",
            resource_id=str(session_v2.session_id),
            detail={"title": req.title},
        )
    return {"id": str(session_v2.session_id), "title": session_v2.state.title}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    await session_v2.delete()
    if state.audit_log:
        await state.audit_log.record(
            action_type="session.delete",
            resource_type="session",
            resource_id=session_id,
            detail={"title": session_v2.state.title},
        )
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


@router.get("/sessions/{session_id}/run-state")
async def get_run_state(session_id: str) -> dict[str, str]:
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "status": session_v2.state.run_status,
        "error": session_v2.state.run_error,
    }


VALID_RUN_STATUSES = frozenset({"running", "stopped", "errored", "completed"})


@router.put("/sessions/{session_id}/run-state")
async def set_run_state(session_id: str, body: RunStateRequest) -> dict[str, str]:
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    if body.status not in VALID_RUN_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
    method_map = {
        "running": session_v2.mark_run_start,
        "stopped": session_v2.mark_run_stop,
        "errored": lambda: session_v2.mark_run_error(error=body.error),
        "completed": session_v2.mark_run_complete,
    }
    fn = method_map[body.status]
    await fn()
    reloaded = await SessionV2.load(state.event_store, SessionID(session_id))
    return {
        "status": reloaded.state.run_status,
        "error": reloaded.state.run_error,
    }
