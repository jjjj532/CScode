from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    """Create a temporary directory and return a database path for testing."""
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_"))
    return temp_dir / "test_cscode.db"


def test_get_config():
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            response = client.get("/api/config")
            assert response.status_code == 200
            data = response.json()
            assert "provider" in data
            assert "model" in data
    finally:
        if db_path.exists():
            db_path.unlink()


def test_create_session():
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            response = client.post("/api/sessions", json={"title": "Test Session"})
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert data["title"] == "Test Session"
    finally:
        if db_path.exists():
            db_path.unlink()


# ---------------------------------------------------------------------------
# P1-2: Session Context API (GET /api/sessions/{id}/context)
# ---------------------------------------------------------------------------

def test_get_session_context():
    """P1-2: GET /api/sessions/{id}/context returns LLM context messages."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            # Create session
            create_resp = client.post("/api/sessions", json={"title": "CtxTest"})
            assert create_resp.status_code == 200
            sid = create_resp.json()["id"]

            # Get context
            resp = client.get(f"/api/sessions/{sid}/context")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            # Each item should have role and content
            if data:
                assert "role" in data[0]
                assert "content" in data[0]
    finally:
        if db_path.exists():
            db_path.unlink()


# ---------------------------------------------------------------------------
# P1-5: Agent/Model Switch API
# ---------------------------------------------------------------------------

def test_switch_model():
    """P1-5: POST /api/sessions/{id}/model updates session model."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            create_resp = client.post("/api/sessions", json={"title": "ModelTest"})
            assert create_resp.status_code == 200
            sid = create_resp.json()["id"]

            resp = client.post(f"/api/sessions/{sid}/model", json={"model": "gpt-4o-mini", "provider": "openai"})
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}
    finally:
        if db_path.exists():
            db_path.unlink()


def test_switch_agent():
    """P1-5: POST /api/sessions/{id}/agent updates session agent."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            create_resp = client.post("/api/sessions", json={"title": "AgentTest"})
            assert create_resp.status_code == 200
            sid = create_resp.json()["id"]

            resp = client.post(f"/api/sessions/{sid}/agent", json={"agent": "fast"})
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}
    finally:
        if db_path.exists():
            db_path.unlink()


# ---------------------------------------------------------------------------
# P1-4: Stop session cleanup
# ---------------------------------------------------------------------------

def test_stop_session_returns_ok():
    """P1-4: POST /api/sessions/{id}/stop returns ok."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            create_resp = client.post("/api/sessions", json={"title": "StopTest"})
            assert create_resp.status_code == 200
            sid = create_resp.json()["id"]

            resp = client.post(f"/api/sessions/{sid}/stop")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}
    finally:
        if db_path.exists():
            db_path.unlink()


# ---------------------------------------------------------------------------
# P1-6: Event persistence types include error
# ---------------------------------------------------------------------------

def test_persist_event_types_include_error():
    """P1-6: PERSIST_EVENT_TYPES includes 'error' for reliability."""
    from cscode.server.app import PERSIST_EVENT_TYPES
    assert "error" in PERSIST_EVENT_TYPES, "error events should be persisted"


# ---------------------------------------------------------------------------
# P1-3: Session-level SSE events endpoint
# ---------------------------------------------------------------------------

def test_session_events_sse():
    """P1-3: Sessions events SSE endpoint is registered."""
    from cscode.server.app import api_router
    paths = [p for r in api_router.routes for p in [getattr(r, 'path', '')] if p]
    assert any("events" in p and "session_id" in p for p in paths)


# ---------------------------------------------------------------------------
# P2-4: Session compact API
# ---------------------------------------------------------------------------

def test_compact_session():
    """P2-4: POST /api/sessions/{id}/compact returns ok."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            create_resp = client.post("/api/sessions", json={"title": "CompactTest"})
            assert create_resp.status_code == 200
            sid = create_resp.json()["id"]

            resp = client.post(f"/api/sessions/{sid}/compact")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
    finally:
        if db_path.exists():
            db_path.unlink()


# ---------------------------------------------------------------------------
# P2-5: File system API
# ---------------------------------------------------------------------------

def test_file_read():
    """P2-5: POST /api/files/read reads a file."""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    tmp.write("hello world")
    tmp.close()
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            resp = client.post("/api/files/read", json={"path": tmp.name})
            assert resp.status_code == 200
            data = resp.json()
            assert data["content"] == "hello world"
            assert data["size"] == 11
    finally:
        os.unlink(tmp.name)
        if db_path.exists():
            db_path.unlink()


def test_file_list():
    """P2-5: GET /api/files/list lists directory contents."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            resp = client.get("/api/files/list", params={"path": "."})
            assert resp.status_code == 200
            data = resp.json()
            assert "entries" in data
            assert data["count"] >= 0
    finally:
        if db_path.exists():
            db_path.unlink()


# ---------------------------------------------------------------------------
# P2-1: API path naming consistency — /api/session/... aliases
# ---------------------------------------------------------------------------

def _normalize_path_for_test(path: str) -> str:
    """Strip query params for path matching."""
    return path.split("?")[0]


def test_logging_middleware_logs_api_requests(caplog: pytest.LogCaptureFixture):
    """S0.1: Logging middleware records method, path, status, duration for /api/ requests."""
    import logging
    caplog.set_level(logging.INFO)
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            client.get("/api/health")
        # Find the log message matching the request
        matching = [r for r in caplog.records
                    if r.name == "cscode.server.app"
                    and "GET" in r.getMessage()
                    and "/api/health" in r.getMessage()
                    and "200" in r.getMessage()]
        assert matching, (
            f"No matching log record found.\n"
            f"Captured records ({len(caplog.records)}):\n" +
            "\n".join(f"  [{r.name}] {r.getMessage()}" for r in caplog.records)
        )
        msg = matching[0].getMessage()
        assert "ms" in msg or "duration" in msg.lower(), f"Log message missing duration: {msg}"
    finally:
        if db_path.exists():
            db_path.unlink()

def test_session_alias_list():
    """P2-1: GET /api/session behaves like /api/sessions."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            client.post("/api/sessions", json={"title": "AliasListTest"})
            resp = client.get("/api/session")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
    finally:
        if db_path.exists():
            db_path.unlink()


def test_session_alias_messages():
    """P2-1: GET /api/session/{id}/messages works."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            create_resp = client.post("/api/sessions", json={"title": "AliasMsg"})
            assert create_resp.status_code == 200
            sid = create_resp.json()["id"]

            resp = client.get(f"/api/session/{sid}/messages")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)
    finally:
        if db_path.exists():
            db_path.unlink()


def test_session_alias_stop():
    """P2-1: POST /api/session/{id}/stop works."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            create_resp = client.post("/api/sessions", json={"title": "AliasStop"})
            assert create_resp.status_code == 200
            sid = create_resp.json()["id"]

            resp = client.post(f"/api/session/{sid}/stop")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}
    finally:
        if db_path.exists():
            db_path.unlink()


def test_session_alias_context():
    """P2-1: GET /api/session/{id}/context works."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            create_resp = client.post("/api/sessions", json={"title": "AliasCtx"})
            assert create_resp.status_code == 200
            sid = create_resp.json()["id"]

            resp = client.get(f"/api/session/{sid}/context")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)
    finally:
        if db_path.exists():
            db_path.unlink()


# ---------------------------------------------------------------------------
# P2-2: Config system — MCP / Plugin config fields
# ---------------------------------------------------------------------------

def test_config_mcp_plugins_fields():
    """P2-2: ConfigRequest supports mcp_servers and plugins fields."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app, ConfigRequest
        # Verify the model schema supports the new fields
        import pydantic
        schema = ConfigRequest.model_json_schema()
        props = schema.get("properties", {})
        assert "mcp_servers" in props, "mcp_servers field missing from ConfigRequest"
        assert "plugins" in props, "plugins field missing from ConfigRequest"

        with TestClient(app) as client:
            payload = {
                "provider": "openai",
                "model": "gpt-4o",
                "mcp_servers": [
                    {"name": "fs", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem"]}
                ],
                "plugins": {
                    "enabled": ["code-reviewer", "test-engineer"],
                    "settings": {"code-reviewer": {"strict": True}}
                },
            }
            save_resp = client.post("/api/config", json=payload)
            assert save_resp.status_code == 200
            assert save_resp.json() == {"status": "ok"}

            get_resp = client.get("/api/config")
            assert get_resp.status_code == 200
            data = get_resp.json()
            assert "mcp_servers" in data
            assert isinstance(data["mcp_servers"], list)
            assert len(data["mcp_servers"]) == 1
            assert data["mcp_servers"][0]["name"] == "fs"
            assert "plugins" in data
            assert "enabled" in data["plugins"]
            assert "code-reviewer" in data["plugins"]["enabled"]
    finally:
        if db_path.exists():
            db_path.unlink()


def test_config_keybindings():
    """P2-2: ConfigRequest supports keybindings dict field."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app, ConfigRequest
        schema = ConfigRequest.model_json_schema()
        props = schema.get("properties", {})
        assert "keybindings" in props, "keybindings field missing from ConfigRequest"

        with TestClient(app) as client:
            payload = {
                "provider": "openai",
                "model": "gpt-4o",
                "keybindings": {
                    "send_message": "Enter",
                    "new_session": "Cmd+N",
                    "cancel": "Escape",
                },
            }
            save_resp = client.post("/api/config", json=payload)
            assert save_resp.status_code == 200

            get_resp = client.get("/api/config")
            assert get_resp.status_code == 200
            data = get_resp.json()
            assert "keybindings" in data
            assert data["keybindings"]["send_message"] == "Enter"
            assert data["keybindings"]["new_session"] == "Cmd+N"
    finally:
        if db_path.exists():
            db_path.unlink()


# ---------------------------------------------------------------------------
# P2-3: Permission rules API — always allow persistence
# ---------------------------------------------------------------------------

def test_permission_rules_crud():
    """P2-3: CRUD for permission rules."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            list_resp = client.get("/api/permission-rules")
            assert list_resp.status_code == 200
            assert list_resp.json() == []

            create_resp = client.post(
                "/api/permission-rules",
                json={"pattern": "read_file:*", "allow": True, "label": "Allow reading all files"},
            )
            assert create_resp.status_code == 200
            rule = create_resp.json()
            assert "id" in rule
            assert rule["pattern"] == "read_file:*"
            rule_id = rule["id"]

            list_resp = client.get("/api/permission-rules")
            assert list_resp.status_code == 200
            assert len(list_resp.json()) == 1
            assert list_resp.json()[0]["id"] == rule_id

            del_resp = client.delete(f"/api/permission-rules/{rule_id}")
            assert del_resp.status_code == 200
            assert del_resp.json() == {"status": "ok"}

            list_resp = client.get("/api/permission-rules")
            assert list_resp.status_code == 200
            assert list_resp.json() == []
    finally:
        if db_path.exists():
            db_path.unlink()
