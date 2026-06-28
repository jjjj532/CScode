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


def _llm_event_to_dict(event: LLMEvent) -> dict[str, object]:
    """Convert LLMEvent to dict for SSE streaming."""
    match event:
        case TextDelta(text=text):
            return {"type": "text.delta", "content": text}
        case TextEnded(full_text=full_text):
            return {"type": "text.ended", "content": full_text}
        case ToolCallEnded(tool_call_id=id, name=name, args=args):
            return {"type": "tool.called", "tool_call_id": id, "name": name, "args": args}
        case ToolResult(tool_call_id=id, result=result):
            return {"type": "tool.result", "tool_call_id": id, "result": result}
        case Finish(finish_reason=finish_reason):
            return {"type": "complete", "content": finish_reason}
        case ToolFailure(tool_call_id=id, error=error):
            return {"type": "tool.failed", "tool_call_id": id, "error": error}
        case _:
            return {"type": "unknown"}


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

    async def process(self, session_id: str) -> None:
        await self._handler()


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

_db: Database | None = None
_event_store: EventStore | None = None
_coordinator: SessionCoordinator | None = None
_projector: Projector | None = None
_compactor: Compactor | None = None
_tracker: TaskTracker | None = None
_question_registry: QuestionRegistry | None = None
_tool_registry: Any = None
_active_agent_tasks: dict[str, asyncio.Task[Any]] = {}


class ChatResponse(BaseModel):
    response: str
    session_id: str


class ConfigRequest(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o"
    api_base: str | None = None
    api_key: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    system_prompt: str | None = None


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
    try:
        session_v2 = await SessionV2.load(event_store, SessionID(session_id))
    except Exception:
        # Session doesn't exist, create new
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

    # Ensure system prompt is first
    if not messages or messages[0].role != MessageRole.SYSTEM:
        messages.insert(0, NewMessage.system(
            "You are CScode, an AI-powered coding assistant. You help users write, review, and debug code. "
            "You have access to tools for reading, writing, and editing files, "
            "running shell commands, searching codebases, and browsing the web."
        ))

    if file_context:
        # Append file context as system message
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
            await _build_context_messages(session_v2, user_text, file_context)

            # Append prompt.admitted event
            await _event_store.append(str(session_v2.session_id), [
                {"type": "prompt.admitted", "data": {"content": message, "files": attached_filenames}}
            ])

            queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

            def _e(data: dict[str, object]) -> str:
                data["session_id"] = str(session_v2.session_id)
                return f"data: {json.dumps(data)}\n\n"

            _persist_event_types = frozenset({
                "step.started", "text.ended", "step.ended",
                "tool.called", "tool.success", "tool.failed",
            })

            async def on_event(event: LLMEvent) -> None:
                sse_event = _llm_event_to_dict(event)
                sse_event["session_id"] = str(session_v2.session_id)
                await queue.put(sse_event)
                if _event_store is not None:
                    evt_type = sse_event.get("type", "")
                    if isinstance(evt_type, str) and evt_type in _persist_event_types:
                        evt_data = sse_event.get("data", {})
                        await _event_store.append(str(session_v2.session_id), [
                            {"type": evt_type, "data": dict(evt_data) if isinstance(evt_data, dict) else {}}
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
                from cscode.core.config import Config, load_config
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
            async def run_with_coordinator() -> None:
                if _coordinator is not None:
                    await _coordinator.run(str(session_v2.session_id), _CallableProcessor(agent_runner))
                else:
                    await agent_runner()

            # Cancel any existing agent task for this session
            old_task = _active_agent_tasks.get(str(session_v2.session_id))
            if old_task and not old_task.done():
                logger.info("Cancelling previous agent task for session %s", session_v2.session_id)
                old_task.cancel()
                try:
                    await asyncio.wait_for(old_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            agent_task = asyncio.create_task(run_with_coordinator())
            _active_agent_tasks[str(session_v2.session_id)] = agent_task

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

                    try:
                        response = agent_task.result()
                        # Session state is already updated via EventStore by on_event handler
                        for f in OUTPUTS_DIR.iterdir():
                            if f.is_file() and f.stat().st_mtime >= before:
                                yield _e({'type': 'file_created', 'filename': f.name})
                        if not response:
                            logger.warning("[DIAG] Empty response from agent for session=%s", session_v2.session_id)
                            yield _e({'type': 'error', 'content': 'LLM returned empty response - API returned no content'})
                        else:
                            yield _e({'type': 'complete', 'content': response})
                    except Exception as e:
                        logger.warning("[DIAG] agent task error session=%s error=%s", session_v2.session_id, e)
                        yield _e({'type': 'error', 'content': str(e)})
                    finally:
                        # Auto-generate title for new sessions
                        if is_new:
                            generated_title = None
                            try:
                                title_sys = NewMessage.system("Summarize the user")
                                # Create a minimal agent for title generation
                                if _db is not None:
                                    from cscode.core.config import Config, ConfigStore, load_config
                                    store = ConfigStore(_db)
                                    saved_config_raw = await store.get()
                                    if saved_config_raw is not None:
                                        saved_config = Config.from_dict(saved_config_raw)
                                    else:
                                        saved_config = load_config()
                                else:
                                    from cscode.core.config import Config, load_config
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
                            # Update title via session_v2
                            await session_v2.update_metadata(title=generated_title)
                            yield _e({'type': 'session:title', 'title': generated_title})

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
                        yield _e({'type': 'status', 'message': 'Agent is working...'})
                        last_status_time = now
                    continue

        except Exception as e:
                if _e is not None:
                    yield _e({'type': 'error', 'content': str(e)})

        finally:
            if session_v2 is not None and agent_task is not None:
                if _active_agent_tasks.get(str(session_v2.session_id)) is agent_task:
                    del _active_agent_tasks[str(session_v2.session_id)]
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
            {"type": "prompt.admitted", "data": {"content": message, "files": attached_filenames}}
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

        # Auto-generate title for new sessions
        if is_new:
            generated_title = None
            try:
                title_sys = NewMessage.system("Summarize the user's request in 3-6 words.")
                title_usr_msg = NewMessage.user(message or "")  # noqa: F841
                title_usr = NewMessage.user(message or "")  # noqa: F841
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
                "id": str(state.session_id),
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
    return load_config().to_dict()


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
    global _active_agent_tasks
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

app.include_router(api_router)

# Static files for web UI
web_dist = Path(__file__).parent.parent / "web" / "dist"
if web_dist.exists():
    app.mount("/", StaticFiles(directory=web_dist, html=True), name="static")
