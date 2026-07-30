from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from cscode.core.session import SessionProjector, SessionV2
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


@router.get("/sessions/{session_id}/instruction")
async def get_session_instruction(session_id: str) -> dict[str, str]:
    """P2-6: Get the per-session custom instruction."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"instruction": session_v2.state.instruction}


@router.put("/sessions/{session_id}/instruction")
async def set_session_instruction(session_id: str, body: dict[str, object]) -> dict[str, str]:
    """P2-6: Set or update the per-session custom instruction."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    instruction = str(body.get("instruction", ""))
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    await session_v2.set_instruction(instruction)
    return {"instruction": session_v2.state.instruction}


@router.delete("/sessions/{session_id}/instruction")
async def delete_session_instruction(session_id: str) -> dict[str, bool]:
    """P2-6: Remove the per-session custom instruction."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    await session_v2.delete_instruction()
    return {"deleted": True}


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


@router.get("/sessions/{session_id}/overflow")
async def get_session_overflow(session_id: str) -> dict[str, bool | int]:
    """P2-12: Check if a session is overflowing (too many messages)."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    info = session_v2.check_overflow()
    return {
        "overflowing": info["overflowing"],
        "near_overflow": info["near_overflow"],
        "message_count": info["message_count"],
        "threshold": info["threshold"],
    }


@router.get("/sessions/{session_id}/info")
async def get_session_info(session_id: str) -> dict[str, object]:
    """P2-7: Return full session metadata."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")

    st = session_v2.state
    return {
        "session_id": str(st.session_id),
        "title": st.title,
        "model": st.model,
        "provider": st.provider,
        "agent": st.agent,
        "status": st.status,
        "workspace_id": st.workspace_id,
        "message_count": len(st.messages),
        "event_count": st.seq,
        "tool_rounds": st.tool_rounds,
        "created_at": st.created_at,
        "updated_at": st.updated_at,
        "seq": st.seq,
    }


def _make_msg_id(role: str, content: str, index: int) -> str:
    """Generate a stable synthetic message ID from role + content hash."""
    raw = f"{role}:{content}:{index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@router.post("/sessions/{session_id}/workspace")
async def associate_session_workspace(
    session_id: str,
    body: dict[str, str],
) -> dict[str, str]:
    """P2-3: Associate a session with a workspace."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    ws_id = body.get("workspace_id", "")
    if not ws_id:
        raise HTTPException(status_code=400, detail="workspace_id is required")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    await session_v2.associate_workspace(ws_id)
    return {"status": "ok"}


@router.post("/sessions/{session_id}/move-workspace")
async def move_session_workspace(
    session_id: str,
    body: dict[str, str],
) -> dict[str, str]:
    """P2-4: Move a session to another workspace."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    to_ws = body.get("to_workspace_id", "")
    if not to_ws:
        raise HTTPException(status_code=400, detail="to_workspace_id is required")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    await session_v2.move_workspace(to_ws)
    return {"status": "ok"}


@router.post("/sessions/{session_id}/export")
async def export_session(session_id: str) -> Response:
    """P2-4: Export a session as JSON file."""
    if state.event_store is None or state.projector is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    events = await state.event_store.read(session_id)
    proj_state = SessionProjector.project(events)

    data = {
        "session_id": str(proj_state.session_id),
        "title": proj_state.title,
        "provider": proj_state.provider,
        "model": proj_state.model,
        "created_at": proj_state.created_at,
        "updated_at": proj_state.updated_at,
        "messages": [
            {"role": msg.role, "content": msg.content}
            for msg in proj_state.messages
        ],
    }
    safe_filename = proj_state.title.replace(" ", "_")
    encoded_filename = quote(safe_filename, safe="", encoding="utf-8")
    return Response(
        content=json.dumps(data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}.json"},
    )


@router.post("/sessions/{session_id}/model")
async def switch_model(session_id: str, body: dict[str, object]) -> dict[str, str]:
    """P1-5: Switch the model/provider for a session."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    model = body.get("model", session_v2.state.model)
    provider = body.get("provider", session_v2.state.provider)
    await session_v2.update_metadata(model=str(model))
    logger.info("Session %s model switched to %s (provider=%s)", session_id, model, provider)
    return {"status": "ok"}


@router.post("/sessions/{session_id}/agent")
async def switch_agent(session_id: str, body: dict[str, object]) -> dict[str, str]:
    """P1-5: Switch the agent for a session."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    agent = body.get("agent", "auto")
    await session_v2.update_metadata(agent=str(agent))
    logger.info("Session %s agent switched to %s", session_id, agent)
    return {"status": "ok"}


@router.get("/sessions/{session_id}/context")
async def get_session_context(session_id: str) -> list[dict[str, object]]:
    """P1-2: Return LLM context messages for a session (with system prompts)."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    plugin_text = (
        await state.plugin_host.render_plugin_context()
        if state.plugin_host is not None else ""
    )
    messages = SessionProjector.build_context(
        session_v2.state,
        plugin_context_text=plugin_text,
    )
    return [{"role": msg.role, "content": msg.content} for msg in messages]


@router.get("/sessions/{session_id}/summary")
async def get_session_summary(session_id: str) -> dict[str, object]:
    """P1-8: Return a statistical summary of a session."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    from cscode.core.session_summary import SessionSummary

    return SessionSummary(session_v2).generate()


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str) -> list[dict[str, object]]:
    """P0-1: Return messages for a session (used by sidebar session switching)."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = SessionProjector.build_context(session_v2.state)
    return [
        {
            "role": msg.role,
            "content": msg.content,
            "id": str(msg.id) if msg.id is not None else _make_msg_id(msg.role, msg.content, i),
        }
        for i, msg in enumerate(messages)
    ]


@router.get("/sessions/{session_id}/reminders")
async def list_reminders(session_id: str) -> dict[str, list[dict[str, object]]]:
    """P2-14: List all reminders for a session."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"reminders": session_v2.state.reminders}


@router.post("/sessions/{session_id}/reminders")
async def add_reminder(session_id: str, body: dict[str, str]) -> dict[str, object]:
    """P2-14: Add a reminder to a session."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return await session_v2.add_reminder(text)


@router.post("/sessions/{session_id}/retry")
async def retry_session(session_id: str) -> dict[str, bool | str | int]:
    """P2-13: Retry the last prompt in a session."""
    if state.event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    last = session_v2.get_last_prompt()
    if last is None:
        raise HTTPException(status_code=400, detail="No prompt to retry")
    events = await session_v2.retry()
    return {
        "retried": True,
        "last_prompt": last,
        "event_count": len(events),
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


@router.post("/sessions/{session_id}/compact")
async def compact_session(session_id: str) -> dict[str, object]:
    """Compress a session by replacing old events with a summary."""
    if state.event_store is None or state.compactor is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    session_v2 = await SessionV2.load(state.event_store, SessionID(session_id))
    if session_v2.state.seq == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        baseline_seq = await state.compactor.compact(session_id)
        return {"status": "ok", "baseline_seq": baseline_seq}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/questions")
async def list_questions(session_id: str) -> list[dict[str, object]]:
    """P0-2: List pending questions for a session (used by frontend polling)."""
    if state.question_registry is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    return await state.question_registry.list_pending(session_id)


@router.post("/sessions/{session_id}/questions/{request_id}/reply")
async def reply_question(
    session_id: str, request_id: str, body: dict[str, object]
) -> dict[str, str]:
    """P0-2: Reply to a pending question."""
    if state.question_registry is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    answers = body.get("answers", [])
    if isinstance(answers, list):
        str_answers = [str(a) for a in answers]
    else:
        str_answers = [str(answers)]
    ok = await state.question_registry.resolve(request_id, str_answers)
    if not ok:
        raise HTTPException(status_code=404, detail="Question not found or already answered")

    # P2-3: If always_allow is true, auto-save a global allow-all permission rule (SQLite)
    if body.get("always_allow") and state.db is not None:
        logger.info("always_allow triggered for session=%s request=%s", session_id, request_id)
        try:
            from cscode.core.permission_v2 import Rule as PermissionRule
            from cscode.core.permission_v2 import RuleEffect
            from cscode.core.permission_v2 import SavedRules as PermissionSavedRules

            saved = PermissionSavedRules(state.db)
            await saved.save(PermissionRule(action="*", resource="*", effect=RuleEffect.ALLOW))
        except Exception:
            logger.exception("Failed to save always_allow rule")

    return {"status": "ok"}


@router.post("/sessions/{session_id}/questions/{request_id}/reject")
async def reject_question(session_id: str, request_id: str) -> dict[str, str]:
    """P0-2: Reject a pending question."""
    if state.question_registry is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    ok = await state.question_registry.reject(request_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Question not found or already answered")
    return {"status": "ok"}
