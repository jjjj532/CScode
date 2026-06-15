from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

from collections.abc import AsyncGenerator

from fastapi import APIRouter, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cscode.core.config import load_config
from cscode.core.engine import Agent, AgentOptions
from cscode.core.messages import Message, MessageRole
from cscode.providers import create_provider
from cscode.storage.db import Database
from cscode.storage.session import SessionStore
from cscode.tools.base import ToolRegistry
from cscode.tools.bash import BashTool
from cscode.tools.edit import EditTool
from cscode.tools.glob import GlobTool
from cscode.tools.grep import GrepTool
from cscode.tools.ls import LsTool
from cscode.tools.read import ReadTool
from cscode.tools.write import WriteTool
from cscode.tools.browser import BrowserTool

api_router = APIRouter(prefix="/api")

# Output directory for user-facing generated files
OUTPUTS_DIR = Path("/tmp/cscode-outputs")
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Find web dist in multiple locations
def find_web_dist() -> Path:
    # 1. Check CSCORE_RESOURCE_DIR env var (set by Tauri Rust side)
    import os
    resource_dir = os.environ.get("CSCORE_RESOURCE_DIR")
    if resource_dir:
        bundled = Path(resource_dir) / "web-dist"
        print(f"DEBUG: CSCORE_RESOURCE_DIR={resource_dir}, bundled={bundled}, exists={bundled.exists()}")
        if bundled.exists():
            print(f"DEBUG: returning bundled web-dist at {bundled}")
            return bundled
    
    # 2. Try to find the app bundle by checking the executable path FIRST
    try:
        import sys
        exe_path = Path(sys.executable).resolve()
        print(f"DEBUG find_web_dist: exe_path={exe_path}")
        # Check if we're in a macOS app bundle (Contents/MacOS/)
        if exe_path.parent.name == "MacOS" and exe_path.parent.parent.name == "Contents":
            resources = exe_path.parent.parent / "Resources" / "web-dist"
            print(f"DEBUG: checking resources={resources}, exists={resources.exists()}")
            if resources.exists():
                print(f"DEBUG: returning resources={resources}")
                return resources
    except Exception as e:
        print(f"DEBUG: exe_path check failed: {e}")
    
    # 3. Try to find the app bundle by checking the current working directory
    try:
        cwd = Path.cwd()
        print(f"DEBUG: cwd={cwd}")
        # Check if we're in a macOS app bundle (Contents/MacOS/)
        if cwd.name == "MacOS" and cwd.parent.name == "Contents":
            resources = cwd.parent / "Resources" / "web-dist"
            print(f"DEBUG: checking cwd resources={resources}, exists={resources.exists()}")
            if resources.exists():
                return resources
    except Exception as e:
        print(f"DEBUG: cwd check failed: {e}")
    
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
        print(f"DEBUG: checking parents of exe_path={exe_path}")
        for parent in exe_path.parents:
            if parent.name == "Contents":
                resources = parent / "Resources" / "web-dist"
                print(f"DEBUG: checking parent resources={resources}, exists={resources.exists()}")
                if resources.exists():
                    return resources
    except Exception as e:
        print(f"DEBUG: parent check failed: {e}")
    
    # 6. Development location
    dev_path = Path(__file__).resolve().parent.parent / "web" / "dist"
    print(f"DEBUG: dev_path={dev_path}, exists={dev_path.exists()}")
    if dev_path.exists():
        return dev_path
    
    # 7. Fallback to parent directories
    for parent in Path(__file__).resolve().parents:
        web_path = parent / "web" / "dist"
        if web_path.exists():
            return web_path
    
    return Path(__file__).resolve().parent.parent / "web" / "dist"

WEB_DIST = find_web_dist()

app = FastAPI(title="CScode API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_db: Database | None = None
_session_store: SessionStore | None = None
_agent: Agent | None = None


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

    async def event_stream() -> AsyncGenerator[str, None]:
        nonlocal session_id
        global _agent, _session_store, _db
        if _agent is None or _session_store is None:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Server not initialized'})}\n\n"
            return

        try:
            from cscode.core.config import ConfigStore
            if _db is not None:
                store = ConfigStore(_db)
                saved_config = await store.get()
                if saved_config:
                    from cscode.core.config import Config
                    from cscode.providers import create_provider
                    config = Config.from_dict(saved_config)
                    provider = create_provider(config)
                    _agent.provider = provider
                    _agent.config = config
        except Exception as e:
            import logging
            logging.warning(f"Failed to load config from DB: {e}")

        session_id = session_id or str(uuid.uuid4())
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        try:

            if _session_store is not None:
                session = await _session_store.get(session_id)
                if session is None:
                    from cscode.core.config import ConfigStore
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

            existing_messages: list[Message] = []
            if _session_store is not None:
                existing_messages = await _session_store.get_messages(session_id)

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

            messages = list(existing_messages)
            # Limit to recent messages to prevent API errors
            MAX_MESSAGES = 20
            if len(messages) > MAX_MESSAGES:
                messages = messages[-MAX_MESSAGES:]
            if _agent.options.system_prompt and (not messages or messages[0].role != MessageRole.SYSTEM or _agent.options.system_prompt not in messages[0].content):
                messages.insert(0, Message(role=MessageRole.SYSTEM, content=_agent.options.system_prompt))
            if file_context:
                messages.append(Message(role=MessageRole.SYSTEM, content=file_context))
            user_text = message.strip() if message else "请分析附件内容"
            messages.append(Message(role=MessageRole.USER, content=user_text))

            # Save user message immediately so frontend session reload finds it
            if _session_store is not None:
                await _session_store.save_messages(session_id, messages)

            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
            async def on_event(event: dict[str, Any]) -> None:
                await queue.put(event)

            before = time.time()
            dynamic_timeout = _detect_timeout(message, files, attached_filenames)
            agent_task = asyncio.create_task(
                _agent._run_loop(messages, attached_filenames=attached_filenames if attached_filenames else None, timeout=dynamic_timeout, on_event=on_event)
            )

            while True:
                if await request.is_disconnected():
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
                            await _session_store.save_messages(session_id, messages)
                        # Emit file_created for files modified during this agent run
                        for f in OUTPUTS_DIR.iterdir():
                            if f.is_file() and f.stat().st_mtime >= before:
                                yield f"data: {json.dumps({'type': 'file_created', 'filename': f.name})}\n\n"
                        yield f"data: {json.dumps({'type': 'complete', 'content': response})}\n\n"
                    except Exception as e:
                        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    continue

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _handle_chat(
    message: str, session_id: str | None, files: list[tuple[str, bytes]] | None = None
) -> ChatResponse:
    global _agent
    if _agent is None or _session_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    try:
        from cscode.core.config import ConfigStore
        if _db is not None:
            store = ConfigStore(_db)
            saved_config = await store.get()
            print(f"DEBUG: Saved config: {saved_config}")
            if saved_config:
                from cscode.core.config import Config
                from cscode.providers import create_provider
                config = Config.from_dict(saved_config)
                print(f"DEBUG: Loaded model: {config.model}, provider: {config.provider}")
                provider = create_provider(config)
                _agent.provider = provider
                _agent.config = config
    except Exception as e:
        import logging
        logging.warning(f"Failed to load config from DB: {e}")

    session_id = session_id or str(uuid.uuid4())

    try:
        import time
        t0 = time.time()
        # Ensure session exists in database
        if _session_store is not None:
            session = await _session_store.get(session_id)
            if session is None:
                from cscode.core.config import ConfigStore
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
                
                print(f"DEBUG: Creating new session {session_id} with provider={provider_name}, model={model}")
                await _session_store.create(title="New Chat", provider=provider_name, model=model, session_id=session_id)
                print("DEBUG: Session created successfully")
        
        # Load existing messages for this session
        existing_messages: list[Message] = []
        if _session_store is not None:
            existing_messages = await _session_store.get_messages(session_id)
        print(f"PERF: load_messages={time.time()-t0:.2f}s")
        t1 = time.time()
        
        # Build file context if files were uploaded
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
        print(f"PERF: parse_files={time.time()-t1:.2f}s, file_context_len={len(file_context)}")
        t2 = time.time()
        
        # Build messages with history
        messages = list(existing_messages)
        # Add system prompt on first message if not already present
        if _agent.options.system_prompt and (not existing_messages or existing_messages[0].role != MessageRole.SYSTEM or _agent.options.system_prompt not in existing_messages[0].content):
            messages.insert(0, Message(role=MessageRole.SYSTEM, content=_agent.options.system_prompt))
        # File context as SYSTEM must come BEFORE user message
        if file_context:
            messages.append(Message(role=MessageRole.SYSTEM, content=file_context))
        user_text = message.strip() if message else "请分析附件内容"
        messages.append(Message(role=MessageRole.USER, content=user_text))
        
        # Run agent with full message history
        print(f"PERF: build_messages={time.time()-t2:.2f}s, total_messages={len(messages)}, total_chars={sum(len(m.content) for m in messages)}")
        t3 = time.time()
        dynamic_timeout = _detect_timeout(message, files, attached_filenames)
        response = await _agent._run_loop(messages, attached_filenames=attached_filenames if attached_filenames else None, timeout=dynamic_timeout)
        print(f"PERF: agent_run_loop={time.time()-t3:.2f}s")
        
        # Save updated messages to session
        if _session_store is not None:
            await _session_store.save_messages(session_id, messages)
        print(f"PERF: total_handle_chat={time.time()-t0:.2f}s")
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
    from cscode.core.config import load_config
    from cscode.core.config import ConfigStore
    
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

    from cscode.core.config import ConfigStore
    if _db is not None:
        store = ConfigStore(_db)
        await store.save(config_data)

    config_data.pop("api_key", None)
    return {"status": "saved", "config": config_data}


@api_router.post("/sessions", response_model=dict[str, Any])
async def create_session(request: SessionCreateRequest) -> dict[str, Any]:
    if _session_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    session = await _session_store.create(title=request.title)
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else "",
    }


@api_router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    if _session_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    await _session_store.delete(session_id)
    return {"status": "deleted", "id": session_id}


@api_router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str) -> list[dict[str, Any]]:
    if _session_store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    msgs: list[Message] = await _session_store.get_messages(session_id)
    return [
        {
            "role": msg.role.value,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else "",
        }
        for msg in msgs
    ]


@api_router.get("/download/{filename:path}")
async def download_file(filename: str, raw: bool = False, quiet: bool = False) -> Any:
    """Serve file content (raw=true) or copy to ~/Downloads/."""
    import shutil
    import subprocess
    import platform
    from fastapi.responses import FileResponse
    from urllib.parse import quote

    file_path = OUTPUTS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        from fastapi import HTTPException
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

    downloads_dir = Path.home() / "Downloads"
    downloads_dir.mkdir(exist_ok=True)
    dest = downloads_dir / file_path.name
    try:
        shutil.copy2(file_path, dest)
        if not quiet and platform.system() == "Darwin":
            subprocess.run(["open", "-R", str(dest)], check=False)
        return {"status": "ok", "dest": str(dest), "filename": file_path.name}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


app.include_router(api_router)

# Mount outputs directory for file download
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR), check_dir=True), name="outputs")

if WEB_DIST.exists():
    # Mount assets directory at /assets FIRST - before any routes
    assets_dir = WEB_DIST / "assets"
    print(f"DEBUG: assets_dir={assets_dir}, exists={assets_dir.exists()}")
    if assets_dir.exists():
        print(f"DEBUG: assets_dir contents: {list(assets_dir.iterdir())}")
        app.mount("/assets", StaticFiles(directory=str(assets_dir), html=False, check_dir=True), name="assets")
        print("DEBUG: Assets mounted at /assets")
    
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
        print(f"DEBUG serve_static: path={path}, file_path={file_path}, exists={file_path.exists()}")
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


@app.on_event("startup")
async def startup() -> None:
    global _db, _session_store, _agent

    # Pass bundled Python path to subprocesses so they can find openpyxl etc.
    resource_dir = os.environ.get("CSCORE_RESOURCE_DIR", "")
    if resource_dir:
        python_dir = os.path.join(resource_dir, "python")
        if os.path.isdir(python_dir):
            existing = os.environ.get("PYTHONPATH", "")
            os.environ["PYTHONPATH"] = f"{python_dir}{os.pathsep}{existing}" if existing else python_dir
            print(f"DEBUG: Set PYTHONPATH for subprocesses: {python_dir}")

    _db = Database()
    await _db.init()
    _session_store = SessionStore(_db)

    # Ensure output dir and write Excel template
    os.makedirs("/tmp/cscode-outputs", exist_ok=True)
    template_path = "/tmp/cscode-outputs/xlsx_template.py"
    if not os.path.exists(template_path):
        with open(template_path, "w") as f:
            f.write(_XLSX_TEMPLATE)
        os.chmod(template_path, 0o755)

    config = load_config()
    provider = create_provider(config)
    registry = ToolRegistry()
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(BashTool())
    registry.register(GrepTool())
    registry.register(GlobTool())
    registry.register(LsTool())
    registry.register(BrowserTool())
    _agent = Agent(
        config=config,
        provider=provider,
        registry=registry,
        options=AgentOptions(
            max_tool_rounds=15,
            timeout=600.0,
            system_prompt="""You are CScode, an AI-powered coding assistant.

IMPORTANT: When a file is attached by the user, its content appears in [FILE: ...] blocks above. Use this content directly. If you need to explore the file content, use the Read tool (NOT Glob, Grep, or Ls). The file content is already provided — you do not need to search for it.

When generating .xlsx files, use a TWO-STEP approach for speed:
  Step 1 - Generate CSV: Write a .csv file via Write tool. First row must be column headers.
    Example CSV content for a test case table:
```
用例ID,用例名称,优先级,前置条件,测试步骤,预期结果
TC001,登录成功,P0,用户未登录,1.打开APP 2.输入用户名密码 3.点击登录,登录成功跳转首页
TC002,登录失败,P0,用户未登录,1.打开APP 2.输入错误密码,提示密码错误
```
  Step 2 - Convert to .xlsx: Run this Bash command:
    python3 /tmp/cscode-outputs/xlsx_template.py /tmp/cscode-outputs/data.csv --output /tmp/cscode-outputs/result.xlsx

  This is faster than writing openpyxl code from scratch. The xlsx_template.py auto-formats with headers, filter, and freeze panes.

Save ALL user-facing generated files to /tmp/cscode-outputs/. When a file is ready, output exactly ONE download link like this:
**下载链接：** /outputs/filename.ext
Do NOT output Markdown link syntax like [text](/outputs/...). Do NOT output a second "路径" line.

BROWSER AUTOMATION - When you need to interact with a real website:
1. Use browser.open to open a URL: browser action=open url=https://example.com
2. Click elements: browser action=click selector="#button-id"
3. Type text: browser action=type selector="#input-id" text="hello"
4. Press keys: browser action=press selector="body" key=Enter
5. Take screenshot: browser action=screenshot
6. Get text content: browser action=get_text selector=".content"
7. Get HTML: browser action=get_html selector=".container"
8. Wait for element: browser action=wait selector=".loading" seconds=5
9. Scroll: browser action=scroll selector=".footer"
10. Close browser: browser action=close

Example workflow for testing a website:
1. browser action=open url="https://voice.styoai.com"
2. browser action=type selector="#username" text="admin"
3. browser action=type selector="#password" text="xxx"
4. browser action=click selector="button[type=submit]"
5. browser action=get_text selector=".dashboard"

Available tools: Read, Write, Edit, Bash, Grep, Glob, Ls, Browser.

IMPORTANT: You have a browser automation tool! Use it to interact with REAL websites!
- The browser tool can open any URL, click elements, fill forms, take screenshots, etc.
- Do NOT generate local test scripts - use browser tool to test websites DIRECTLY
- Example: browser action=open url="https://voice.styoai.com" will open the real website
- If user asks to test a website, ALWAYS use browser tool, do NOT generate scripts""",
        ),
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    if _db is not None:
        await _db.close()
