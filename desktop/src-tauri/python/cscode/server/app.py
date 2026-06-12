from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

api_router = APIRouter(prefix="/api")

from cscode.core.config import load_config
from cscode.core.engine import Agent, AgentOptions
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


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


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
async def chat(request: ChatRequest) -> ChatResponse:
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

    session_id = request.session_id or str(uuid.uuid4())

    try:
        # Ensure session exists in database
        if _session_store is not None:
            session = await _session_store.get(session_id)
            if session is None:
                # Create session with config from saved config or defaults
                from cscode.core.config import ConfigStore, load_config
                config_data = None
                if _db is not None:
                    store = ConfigStore(_db)
                    saved_config = await store.get()
                    if saved_config:
                        config_data = saved_config
                
                provider = "openai"
                model = "gpt-4o"
                if config_data:
                    provider = config_data.get("provider", "openai")
                    model = config_data.get("model", "gpt-4o")
                
                print(f"DEBUG: Creating new session {session_id} with provider={provider}, model={model}")
                await _session_store.create(title="New Chat", provider=provider, model=model, session_id=session_id)
                print(f"DEBUG: Session created successfully")
        
        # Load existing messages for this session
        existing_messages = []
        if _session_store is not None:
            existing_messages = await _session_store.get_messages(session_id)
        
        # Build messages with history - Agent._run_loop already adds system prompt
        from cscode.core.messages import Message, MessageRole
        messages = list(existing_messages)
        messages.append(Message(role=MessageRole.USER, content=request.message))
        
        # Run agent with full message history (Agent._run_loop adds system prompt internally)
        response = await _agent._run_loop(messages)
        
        # Save updated messages to session
        if _session_store is not None:
            await _session_store.save_messages(session_id, messages)
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

    messages = await _session_store.get_messages(session_id)
    return [
        {
            "role": msg.role.value,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else "",
        }
        for msg in messages
    ]


app.include_router(api_router)

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
    async def test_assets():
        return {"message": "assets endpoint works"}
    
    # Serve index.html at root
    from fastapi.responses import FileResponse
    
    @app.get("/")
    async def serve_index():
        index_path = WEB_DIST / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"detail": "Not found"}
    
    # Serve other static files from web-dist
    @app.get("/{path:path}")
    async def serve_static(path: str):
        file_path = WEB_DIST / path
        print(f"DEBUG serve_static: path={path}, file_path={file_path}, exists={file_path.exists()}")
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return {"detail": "Not found"}


@app.on_event("startup")
async def startup() -> None:
    global _db, _session_store, _agent
    _db = Database()
    await _db.init()
    _session_store = SessionStore(_db)
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
    _agent = Agent(
        config=config,
        provider=provider,
        registry=registry,
        options=AgentOptions(
            system_prompt="You are CScode, an AI-powered coding assistant.",
        ),
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    if _db is not None:
        await _db.close()
