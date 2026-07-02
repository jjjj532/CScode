"""CScode Server — FastAPI application with Event Sourcing session architecture.

Phase 2 architecture:
- SessionV2 + EventStore: append-only event log, no delete+reinsert
- SessionCoordinator: per-session serialization
- AgentV2 per request via factory
- SessionProjector: rebuilds state from events
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, AsyncIterator

from fastapi import APIRouter, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cscode.app.factory import create_agent_v2, create_tool_registry
from cscode.core.coordinator import SessionCoordinator
from cscode.core.session import SessionProjector, SessionV2
from cscode.core.tracker import TaskTracker
from cscode.llm.types import LLMRequest
from cscode.schema.events import (
    Finish,
    LLMEvent,
    TextDelta,
    TextEnded,
    ToolCallEnded,
    ToolFailure,
    ToolResult,
)
from cscode.schema.ids import SessionID
from cscode.schema.messages import (
    Message as NewMessage,
)
from cscode.schema.messages import (
    MessageRole,
)
from cscode.server.compactor import Compactor
from cscode.server.projector import Projector
from cscode.server.question_registry import QuestionRegistry
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api")

OUTPUTS_DIR = Path("/tmp/cscode-outputs")

# Event types that are persisted to EventStore for message history.
PERSIST_EVENT_TYPES = frozenset({
    "step.started", "text.ended", "step.ended",
    "tool.called", "tool.success", "tool.failed",
    "error",
})


def _llm_event_to_dict(event: LLMEvent) -> dict[str, object]:
    """Convert LLMEvent to dict for SSE streaming.

    Returns dict with 'type' and 'data' keys where data holds the payload.
    This ensures frontend applyEvent receives event.data.xxx consistently.
    """
    match event:
        case TextDelta(text=text):
            return {"type": "text.delta", "data": {"content": text}}
        case TextEnded(full_text=full_text):
            return {"type": "text.ended", "data": {"content": full_text}}
        case ToolCallEnded(tool_call_id=id, name=name, args=args):
            return {"type": "tool.called", "data": {"tool_call_id": id, "name": name, "args": args}}
        case ToolResult(tool_call_id=id, result=result):
            return {"type": "tool.success", "data": {"tool_call_id": id, "result": result}}
        case Finish(finish_reason=finish_reason):
            return {"type": "complete", "data": {"finish_reason": finish_reason}}
        case ToolFailure(tool_call_id=id, error=error):
            return {"type": "tool.failed", "data": {"tool_call_id": id, "error": error}}
        case _:
            return {"type": "unknown", "data": {}}


async def _auto_compact(session_id: str, event_store: EventStore) -> None:
    """Fire-and-forget auto-compaction."""
    try:
        await asyncio.sleep(0)  # yield to event loop
    except Exception:
        pass


def _build_system_prompt(file_context: str = "") -> NewMessage:
    base = (
        "You are CScode, an AI-powered coding assistant. You help users write, review, and debug code. "
        "You have access to tools for reading, writing, and editing files, "
        "running shell commands, searching codebases, and browsing the web."
    )
    if file_context:
        base += f"\n\n{file_context}"
    return NewMessage.system(base)


class _CallableProcessor:
    """Adapts a callable agent runner to core/coordinator's processor interface."""
    def __init__(self, handler: Any) -> None:
        self._handler = handler

    async def process(self, session_id: str) -> str:
        return await self._handler()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _db, _event_store, _coordinator, _projector, _compactor, _tracker, _question_registry, _tool_registry

    # Diagnostics log — stderr + file
    from cscode.utils.logging import setup_logging
    setup_logging("DEBUG")

    fh = logging.FileHandler("/tmp/cscode-diag.log", mode="w")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(fh)
    logging.getLogger().setLevel(logging.DEBUG)
    logger.info("=== CScode server started (Event Sourcing architecture) ===")

    resource_dir = os.environ.get("CSCODE_RESOURCE_DIR", "")
    if resource_dir:
        python_dir = os.path.join(resource_dir, "python")
        if os.path.isdir(python_dir):
            existing = os.environ.get("PYTHONPATH", "")
            os.environ["PYTHONPATH"] = f"{python_dir}{os.pathsep}{existing}" if existing else python_dir
            logger.debug("Set PYTHONPATH for subprocesses: %s", python_dir)

    db_path = os.environ.get("CSCODE_DB_PATH")
    _db = Database(db_path=db_path)
    await _db.init()

    # New architecture: EventStore + SessionCoordinator
    _event_store = EventStore(_db)
    _coordinator = SessionCoordinator()
    _projector = Projector(_db)
    _compactor = Compactor(_db, _event_store, _projector)
    _tracker = TaskTracker(_db)
    _question_registry = QuestionRegistry()

    # Shared tool registry (AgentV2 instances will reuse this)
    _tool_registry = create_tool_registry()

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    template_path = OUTPUTS_DIR / "xlsx_template.py"
    if not template_path.exists():
        template_path.write_text(_XLSX_TEMPLATE)
        template_path.chmod(0o755)

    logger.info("Lifespan startup complete")

    yield

    if _db is not None:
        await _db.close()
    logger.info("Lifespan shutdown complete")


app = FastAPI(title="CScode API", version="0.3.4", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next: Any) -> Response:
    """Log method, path, status, duration for every request."""
    start = time.monotonic()
    response: Response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s %s %.0fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


_db: Database | None = None
_event_store: EventStore | None = None
_coordinator: SessionCoordinator | None = None
_projector: Projector | None = None
_compactor: Compactor | None = None
_tracker: TaskTracker | None = None
_question_registry: QuestionRegistry | None = None
_tool_registry: Any = None
_active_agent_tasks: dict[str, asyncio.Task[Any]] = {}
_session_queues: dict[str, asyncio.Queue[dict[str, object]]] = {}
_permission_store: dict[str, dict[str, object]] = {}


class ChatResponse(BaseModel):
    response: str
    session_id: str


class McpServerConfig(BaseModel):
    name: str
    command: str
    args: list[str] = []
    env: dict[str, str] = {}
    enabled: bool = True


class PluginConfig(BaseModel):
    enabled: list[str] = []
    settings: dict[str, dict[str, object]] = {}


class PermissionRule(BaseModel):
    pattern: str
    allow: bool = True


class PermissionRuleCreate(BaseModel):
    pattern: str
    allow: bool = True
    label: str = ""


class ConfigRequest(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o"
    api_base: str | None = None
    api_key: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    system_prompt: str | None = None
    theme: str | None = None
    mcp_servers: list[McpServerConfig] = []
    plugins: PluginConfig = PluginConfig()
    permission_rules: list[PermissionRule] = []
    keybindings: dict[str, str] = {}


class SessionCreateRequest(BaseModel):
    title: str = "New Session"


@api_router.get("/health")
async def health() -> dict[str, str]:
    from cscode import __version__
    return {"status": "ok", "version": __version__}


async def _get_or_create_session(
    session_id: str | None,
    event_store: EventStore,
    config_data: dict[str, Any] | None = None,
) -> tuple[SessionV2, bool]:
    """Get existing session or create new one. Returns (session_v2, is_new)."""
    if session_id is None:
        session_id = str(uuid.uuid4())

    is_new = False
    sid = SessionID(session_id)
    events = await event_store.read(sid)
    if events:
        state = SessionProjector.project(events)
        session_v2 = SessionV2(event_store, sid, state)
    else:
        provider = "openai"
        model = "gpt-4o"
        if config_data:
            provider = config_data.get("provider", "openai")
            model = config_data.get("model", "gpt-4o")
        session_v2 = await SessionV2.create(event_store, model=model, provider=provider, title="New Chat", agent="auto")
        is_new = True

    return session_v2, is_new


async def _build_context_messages(
    session_v2: SessionV2,
    user_message: str,
    file_context: str = "",
) -> list[NewMessage]:
    """Build message list for LLM from session state + new user input."""
    # Get messages from session state (reconstructed from events)
    messages = list(SessionProjector.build_context(session_v2.state))

    if not messages or messages[0].role != MessageRole.SYSTEM:
        # Merge file_context into system prompt (some providers ignore 2+ system messages)
        messages.insert(0, _build_system_prompt(file_context))
    elif file_context:
        messages.append(NewMessage.system(file_context))

    # Add user message
    messages.append(NewMessage.user(user_message.strip() if user_message else "请分析附件内容"))

    return messages


@api_router.post("/chat")
async def chat(request: Request) -> ChatResponse:
    message = ""
    session_id: str | None = None
    files: list[tuple[str, bytes]] = []

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        _message = form.get("message", "")
        if isinstance(_message, str):
            message = _message
        _session_raw = form.get("session_id", None)
        if isinstance(_session_raw, str):
            session_id = _session_raw
        for f in form.getlist("files"):
            if isinstance(f, UploadFile):
                content = await f.read()
                files.append((f.filename or "unknown", content))
    else:
        body = await request.json()
        message = body.get("message", "")
        session_id = body.get("session_id", None)
        files_data = body.get("files", [])
        for f in files_data:
            if isinstance(f, dict):
                import base64
                try:
                    file_bytes = base64.b64decode(f.get("content", ""))
                except Exception:
                    file_bytes = f.get("content", "").encode("utf-8")
                files.append((f.get("name", "file"), file_bytes))

    return await _handle_chat(message, session_id, files)


@api_router.post("/chat/stream")
async def chat_stream(request: Request) -> StreamingResponse:
    message = ""
    session_id: str | None = None
    files: list[tuple[str, bytes]] = []

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        _message = form.get("message", "")
        if isinstance(_message, str):
            message = _message
        _session_raw = form.get("session_id", None)
        if isinstance(_session_raw, str):
            session_id = _session_raw
        for f in form.getlist("files"):
            if isinstance(f, UploadFile):
                content = await f.read()
                files.append((f.filename or "unknown", content))
    else:
        body = await request.json()
        message = body.get("message", "")
        session_id = body.get("session_id", None)
        files_data = body.get("files", [])
        for f in files_data:
            if isinstance(f, dict):
                import base64
                try:
                    file_bytes = base64.b64decode(f.get("content", ""))
                except Exception:
                    file_bytes = f.get("content", "").encode("utf-8")
                files.append((f.get("name", "file"), file_bytes))

    async def event_stream() -> AsyncGenerator[str, None]:
        global _event_store, _coordinator, _tool_registry, _db
        nonlocal session_id
        if _event_store is None or _coordinator is None:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Server not initialized'})}\n\n"
            return

        session_v2: Any = None
        agent_task: Any = None

        try:
            if session_id is None:
                session_id = str(uuid.uuid4())
            # Load or create session
            config_data = None
            if _db is not None:
                from cscode.core.config import ConfigStore
                store = ConfigStore(_db)
                saved_config_dict = await store.get()
                if saved_config_dict:
                    config_data = saved_config_dict

            session_v2, is_new = await _get_or_create_session(session_id, _event_store, config_data)

            if is_new:
                yield f"data: {json.dumps({'type': 'session', 'session_id': session_v2.session_id})}\n\n"

            # Build file context
            FILE_CONTEXT_MAX = 30000
            file_context = ""
            attached_filenames: list[str] = []
            if files:
                from cscode.utils.file_parser import parse_file
                parts = []
                total_len = 0
                for name, content in files:
                    text = parse_file(name, content)
                    remaining = FILE_CONTEXT_MAX - total_len
                    if remaining <= 0:
                        parts.append(f"[FILE: {name}]\n[skipped: context limit reached]")
                        continue
                    if len(text) > remaining:
                        text = text[:remaining] + f"\n[truncated: file too long, showing {remaining} of {len(text)} characters]"
                    total_len += len(text)
                    parts.append(f"[FILE: {name}]\n{text}")
                    attached_filenames.append(name)
                header = (
                    "The user attached the following file(s). "
                    "The full content is provided below in [FILE: ...] blocks. "
                    "Glob, Grep, and Ls are blocked for attached files. "
                    "Use Read tool if you need to read any file's content.\n\n"
                )
                file_context = "\n\n" + header + "\n\n".join(parts)

            # Build messages for LLM
            user_text = message.strip() if message else "请分析附件内容"

            # Append prompt.admitted event
            await _event_store.append(str(session_v2.session_id), [
{"type": "prompt.admitted", "data": {"prompt": message, "files": attached_filenames}}
            ])

            queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

            def _e(data: dict[str, object]) -> str:
                data["session_id"] = str(session_v2.session_id)
                return f"data: {json.dumps(data)}\n\n"

            async def on_event(event: LLMEvent) -> None:
                sse_event = _llm_event_to_dict(event)
                sse_event["session_id"] = str(session_v2.session_id)
                await queue.put(sse_event)
                if _event_store is not None:
                    evt_type = sse_event.get("type", "")
                    if isinstance(evt_type, str) and evt_type in PERSIST_EVENT_TYPES:
                        evt_data = sse_event.get("data", {})
                        await _event_store.append(str(session_v2.session_id), [
                            {"type": evt_type, "data": dict(evt_data) if isinstance(evt_data, dict) else {}}
                        ])

            async def _emit_step_started() -> None:
                step_event: dict[str, object] = {"type": "step.started", "data": {}, "session_id": str(session_v2.session_id)}
                await queue.put(step_event)
                if _event_store is not None:
                    await _event_store.append(str(session_v2.session_id), [
                        {"type": "step.started", "data": {}}
                    ])

            async def _emit_step_ended() -> None:
                step_event: dict[str, object] = {"type": "step.ended", "data": {}, "session_id": str(session_v2.session_id)}
                await queue.put(step_event)
                if _event_store is not None:
                    await _event_store.append(str(session_v2.session_id), [
                        {"type": "step.ended", "data": {}}
                    ])

            before = time.time()

            # Create agent for this request
            if _db is not None:
                from cscode.core.config import Config, ConfigStore, load_config
                store = ConfigStore(_db)
                saved_config_raw = await store.get()
                if saved_config_raw is not None:
                    saved_config = Config.from_dict(saved_config_raw)
                else:
                    saved_config = load_config()
            else:
                from cscode.core.config import load_config
                saved_config = load_config()

            agent = create_agent_v2(saved_config, tool_registry=_tool_registry)
            agent._max_tool_rounds = 20

            async def agent_runner() -> str:
                logger.info("[DIAG] agent_runner: starting run_with_messages session=%s", session_v2.session_id)
                t0 = time.time()
                try:
                    # Build context messages
                    new_messages = await _build_context_messages(
                        session_v2,
                        user_text,
                        file_context
                    )

                    result = await agent.run_with_messages(
                        new_messages,
                        on_event=on_event,
                    )
                    return result
                finally:
                    logger.info("[DIAG] agent_runner: completed session=%s in %.1fs", session_v2.session_id, time.time() - t0)

            # Use Coordinator for per-session serialization
            async def run_with_coordinator() -> str:
                if _coordinator is not None:
                    return await _coordinator.run(str(session_v2.session_id), _CallableProcessor(agent_runner))
                else:
                    return await agent_runner()

            # Cancel any existing agent task for this session
            old_task = _active_agent_tasks.get(str(session_v2.session_id))
            if old_task and not old_task.done():
                logger.info("Cancelling previous agent task for session %s", session_v2.session_id)
                old_task.cancel()
                try:
                    await asyncio.wait_for(old_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            _agent_event_queue: asyncio.Queue[dict[str, object]] = queue
            async def stepped_agent_runner() -> str:
                await _emit_step_started()
                try:
                    return await run_with_coordinator()
                finally:
                    await _emit_step_ended()

            agent_task = asyncio.create_task(stepped_agent_runner())
            _active_agent_tasks[str(session_v2.session_id)] = agent_task
            _session_queues[str(session_v2.session_id)] = queue

            last_event_time = time.time()
            last_status_time = time.time()
            response = ""

            while True:
                if await request.is_disconnected():
                    logger.info("Client disconnected for session %s, cancelling task", session_v2.session_id)
                    if _question_registry is not None:
                        await _question_registry.cancel_session(str(session_v2.session_id))
                    agent_task.cancel()
                    break

                if agent_task.done():
                    # Drain remaining queue events
                    while not queue.empty():
                        try:
                            event = queue.get_nowait()
                            yield f"data: {json.dumps(event)}\n\n"
                        except asyncio.QueueEmpty:
                            break

                    # Auto-generate title if still using default (handles both
                    # direct SSE new sessions AND frontend pre-created sessions)
                    _current_title = session_v2.state.title
                    if not _current_title or _current_title in ("New Session", "New Chat"):
                        generated_title = None
                        try:
                            title_sys = NewMessage.system("You give very short session titles. Reply with ONLY 3-6 words.")
                            if _db is not None:
                                from cscode.core.config import Config, ConfigStore, load_config
                                store = ConfigStore(_db)
                                saved_config_raw = await store.get()
                                if saved_config_raw is not None:
                                    saved_config = Config.from_dict(saved_config_raw)
                                else:
                                    saved_config = load_config()
                            else:
                                from cscode.core.config import load_config
                                saved_config = load_config()
                            title_agent = create_agent_v2(saved_config, tool_registry=_tool_registry)
                            title_r = await title_agent.llm_client.generate(
                                LLMRequest(
                                    model=title_agent.llm_client.route.model,
                                    messages=(title_sys, NewMessage.user(message or "")),
                                )
                            )
                            title_text = title_r.content.strip().strip('"\'.,!?')
                            if title_text:
                                generated_title = title_text
                        except Exception:
                            pass
                        if not generated_title:
                            generated_title = (message[:47] + "...") if len(message) > 50 else (message or "New Chat")
                        await session_v2.update_metadata(title=generated_title)
                        yield _e({'type': 'session:title', 'data': {'title': generated_title}})

                    try:
                        response = agent_task.result()
                        for f in OUTPUTS_DIR.iterdir():
                            if f.is_file() and f.stat().st_mtime >= before:
                                yield _e({'type': 'file_created', 'data': {'filename': f.name}})
                        if not response:
                            logger.warning("[DIAG] Empty response from agent for session=%s", session_v2.session_id)
                            yield _e({'type': 'error', 'data': {'content': 'LLM returned empty response - API returned no content'}})
                        else:
                            yield _e({'type': 'complete', 'data': {'content': response}})
                    except Exception as e:
                        logger.warning("[DIAG] agent task error session=%s error=%s", session_v2.session_id, e)
                        yield _e({'type': 'error', 'data': {'content': str(e)}})

                    asyncio.create_task(_auto_compact(str(session_v2.session_id), _event_store))
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                    last_event_time = time.time()
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    now = time.time()
                    if now - last_event_time > 10:
                        logger.info("[DIAG] keepalive session=%s last_event=%.1fs ago", session_v2.session_id, now - last_event_time)
                        yield ": keepalive\n\n"
                        last_event_time = now
                    if now - last_status_time > 60:
                        yield _e({'type': 'status', 'data': {'message': 'Agent is working...'}})
                        last_status_time = now
                    continue

        except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'data': {'content': str(e)}, 'session_id': str(session_v2.session_id) if session_v2 else 'unknown'})}\n\n"

        finally:
            if session_v2 is not None and agent_task is not None:
                if _active_agent_tasks.get(str(session_v2.session_id)) is agent_task:
                    del _active_agent_tasks[str(session_v2.session_id)]
                _session_queues.pop(str(session_v2.session_id), None)
                if not agent_task.done():
                    logger.info("[DIAG] Generator exiting, cancelling agent task for session %s", session_v2.session_id)
                    agent_task.cancel()
                    try:
                        await asyncio.wait_for(agent_task, timeout=5.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@api_router.get("/events")
async def event_stream(session_id: str, after_seq: int = 0) -> StreamingResponse:
    global _event_store
    if _event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    async def stream() -> AsyncIterator[str]:
        assert _event_store is not None
        import asyncio
        import json
        try:
            async for event in _event_store.subscribe(session_id, after_seq):
                yield f"event: {event.type}\ndata: {json.dumps(event.data)}\n\n"
        except asyncio.CancelledError:
            pass
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@api_router.get("/sessions/{session_id}/events")
async def session_event_stream(session_id: str, after_seq: int = 0) -> StreamingResponse:
    """P1-3: Per-session SSE event subscription.

    Delegates to the existing /events endpoint logic for compatibility.
    """
    return await event_stream(session_id, after_seq)


async def _handle_chat(
    message: str, session_id: str | None, files: list[tuple[str, bytes]] | None = None
) -> ChatResponse:
    global _event_store, _tool_registry, _db
    if _event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    session_id = session_id or str(uuid.uuid4())

    try:
        # Load or create session
        config_data = None
        if _db is not None:
            from cscode.core.config import ConfigStore
            store = ConfigStore(_db)
            saved_config_dict = await store.get()
            if saved_config_dict:
                config_data = saved_config_dict

        session_v2, is_new = await _get_or_create_session(session_id, _event_store, config_data)

        # Build file context
        FILE_CONTEXT_MAX = 30000
        file_context = ""
        attached_filenames: list[str] = []
        if files:
            from cscode.utils.file_parser import parse_file
            parts = []
            total_len = 0
            for name, content in files:
                text = parse_file(name, content)
                remaining = FILE_CONTEXT_MAX - total_len
                if remaining <= 0:
                    parts.append(f"[FILE: {name}]\n[skipped: context limit reached]")
                    continue
                if len(text) > remaining:
                    text = text[:remaining] + f"\n[truncated: file too long, showing {remaining} of {len(text)} characters]"
                total_len += len(text)
                parts.append(f"[FILE: {name}]\n{text}")
                attached_filenames.append(name)
            header = (
                "The user attached the following file(s). "
                "The full content is provided below in [FILE: ...] blocks. "
                "Glob, Grep, and Ls are blocked for attached files. "
                "Use Read tool if you need to read any file's content.\n\n"
            )
            file_context = "\n\n" + header + "\n\n".join(parts)

        # Build messages for LLM
        user_text = message.strip() if message else "请分析附件内容"
        messages = await _build_context_messages(session_v2, user_text, file_context)

        # Append prompt.admitted event
        await _event_store.append(str(session_v2.session_id), [
            {"type": "prompt.admitted", "data": {"prompt": message, "files": attached_filenames}}
        ])

        # Create agent for this request
        if _db is not None:
            from cscode.core.config import Config, ConfigStore, load_config
            store = ConfigStore(_db)
            saved_config_raw = await store.get()
            if saved_config_raw is not None:
                saved_config = Config.from_dict(saved_config_raw)
            else:
                saved_config = load_config()
        else:
            from cscode.core.config import load_config
            saved_config = load_config()

        agent = create_agent_v2(saved_config, tool_registry=_tool_registry)

        # Run agent with full message history
        try:
            response = await agent.run_with_messages(messages, on_event=None)
        except Exception as e:
            logger.error("agent_runner error: %s", e)
            raise

        # Auto-generate title if still using default
        _current_title = session_v2.state.title
        if not _current_title or _current_title in ("New Session", "New Chat"):
            generated_title = None
            try:
                title_sys = NewMessage.system("You give very short session titles. Reply with ONLY 3-6 words.")
                title_agent = create_agent_v2(saved_config, tool_registry=_tool_registry)
                title_r = await title_agent.llm_client.generate(
                    LLMRequest(
                        model=title_agent.llm_client.route.model,
                        messages=(title_sys, NewMessage.user(message or "")),
                    )
                )
                title_text = title_r.content.strip().strip('"\'.,!?')
                if title_text:
                    generated_title = title_text
            except Exception:
                pass
            if not generated_title:
                generated_title = (message[:47] + "...") if len(message) > 50 else (message or "New Chat")
            await session_v2.update_metadata(title=generated_title)

        # Auto-compact if threshold exceeded (fire-and-forget)
        asyncio.create_task(_auto_compact(str(session_v2.session_id), _event_store))

        logger.debug("_handle_chat completed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return ChatResponse(response=response, session_id=session_id)


@api_router.get("/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    global _event_store, _projector
    if _event_store is None or _projector is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    # Get all session IDs from event_sequences
    if _db is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    cursor = await _db.conn.execute("SELECT aggregate_id FROM event_sequences")
    rows = await cursor.fetchall()

    sessions = []
    for row in rows:
        aggregate_id = row["aggregate_id"]
        try:
            session_v2 = await SessionV2.load(_event_store, aggregate_id)
            state = session_v2.state
            sessions.append({
                "id": str(state.session_id) if state.session_id else aggregate_id,
                "title": state.title,
                "provider": state.provider,
                "model": state.model,
                "created_at": state.created_at,
                "updated_at": state.updated_at,
            })
        except Exception:
            continue

    return sessions


@api_router.get("/config")
async def get_config() -> dict[str, Any]:
    global _db
    if _db is not None:
        from cscode.core.config import ConfigStore
        store = ConfigStore(_db)
        saved_config = await store.get()
        if saved_config:
            return saved_config

    from cscode.core.config import load_config
    cfg = load_config()
    # Some PyInstaller builds may return dict instead of Config
    if isinstance(cfg, dict):
        return cfg
    return cfg.to_dict()


@api_router.post("/config")
async def save_config(config: ConfigRequest) -> dict[str, str]:
    global _db
    if _db is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    from cscode.core.config import ConfigStore
    store = ConfigStore(_db)
    await store.save(config.model_dump())

    return {"status": "ok"}


@api_router.post("/sessions")
async def create_session(request: SessionCreateRequest) -> dict[str, Any]:
    global _event_store
    if _event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    from cscode.core.config import load_config
    config = load_config()

    session_v2 = await SessionV2.create(_event_store, model=config.model, provider=config.provider, title=request.title)

    return {"id": str(session_v2.session_id), "title": session_v2.state.title}


@api_router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    global _event_store
    if _event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    session_v2 = await SessionV2.load(_event_store, SessionID(session_id))
    await session_v2.delete()

    return {"status": "ok"}


@api_router.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str) -> dict[str, str]:
    global _active_agent_tasks, _question_registry, _session_queues

    # 1. Cancel pending questions for this session
    if _question_registry is not None:
        await _question_registry.cancel_session(session_id)

    # 2. Send stop signal to SSE event stream
    queue = _session_queues.get(session_id)
    if queue is not None:
        await queue.put({"type": "step.ended", "data": {}, "session_id": session_id})

    # 3. Cancel the agent task
    task = _active_agent_tasks.get(session_id)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    return {"status": "ok"}


@api_router.patch("/sessions/{session_id}")
async def update_session(session_id: str, title: str = "") -> dict[str, str]:
    global _event_store
    if _event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    session_v2 = await SessionV2.load(_event_store, SessionID(session_id))
    await session_v2.update_metadata(title=title if title else None)

    return {"status": "ok"}


@api_router.post("/sessions/{session_id}/export")
async def export_session(session_id: str) -> Response:
    global _event_store, _projector
    if _event_store is None or _projector is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    # Load session for validation (events are used for state projection)
    await SessionV2.load(_event_store, SessionID(session_id))  # noqa: F841
    events = await _event_store.read(session_id)
    state = SessionProjector.project(events)

    import json
    data = {
        "session_id": str(state.session_id),
        "title": state.title,
        "provider": state.provider,
        "model": state.model,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
            }
            for msg in state.messages
        ],
    }
    return Response(
        content=json.dumps(data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={state.title.replace(' ', '_')}.json"},
    )


@api_router.post("/sessions/import")
async def import_session(request: Request) -> dict[str, str]:
    global _event_store
    if _event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    body = await request.json()

    # Create new session with imported data
    session_v2 = await SessionV2.create(_event_store, model=body.get("model", "gpt-4o"), provider=body.get("provider", "openai"), title=body.get("title", "Imported Session"))

    # Replay messages as events
    for msg in body.get("messages", []):
        if msg.get("role") == "user":
            await _event_store.append(str(session_v2.session_id), [
                {"type": "prompt.admitted", "data": {"prompt": msg.get("content", "")}}
            ])
        elif msg.get("role") == "assistant":
            await _event_store.append(str(session_v2.session_id), [
                {"type": "text.ended", "data": {"content": msg.get("content", "")}}
            ])

    return {"id": str(session_v2.session_id), "title": session_v2.state.title}


@api_router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str) -> list[dict[str, object]]:
    """P0-1: Return messages for a session (used by sidebar session switching)."""
    global _event_store
    if _event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    session_v2 = await SessionV2.load(_event_store, SessionID(session_id))
    messages = SessionProjector.build_context(session_v2.state)
    return [
        {"role": msg.role, "content": msg.content, "id": str(msg.id) if msg.id else None}
        for msg in messages
    ]


@api_router.get("/sessions/{session_id}/context")
async def get_session_context(session_id: str) -> list[dict[str, object]]:
    """P1-2: Return LLM context messages for a session (with system prompts)."""
    global _event_store
    if _event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    session_v2 = await SessionV2.load(_event_store, SessionID(session_id))
    messages = SessionProjector.build_context(session_v2.state)
    return [
        {"role": msg.role, "content": msg.content}
        for msg in messages
    ]


@api_router.post("/sessions/{session_id}/model")
async def switch_model(session_id: str, body: dict[str, object]) -> dict[str, str]:
    """P1-5: Switch the model/provider for a session."""
    global _event_store
    if _event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    session_v2 = await SessionV2.load(_event_store, SessionID(session_id))
    model = body.get("model", session_v2.state.model)
    provider = body.get("provider", session_v2.state.provider)
    await session_v2.update_metadata(model=str(model))
    logger.info("Session %s model switched to %s (provider=%s)", session_id, model, provider)
    return {"status": "ok"}


@api_router.post("/sessions/{session_id}/agent")
async def switch_agent(session_id: str, body: dict[str, object]) -> dict[str, str]:
    """P1-5: Switch the agent for a session."""
    global _event_store
    if _event_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    session_v2 = await SessionV2.load(_event_store, SessionID(session_id))
    agent = body.get("agent", "auto")
    await session_v2.update_metadata(agent=str(agent))
    logger.info("Session %s agent switched to %s", session_id, agent)
    return {"status": "ok"}


@api_router.get("/sessions/{session_id}/questions")
async def list_questions(session_id: str) -> list[dict[str, object]]:
    """P0-2: List pending questions for a session (used by frontend polling)."""
    global _question_registry
    if _question_registry is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    return await _question_registry.list_pending(session_id)


@api_router.post("/sessions/{session_id}/questions/{request_id}/reply")
async def reply_question(session_id: str, request_id: str, body: dict[str, object]) -> dict[str, str]:
    """P0-2: Reply to a pending question."""
    global _question_registry
    if _question_registry is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    answers = body.get("answers", [])
    if isinstance(answers, list):
        str_answers = [str(a) for a in answers]
    else:
        str_answers = [str(answers)]
    ok = await _question_registry.resolve(request_id, str_answers)
    if not ok:
        raise HTTPException(status_code=404, detail="Question not found or already answered")

    # P2-3: If always_allow is true, auto-save a permission rule
    if body.get("always_allow"):
        logger.info("always_allow triggered for session=%s request=%s", session_id, request_id)
        rule_id = str(uuid.uuid4())
        _permission_store[rule_id] = {
            "id": rule_id,
            "pattern": f"tool:{session_id}:*",
            "allow": True,
            "label": f"Auto-saved from question {request_id}",
        }

    return {"status": "ok"}


@api_router.post("/sessions/{session_id}/questions/{request_id}/reject")
async def reject_question(session_id: str, request_id: str) -> dict[str, str]:
    """P0-2: Reject a pending question."""
    global _question_registry
    if _question_registry is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    ok = await _question_registry.reject(request_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Question not found or already answered")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# P2-3: Permission rules API
# ---------------------------------------------------------------------------


@api_router.get("/permission-rules")
async def list_permission_rules() -> list[dict[str, object]]:
    """List all saved permission rules."""
    return list(_permission_store.values())


@api_router.post("/permission-rules")
async def create_permission_rule(rule: PermissionRuleCreate) -> dict[str, object]:
    """Create a new permission rule."""
    rule_id = str(uuid.uuid4())
    entry: dict[str, object] = {
        "id": rule_id,
        "pattern": rule.pattern,
        "allow": rule.allow,
        "label": rule.label,
    }
    _permission_store[rule_id] = entry
    return entry


@api_router.delete("/permission-rules/{rule_id}")
async def delete_permission_rule(rule_id: str) -> dict[str, str]:
    """Delete a permission rule."""
    if rule_id not in _permission_store:
        raise HTTPException(status_code=404, detail="Rule not found")
    del _permission_store[rule_id]
    return {"status": "ok"}


@api_router.get("/files/search")
async def search_files(q: str = "") -> list[str]:
    try:
        from cscode.tools.glob import GlobTool
        tool = GlobTool()
        result = await tool.execute({"pattern": q if q else "**/*"})
        if result.success and result.data:
            if "No files matching" in result.data:
                return []
            files = result.data.split("\n")
            return [f for f in files if f]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# P2-4: Session compact API
# ---------------------------------------------------------------------------


@api_router.post("/sessions/{session_id}/compact")
async def compact_session(session_id: str) -> dict[str, object]:
    """Compress a session by replacing old events with a summary."""
    global _compactor
    if _compactor is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    try:
        baseline_seq = await _compactor.compact(session_id)
        return {"status": "ok", "baseline_seq": baseline_seq}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# P2-5: File system API extensions
# ---------------------------------------------------------------------------


class FileReadRequest(BaseModel):
    path: str


@api_router.post("/files/read")
async def read_file(req: FileReadRequest) -> dict[str, object]:
    """Read a file's contents from the workspace."""
    import os
    try:
        path = os.path.abspath(os.path.expanduser(req.path))
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="File not found")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"path": path, "content": content, "size": len(content)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/files/list")
async def list_directory(path: str = ".") -> dict[str, object]:
    """List contents of a directory."""
    import os
    import stat as stat_module
    try:
        dir_path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(dir_path):
            raise HTTPException(status_code=404, detail="Directory not found")
        entries: list[dict[str, object]] = []
        for name in sorted(os.listdir(dir_path)):
            full = os.path.join(dir_path, name)
            try:
                st = os.stat(full)
                mode = st.st_mode
                entries.append({
                    "name": name,
                    "type": "dir" if stat_module.S_ISDIR(mode) else "file" if stat_module.S_ISREG(mode) else "other",
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                })
            except OSError:
                entries.append({"name": name, "type": "unknown", "size": 0, "mtime": 0})
        return {"path": dir_path, "entries": entries, "count": len(entries)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_XLSX_TEMPLATE = """import openpyxl
from openpyxl.utils import get_column_letter

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Sheet1"

# Example headers
headers = ["Column A", "Column B", "Column C"]
for col, header in enumerate(headers, 1):
    ws.cell(row=1, column=col, value=header)

# Example data
for row in range(2, 11):
    for col in range(1, 4):
        ws.cell(row=row, column=col, value=f"Row{row}Col{col}")

# Auto-fit columns
for col in range(1, 4):
    ws.column_dimensions[get_column_letter(col)].width = 15

output_path = "/tmp/cscode-outputs/output.xlsx"
wb.save(output_path)
print(f"Saved to {output_path}")
"""

# ---------------------------------------------------------------------------
# P2-1: Register /api/session/... (singular) aliases for all /api/sessions/...
# ---------------------------------------------------------------------------

def _register_session_aliases() -> None:
    """Add singular-path aliases for every /sessions/ route.

    Note: route.path includes the router prefix (/api/...), so we construct
    alias_path relative to the router prefix (strip /api/ before re-adding
    via api_router.add_api_route).
    """
    for route in list(api_router.routes):
        path: str | None = getattr(route, "path", None)
        methods: set[str] | None = getattr(route, "methods", None)
        endpoint = getattr(route, "endpoint", None)
        if not path or not methods or not endpoint:
            continue
        if "/sessions" not in path:
            continue
        # path = /api/sessions/... or /api/sessions → alias = /session/... or /session
        if path.endswith("/api/sessions"):
            alias_path = path.replace("/api/sessions", "/session", 1)
        else:
            alias_path = path.replace("/api/sessions/", "/session/", 1)
        if alias_path == path:
            continue
        for method in methods:
            api_router.add_api_route(
                alias_path,
                endpoint,
                methods=[method],
                include_in_schema=False,
            )


_register_session_aliases()
app.include_router(api_router)

# Static files for web UI — support both development and PyInstaller bundle paths

_web_dist_candidates = [
    Path(__file__).parent.parent / "web" / "dist",          # dev: src/cscode/web/dist/
    Path(__file__).parent.parent.parent / "web" / "dist",   # dev alt: src/web/dist/
]
# PyInstaller: sys._MEIPASS points to the temp extraction root
_mei_path: str | None = getattr(sys, "_MEIPASS", None)
if _mei_path is not None:
    _mei = Path(_mei_path)
    _web_dist_candidates.insert(0, _mei / "web" / "dist")
    _web_dist_candidates.append(_mei.parent / "web" / "dist")

web_dist: Path | None = None
for p in _web_dist_candidates:
    resolved = p.resolve()
    if resolved.is_dir() and (resolved / "index.html").exists():
        web_dist = resolved
        logger.info("Serving static files from: %s", resolved)
        break

if web_dist is not None:
    app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="static")
else:
    logger.warning("No static frontend dist found; tried: %s", [str(p) for p in _web_dist_candidates])
