from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cscode.app.agent import AgentV2
from cscode.app.factory import create_agent_v2, create_tool_registry
from cscode.core.config import ConfigStore, load_config
from cscode.core.coordinator import SessionCoordinator
from cscode.core.messages import Message as OldMessage
from cscode.core.messages import MessageRole as OldMessageRole
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
from cscode.schema.messages import (
    Message as NewMessage,
)
from cscode.server.compactor import Compactor
from cscode.server.projector import Projector
from cscode.server.question_registry import QuestionRegistry
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore
from cscode.storage.session import SessionStore


class _CallableProcessor:
    """Adapts a Callable agent runner to core/coordinator's processor interface."""
    def __init__(self, handler: Callable[[], Any]) -> None:
        self._handler = handler

    async def process(self, session_id: str) -> None:
        await self._handler()


logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api")

# ─── Message type adapters (old ↔ new) ─────────────────────────────────


def _old_to_new_messages(old_msgs: list[OldMessage]) -> list[NewMessage]:
    """Convert old cscode.core.messages.Message list to new schema.messages.Message list."""
    result: list[NewMessage] = []
    for msg in old_msgs:
        role_str = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
        content = msg.content or ""
        if role_str == "system":
            result.append(NewMessage.system(content))
        elif role_str == "user":
            result.append(NewMessage.user(content))
        elif role_str == "assistant":
            result.append(NewMessage.assistant(content))
        elif role_str == "tool":
            result.append(NewMessage.from_text(role_str, content))
    return result


def _new_to_old_messages(new_msgs: list[NewMessage]) -> list[OldMessage]:
    """Convert new schema.messages.Message list back to old cscode.core.messages.Message list."""
    result: list[OldMessage] = []
    for msg in new_msgs:
        content = msg.content
        role_map = {
            "system": OldMessageRole.SYSTEM,
            "user": OldMessageRole.USER,
            "assistant": OldMessageRole.ASSISTANT,
            "tool": OldMessageRole.TOOL,
        }
        role = role_map.get(msg.role, OldMessageRole.USER)
        if role == OldMessageRole.ASSISTANT and not content:
            continue
        result.append(OldMessage(role=role, content=content))
    return result


def _llm_event_to_dict(event: LLMEvent) -> dict[str, object]:
    """Convert LLMEvent to old-style dict for SSE streaming."""
    match event:
        case TextDelta(text=t):
            return {"type": "step.started", "data": {"text": t}}
        case TextEnded(full_text=t):
            return {"type": "text.ended", "data": {"content": t}}
        case ToolCallEnded(tool_call_id=tcid, name=n, args=a):
            return {"type": "tool.called", "data": {"name": n, "arguments": a, "id": tcid}}
        case ToolResult(tool_call_id=tcid, result=r):
            return {"type": "tool.success", "data": {"tool_call_id": tcid, "result": r}}
        case ToolFailure(tool_call_id=tcid, error=e):
            return {"type": "tool.failed", "data": {"tool_call_id": tcid, "error": e}}
        case Finish():
            return {"type": "step.ended", "data": {}}
        case _:
            return {"type": "step.started", "data": {"text": str(event)}}


# Output directory for user-facing generated files
OUTPUTS_DIR = Path("/tmp/cscode-outputs")

# Auto-compaction: compact after each agent run if events exceed threshold
COMPACTION_THRESHOLD = 100  # relevant events (prompt.admitted + text.ended + tool.success + tool.failed)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Find web dist in multiple locations
def find_web_dist() -> Path:
    # 1. Check CSCORE_RESOURCE_DIR env var (set by Tauri Rust side)
    import os
    resource_dir = os.environ.get("CSCORE_RESOURCE_DIR")
    if resource_dir:
        bundled = Path(resource_dir) / "web-dist"
        logger.debug("CSCORE_RESOURCE_DIR={resource_dir}, bundled={bundled}, exists={bundled.exists()}")
        if bundled.exists():
            logger.debug("returning bundled web-dist at %s", bundled)
            return bundled

    # 2. Try to find the app bundle by checking the executable path FIRST
    try:
        import sys
        exe_path = Path(sys.executable).resolve()
        logger.debug("find_web_dist: exe_path=%s", exe_path)
        # Check if we're in a macOS app bundle (Contents/MacOS/)
        if exe_path.parent.name == "MacOS" and exe_path.parent.parent.name == "Contents":
            resources = exe_path.parent.parent / "Resources" / "web-dist"
            logger.debug("checking resources={resources}, exists={resources.exists()}")
            if resources.exists():
                logger.debug("returning resources={resources}")
                return resources
    except Exception:
        logger.debug("exe_path check failed: {e}")

    # 3. Try to find the app bundle by checking the current working directory
    try:
        cwd = Path.cwd()
        logger.debug("cwd={cwd}")
        # Check if we're in a macOS app bundle (Contents/MacOS/)
        if cwd.name == "MacOS" and cwd.parent.name == "Contents":
            resources = cwd.parent / "Resources" / "web-dist"
            logger.debug("checking cwd resources={resources}, exists={resources.exists()}")
            if resources.exists():
                return resources
    except Exception:
        logger.debug("cwd check failed: {e}")

    # 4. Bundled location (PyInstaller)
    if hasattr(__import__('sys'), 'frozen'):
        base = Path(getattr(__import__('sys'), '_MEIPASS', Path.cwd()))
        bundled = base / "web" / "dist"
        if bundled.exists():
            return bundled

    # 5. Check for app bundle Resources/web-dist from executable location
    try:
        import sys
        exe_path = Path(sys.executable).resolve()
        logger.debug("checking parents of exe_path={exe_path}")
        for parent in exe_path.parents:
            if parent.name == "Contents":
                resources = parent / "Resources" / "web-dist"
                logger.debug("checking parent resources={resources}, exists={resources.exists()}")
                if resources.exists():
                    return resources
    except Exception:
        logger.debug("parent check failed: {e}")

    # 6. Development location
    dev_path = Path(__file__).resolve().parent.parent / "web" / "dist"
    logger.debug("dev_path={dev_path}, exists={dev_path.exists()}")
    if dev_path.exists():
        return dev_path

    # 7. Fallback to parent directories
    for parent in Path(__file__).resolve().parents:
        web_path = parent / "web" / "dist"
        if web_path.exists():
            return web_path

    return Path(__file__).resolve().parent.parent / "web" / "dist"

WEB_DIST = find_web_dist()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _db, _session_store, _agent, _event_store, _coordinator, _projector, _compactor, _tracker, _question_registry

    # Diagnostics log
    fh = logging.FileHandler("/tmp/cscode-diag.log", mode="w")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(fh)
    logging.getLogger().setLevel(logging.DEBUG)
    logger.info("=== CScode server started (diagnostics logging to /tmp/cscode-diag.log) ===")

    resource_dir = os.environ.get("CSCORE_RESOURCE_DIR", "")
    if resource_dir:
        python_dir = os.path.join(resource_dir, "python")
        if os.path.isdir(python_dir):
            existing = os.environ.get("PYTHONPATH", "")
            os.environ["PYTHONPATH"] = f"{python_dir}{os.pathsep}{existing}" if existing else python_dir
            logger.debug("Set PYTHONPATH for subprocesses: {python_dir}")

    db_path = os.environ.get("CSCODE_DB_PATH")
    _db = Database(db_path=db_path)
    await _db.init()
    _session_store = SessionStore(_db)
    _event_store = EventStore(_db)
    _coordinator = SessionCoordinator()
    _projector = Projector(_db)
    _compactor = Compactor(_db, _event_store, _projector)
    _tracker = TaskTracker(_db)
    _question_registry = QuestionRegistry()

    os.makedirs("/tmp/cscode-outputs", exist_ok=True)
    template_path = "/tmp/cscode-outputs/xlsx_template.py"
    if not os.path.exists(template_path):
        with open(template_path, "w") as f:
            f.write(_XLSX_TEMPLATE)
        os.chmod(template_path, 0o755)

    config = load_config()
    _agent = create_agent_v2(
        config,
        tool_registry=create_tool_registry(),
    )
    _agent._max_tool_rounds = 20

    yield

    if _db is not None:
        await _db.close()


app = FastAPI(title="CScode API", version="0.3.3", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_db: Database | None = None
_session_store: SessionStore | None = None
_agent: AgentV2 | None = None
_event_store: EventStore | None = None
_coordinator: SessionCoordinator | None = None
_projector: Projector | None = None
_compactor: Compactor | None = None
_active_agent_tasks: dict[str, asyncio.Task[Any]] = {}
_tracker: TaskTracker | None = None
_question_registry: QuestionRegistry | None = None


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


@api_router.post("/chat", response_model=ChatResponse)
async def chat(request: Request) -> ChatResponse:
    message: str = ""
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
    import asyncio
    import json

    message: str = ""
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
        nonlocal session_id
        global _agent, _session_store, _db, _event_store, _coordinator, _projector, _compactor
        if _agent is None or _session_store is None:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Server not initialized'})}\n\n"
            return

        session_id = session_id or str(uuid.uuid4())

        try:
            if _session_store is not None:
                session = await _session_store.get(session_id)
                if session is None:
                    config_data = None
                    if _db is not None:
                        store = ConfigStore(_db)
                        saved_config = await store.get()
                        if saved_config:
                            config_data = saved_config

                    provider_name: str = "openai"
                    model: str = "gpt-4o"
                    if config_data:
                        provider_name = config_data.get("provider", "openai")
                        model = config_data.get("model", "gpt-4o")

                    await _session_store.create(title="New Chat", provider=provider_name, model=model, session_id=session_id)
                    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            existing_old_messages: list[OldMessage] = []
            if _session_store is not None:
                existing_old_messages = await _session_store.get_messages(session_id)

            FILE_CONTEXT_MAX = 30000  # Limit to prevent API errors
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

            # Build new-style messages for AgentV2
            new_messages = _old_to_new_messages(existing_old_messages)

            # Inject system prompt as first message if not present
            if new_messages and new_messages[0].role != "system":
                new_messages.insert(0, NewMessage.system(
                    "You are CScode, an AI-powered coding assistant. You help users write, review, and debug code. "
                    "You have access to tools for reading, writing, and editing files, "
                    "running shell commands, searching codebases, and browsing the web."
                ))
            elif not new_messages:
                new_messages.append(NewMessage.system(
                    "You are CScode, an AI-powered coding assistant. You help users write, review, and debug code. "
                    "You have access to tools for reading, writing, and editing files, "
                    "running shell commands, searching codebases, and browsing the web."
                ))

            if file_context:
                new_messages.append(NewMessage.system(file_context))
            user_text = message.strip() if message else "请分析附件内容"
            new_messages.append(NewMessage.user(user_text))

            # Append prompt.admitted event to EventStore
            if _event_store is not None:
                await _event_store.append(session_id, [
                    {"type": "prompt.admitted", "data": {"content": message, "files": attached_filenames}}
                ])

            # Save old-format messages (before agent) to prevent data loss on failure
            if _session_store is not None:
                await _session_store.save_messages(session_id, _new_to_old_messages(new_messages))

            queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

            def _e(data: dict[str, object]) -> str:
                data["session_id"] = session_id
                return f"data: {json.dumps(data)}\n\n"

            _persist_event_types = frozenset({
                "step.started", "text.ended", "step.ended",
                "tool.called", "tool.success", "tool.failed",
            })

            async def on_event(event: LLMEvent) -> None:
                sse_event = _llm_event_to_dict(event)
                sse_event["session_id"] = session_id
                await queue.put(sse_event)
                if _event_store is not None:
                    evt_type = sse_event.get("type", "")
                    if isinstance(evt_type, str) and evt_type in _persist_event_types:
                        evt_data = sse_event.get("data", {})
                        await _event_store.append(session_id, [
                            {"type": evt_type, "data": dict(evt_data) if isinstance(evt_data, dict) else {}}
                        ])

            before = time.time()

            async def agent_runner() -> str:
                assert _agent is not None
                logger.info("[DIAG] agent_runner: starting run_with_messages session=%s", session_id)
                t0 = time.time()
                try:
                    result = await _agent.run_with_messages(
                        new_messages,
                        on_event=on_event,
                    )
                    return result
                finally:
                    logger.info("[DIAG] agent_runner: completed session=%s in %.1fs", session_id, time.time() - t0)

            # Use Coordinator for per-session serialization (prevents same-session concurrent)
            async def run_with_coordinator() -> None:
                if _coordinator is not None:
                    await _coordinator.run(session_id, _CallableProcessor(agent_runner))
                else:
                    await agent_runner()

            # Cancel any existing agent task for this session before starting new one
            old_task = _active_agent_tasks.get(session_id)
            if old_task and not old_task.done():
                logger.info("Cancelling previous agent task for session %s", session_id)
                old_task.cancel()
                try:
                    await asyncio.wait_for(old_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            agent_task = asyncio.create_task(run_with_coordinator())
            _active_agent_tasks[session_id] = agent_task

            last_event_time = time.time()
            last_status_time = time.time()
            while True:
                if await request.is_disconnected():
                    logger.info("Client disconnected for session %s, cancelling task", session_id)
                    if _question_registry is not None:
                        await _question_registry.cancel_session(session_id)
                    agent_task.cancel()
                    break
                if agent_task.done():
                    while not queue.empty():
                        try:
                            event = queue.get_nowait()
                            yield f"data: {json.dumps(event)}\n\n"
                        except asyncio.QueueEmpty:
                            break
                    try:
                        response = agent_task.result()
                        if _session_store is not None:
                            await _session_store.save_messages(session_id, _new_to_old_messages(new_messages))
                        for f in OUTPUTS_DIR.iterdir():
                            if f.is_file() and f.stat().st_mtime >= before:
                                yield _e({'type': 'file_created', 'filename': f.name})
                        if not response:
                            logger.warning("[DIAG] Empty response from agent for session=%s", session_id)
                            yield _e({'type': 'error', 'content': 'LLM returned empty response - API returned no content'})
                        else:
                            yield _e({'type': 'complete', 'content': response})
                    except Exception as e:
                        logger.warning("[DIAG] agent task error session=%s error=%s", session_id, e)
                        if _session_store is not None:
                            err_old = _new_to_old_messages(new_messages)
                            err_old.append(OldMessage(role=OldMessageRole.ASSISTANT, content=f"[Task interrupted by error: {e}]"))
                            await _session_store.save_messages(session_id, err_old)
                        yield _e({'type': 'error', 'content': str(e)})
                    finally:
                        if _session_store is not None:
                            session = await _session_store.get(session_id)
                            is_new = session is None or (session.title in ("New Session", "New Chat"))
                            if is_new:
                                generated_title = None
                                try:
                                    title_sys = NewMessage.system("Summarize the user's request in 3-6 words. Return ONLY the title, no quotes, no punctuation.")
                                    title_usr = NewMessage.user(message or "")
                                    title_r = await _agent.llm_client.generate(
                                        LLMRequest(
                                            model=_agent.llm_client.route.model,
                                            messages=(title_sys, title_usr),
                                        )
                                    )
                                    title_text = title_r.content.strip().strip('"\'.,!?')
                                    if title_text:
                                        generated_title = title_text
                                except Exception:
                                    pass
                                if not generated_title:
                                    generated_title = (message[:47] + "...") if len(message) > 50 else (message or "New Chat")
                                await _session_store.update_title(session_id, generated_title)
                                yield _e({'type': 'session:title', 'title': generated_title})
                    asyncio.create_task(_auto_compact(session_id))
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                    last_event_time = time.time()
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    now = time.time()
                    if now - last_event_time > 10:
                        logger.info("[DIAG] keepalive session=%s last_event=%.1fs ago", session_id, now - last_event_time)
                        yield ": keepalive\n\n"
                        last_event_time = now
                    if now - last_status_time > 60:
                        yield _e({'type': 'status', 'message': 'Agent is working...'})
                        last_status_time = now
                    continue

        except Exception as e:
            yield _e({'type': 'error', 'content': str(e)})

        finally:
            if _active_agent_tasks.get(session_id) is agent_task:
                del _active_agent_tasks[session_id]
            if not agent_task.done():
                logger.info("[DIAG] Generator exiting, cancelling agent task for session %s", session_id)
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
        try:
            import asyncio
            import json
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
    global _agent
    if _agent is None or _session_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    session_id = session_id or str(uuid.uuid4())

    try:
        # Ensure session exists in database
        if _session_store is not None:
            session = await _session_store.get(session_id)
            if session is None:
                config_data = None
                if _db is not None:
                    store = ConfigStore(_db)
                    saved_config = await store.get()
                    if saved_config:
                        config_data = saved_config

                provider_name: str = "openai"
                model: str = "gpt-4o"
                if config_data:
                    provider_name = config_data.get("provider", "openai")
                    model = config_data.get("model", "gpt-4o")

                logger.debug("Creating new session {session_id} with provider={provider_name}, model={model}")
                await _session_store.create(title="New Chat", provider=provider_name, model=model, session_id=session_id)
                logger.debug("Session created successfully")

        # Load existing messages for this session
        existing_old_messages: list[OldMessage] = []
        if _session_store is not None:
            existing_old_messages = await _session_store.get_messages(session_id)

        # Build file context if files were uploaded
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

        # Build new-style messages for AgentV2
        new_messages = _old_to_new_messages(existing_old_messages)
        if new_messages and new_messages[0].role != "system":
            new_messages.insert(0, NewMessage.system(
                "You are CScode, an AI-powered coding assistant. You help users write, review, and debug code. "
                "You have access to tools for reading, writing, and editing files, "
                "running shell commands, searching codebases, and browsing the web."
            ))
        elif not new_messages:
            new_messages.append(NewMessage.system(
                "You are CScode, an AI-powered coding assistant. You help users write, review, and debug code. "
                "You have access to tools for reading, writing, and editing files, "
                "running shell commands, searching codebases, and browsing the web."
            ))
        if file_context:
            new_messages.append(NewMessage.system(file_context))
        user_text = message.strip() if message else "请分析附件内容"
        new_messages.append(NewMessage.user(user_text))

        # Save user message immediately (before agent) to prevent data loss on failure
        if _session_store is not None:
            await _session_store.save_messages(session_id, _new_to_old_messages(new_messages))

        # Run agent with full message history
        try:
            assert _agent is not None
            response = await _agent.run_with_messages(new_messages, on_event=None)
        except Exception as e:
            if _session_store is not None:
                err_old = _new_to_old_messages(new_messages)
                err_old.append(OldMessage(role=OldMessageRole.ASSISTANT, content=f"[Task interrupted by error: {e}]"))
                await _session_store.save_messages(session_id, err_old)
            logger.error("agent_runner error: %s", e)
            raise

        # Save updated messages to session (now includes assistant response)
        if _session_store is not None:
            await _session_store.save_messages(session_id, _new_to_old_messages(new_messages))

        # Auto-generate title for new sessions
        if _session_store is not None:
            session = await _session_store.get(session_id)
            is_new = session is None or (session.title in ("New Session", "New Chat"))
            if is_new:
                try:
                    title_sys = NewMessage.system("Summarize the user's request in 3-6 words. Return ONLY the title, no quotes, no punctuation.")
                    title_usr = NewMessage.user(message or "")
                    title_r = await _agent.llm_client.generate(
                        LLMRequest(
                            model=_agent.llm_client.route.model,
                            messages=(title_sys, title_usr),
                        )
                    )
                    generated_title = title_r.content.strip().strip('"\'.,!?')
                    if generated_title:
                        await _session_store.update_title(session_id, generated_title)
                        logger.debug("Auto-generated title: %s", generated_title)
                except Exception:
                    pass
                # Fallback
                session = await _session_store.get(session_id)
                if session is not None and session.title in ("New Session", "New Chat"):
                    fallback = (message[:47] + "...") if len(message) > 50 else (message or "New Chat")
                    await _session_store.update_title(session_id, fallback)

        # Auto-compact if threshold exceeded (fire-and-forget)
        asyncio.create_task(_auto_compact(session_id))

        logger.debug("total_handle_chat completed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return ChatResponse(response=response, session_id=session_id)


@api_router.get("/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    if _session_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    sessions = await _session_store.list()
    return [
        {
            "id": s.id,
            "title": s.title,
            "provider": s.provider,
            "model": s.model,
            "created_at": s.created_at.isoformat() if s.created_at else "",
            "updated_at": s.updated_at.isoformat() if s.updated_at else "",
        }
        for s in sessions
    ]


@api_router.get("/config")
async def get_config() -> dict[str, Any]:
    # First try to load from database
    if _db is not None:
        store = ConfigStore(_db)
        saved_config = await store.get()
        if saved_config:
            return saved_config

    # Fallback to default config
    config = load_config()
    return config.to_dict()


@api_router.post("/config")
async def save_config(request: ConfigRequest) -> dict[str, Any]:
    config_data = request.model_dump(exclude_none=True)

    if _db is not None:
        store = ConfigStore(_db)
        # Remove empty string fields (frontend sends empty strings for unfilled inputs)
        config_data = {k: v for k, v in config_data.items() if not isinstance(v, str) or v}
        # Preserve existing api_key when request doesn't provide one
        if "api_key" not in config_data:
            existing = await store.get()
            if existing and existing.get("api_key"):
                config_data["api_key"] = existing["api_key"]
        await store.save(config_data)
    return {"status": "saved", "config": config_data}


@api_router.post("/sessions", response_model=dict[str, Any])
async def create_session(request: SessionCreateRequest) -> dict[str, Any]:
    if _session_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    session = await _session_store.create(title=request.title)
    return {
        "id": session.id,
        "title": session.title,
        "provider": session.provider,
        "model": session.model,
        "created_at": session.created_at.isoformat() if session.created_at else "",
        "updated_at": session.updated_at.isoformat() if session.updated_at else "",
    }


@api_router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    if _session_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    await _session_store.delete(session_id)
    return {"status": "deleted", "id": session_id}


@api_router.patch("/sessions/{session_id}")
async def update_session(session_id: str, request: dict[str, Any]) -> dict[str, Any]:
    if _session_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    title = request.get("title")
    if title:
        await _session_store.update_title(session_id, title)

    return {"status": "updated", "id": session_id}


@api_router.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str) -> dict[str, str]:
    global _active_agent_tasks, _question_registry
    if _question_registry is not None:
        await _question_registry.cancel_session(session_id)
    task = _active_agent_tasks.get(session_id)
    if task and not task.done():
        logger.info("Stopping agent task for session %s (user request)", session_id)
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=10.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        del _active_agent_tasks[session_id]
    return {"status": "stopped", "session_id": session_id}


@api_router.get("/sessions/{session_id}/questions")
async def list_pending_questions(session_id: str) -> list[dict[str, Any]]:
    global _question_registry
    if _question_registry is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    return await _question_registry.list_pending(session_id)


class QuestionReplyRequest(BaseModel):
    answers: list[str]


@api_router.post("/sessions/{session_id}/questions/{request_id}/reply")
async def reply_question(session_id: str, request_id: str, body: QuestionReplyRequest) -> dict[str, str]:
    global _question_registry
    if _question_registry is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    found = await _question_registry.resolve(request_id, body.answers)
    if not found:
        raise HTTPException(status_code=404, detail="Question request not found or already answered")
    return {"status": "answered", "request_id": request_id}


@api_router.post("/sessions/{session_id}/questions/{request_id}/reject")
async def reject_question(session_id: str, request_id: str) -> dict[str, str]:
    global _question_registry
    if _question_registry is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    found = await _question_registry.reject(request_id)
    if not found:
        raise HTTPException(status_code=404, detail="Question request not found or already answered")
    return {"status": "rejected", "request_id": request_id}


@api_router.get("/sessions/{session_id}/export")
async def export_session(session_id: str) -> dict[str, Any]:
    if _session_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    session = await _session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = await _session_store.get_messages(session_id)
    return {
        "id": session.id,
        "title": session.title,
        "provider": session.provider,
        "model": session.model,
        "created_at": session.created_at.isoformat() if session.created_at else "",
        "updated_at": session.updated_at.isoformat() if session.updated_at else "",
        "messages": [
            {
                "role": msg.role.value,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else "",
            }
            for msg in messages
        ],
    }


@api_router.post("/sessions/import")
async def import_session(request: dict[str, Any]) -> dict[str, Any]:
    if _session_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    title = request.get("title", "Imported Session")
    provider = request.get("provider", "openai")
    model = request.get("model", "gpt-4o")
    messages_data = request.get("messages", [])

    session = await _session_store.create(title=title, provider=provider, model=model)
    if not session.id:
        raise HTTPException(status_code=500, detail="Failed to create session")
    messages = [
        OldMessage(role=OldMessageRole(m["role"]), content=m["content"]) for m in messages_data
    ]
    await _session_store.save_messages(session.id, messages)

    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else "",
    }


@api_router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str) -> list[dict[str, Any]]:
    if _session_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    msgs: list[OldMessage] = await _session_store.get_messages(session_id)
    return [
        {
            "role": msg.role.value,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else "",
        }
        for msg in msgs if not (msg.role == OldMessageRole.ASSISTANT and not msg.content)
    ]


@api_router.get("/files/search")
async def search_files(q: str = "") -> list[str]:
    import fnmatch
    import os

    if not q or not q.strip():
        return []

    cwd = os.getcwd()
    results: list[str] = []

    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git", ".venv", "dist", "build")]
        for f in files:
            if f.startswith("."):
                continue
            rel_path = os.path.relpath(os.path.join(root, f), cwd)
            if fnmatch.fnmatch(f, q) or fnmatch.fnmatch(rel_path, q) or q.lower() in f.lower():
                results.append(rel_path)
            if len(results) >= 50:
                break
        if len(results) >= 50:
            break

    return results


async def _try_open_file(file_path: Path) -> None:
    """Try to open a file with the default app. Non-blocking."""
    import asyncio
    import platform
    system = platform.system()
    try:
        cmd = ["open", str(file_path)] if system == "Darwin" else (
            ["start", "", str(file_path)] if system == "Windows" else ["xdg-open", str(file_path)]
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_data = await proc.communicate()
        if proc.returncode != 0:
            stderr_text = stderr_data.decode(errors="replace").strip()
            logger.warning("Failed to open file %s: returncode=%d stderr=%s",
                           file_path, proc.returncode, stderr_text)
        else:
            logger.info("Opened file %s via %s", file_path, cmd[0])
    except Exception as e:
        logger.warning("Failed to open file %s (exception): %s", file_path, e)


@api_router.get("/download/{filename:path}")
async def download_file(filename: str, raw: bool = False, quiet: bool = False) -> Any:
    """Serve file content (raw=true) or open the file directly from /tmp/cscode-outputs/."""
    import asyncio
    from urllib.parse import quote

    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    file_path = OUTPUTS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if raw:
        basename = file_path.name
        try:
            basename.encode("ascii")
            disposition = f'attachment; filename="{basename}"'
        except UnicodeEncodeError:
            disposition = f"attachment; filename*=UTF-8\'\'{quote(basename, encoding='utf-8')}"
        return FileResponse(
            str(file_path),
            headers={"Content-Disposition": disposition},
        )

    if not quiet:
        asyncio.create_task(_try_open_file(file_path))

    # Always serve the file as download; _try_open_file runs concurrently
    basename = file_path.name
    try:
        basename.encode("ascii")
        disposition = f'attachment; filename="{basename}"'
    except UnicodeEncodeError:
        disposition = f"attachment; filename*=UTF-8\'\'{quote(basename, encoding='utf-8')}"
    return FileResponse(
        str(file_path),
        headers={"Content-Disposition": disposition},
    )


app.include_router(api_router)

# Mount outputs directory for file download
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR), check_dir=True), name="outputs")

if WEB_DIST.exists():
    # Mount assets directory at /assets FIRST - before any routes
    assets_dir = WEB_DIST / "assets"
    logger.debug("assets_dir={assets_dir}, exists={assets_dir.exists()}")
    if assets_dir.exists():
        logger.debug("assets_dir contents: {list(assets_dir.iterdir())}")
        app.mount("/assets", StaticFiles(directory=str(assets_dir), html=False, check_dir=True), name="assets")
        logger.debug("Assets mounted at /assets")

    # Test endpoint
    @app.get("/assets/test")
    async def test_assets() -> dict[str, str]:
        return {"message": "assets endpoint works"}

    # Serve index.html at root
    from fastapi.responses import FileResponse

    @app.get("/")
    async def serve_index() -> Any:
        index_path = WEB_DIST / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"detail": "Not found"}

    # Serve other static files from web-dist
    @app.get("/{path:path}")
    async def serve_static(path: str) -> Any:
        file_path = WEB_DIST / path
        logger.debug("serve_static: path=%s, file_path=%s, exists=%s", path, file_path, file_path.exists())
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return {"detail": "Not found"}


_XLSX_TEMPLATE = r"""#!/usr/bin/env python3
import csv, json, os, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

def build_xlsx(data):
    wb = Workbook(); ws = wb.active
    ws.title = data.get("sheet_name", "Sheet1")
    cols, rows = data.get("columns", []), data.get("data", [])
    hf = Font(bold=True, color="FFFFFF", size=11)
    hfill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    ha = Alignment(horizontal="center", vertical="center")
    bdr = Border(left=Side(style="thin"), right=Side(style="thin"), top=Side(style="thin"), bottom=Side(style="thin"))
    for ci, n in enumerate(cols, 1):
        c = ws.cell(row=1, column=ci, value=n); c.font = hf; c.fill = hfill; c.alignment = ha; c.border = bdr
    for ri, rd in enumerate(rows, 2):
        for ci, v in enumerate(rd, 1):
            c = ws.cell(row=ri, column=ci, value=v); c.border = bdr; c.alignment = Alignment(vertical="center")
    for col in ws.columns:
        best = max((len(str(c.value or "")) for c in col), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(best + 3, 60)
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    return wb

def csv_to_data(path):
    with open(path, newline="", encoding="utf-8") as f:
        r = list(csv.reader(f))
    return {"columns": r[0], "data": r[1:], "sheet_name": os.path.splitext(os.path.basename(path))[0]} if r else {"columns":[],"data":[],"sheet_name":"Sheet1"}

if __name__ == "__main__":
    if len(sys.argv) < 3 or "--output" not in sys.argv:
        print("Usage: xlsx_template.py <input.json|csv> --output <out.xlsx>", file=sys.stderr); sys.exit(1)
    i = sys.argv.index("--output")
    inp, out = sys.argv[1], sys.argv[i+1] if i+1 < len(sys.argv) and not sys.argv[i+1].startswith("--") else "out.xlsx"
    data = csv_to_data(inp) if inp.endswith(".csv") else json.load(open(inp, encoding="utf-8"))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True); build_xlsx(data).save(out)
    print(f"Saved to {out}")
"""


def _detect_timeout(message: str, files: list[Any] | None, attached_filenames: list[str]) -> float:
    gen_keywords = ["xlsx", "excel", "spreadsheet", "pdf", "生成", "测试用例", "报告", "文档"]
    msg_lower = message.lower()
    has_gen_task = any(kw in msg_lower for kw in gen_keywords)

    # Also check file extensions
    file_exts = [f.lower() for f in attached_filenames] if attached_filenames else []
    has_file_gen_task = any(ext.endswith(('.xlsx', '.xls', '.pdf', '.docx', '.doc')) for ext in file_exts)

    has_large_context = files and (attached_filenames or message.count("用例") > 5 or len(message) > 200)
    if has_gen_task or has_file_gen_task or has_large_context:
        return 600.0
    if len(message) < 50 and not files:
        return 180.0  # Increased from 120
    return 300.0


async def _auto_compact(session_id: str) -> None:
    global _compactor, _event_store
    if _compactor is None or _event_store is None:
        return
    try:
        events = await _event_store.read(session_id)
        relevant = [e for e in events if e.type in ("prompt.admitted", "text.ended", "tool.success", "tool.failed")]
        if len(relevant) >= COMPACTION_THRESHOLD:
            await _compactor.compact(session_id)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Auto-compaction failed")



