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


def test_put_config_partial_update_preserves_unprovided_fields():
    """P0-2 regression: PUT /api/config must merge, not replace.

    Previously PUT aliased POST (save_config) which ran model_dump()
    with ALL defaults — so a partial update like {"temperature": 0.1}
    reset model→gpt-4o, api_base→None, provider→openai, etc.
    """
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            seed = {
                "provider": "scnet",
                "model": "MiniMax-M2.5",
                "api_base": "https://api.scnet.cn/api/llm/v1",
                "temperature": 0.7,
            }
            resp = client.post("/api/config", json=seed)
            assert resp.status_code == 200, resp.text

            resp = client.put("/api/config", json={"temperature": 0.1})
            assert resp.status_code == 200, resp.text

            data = client.get("/api/config").json()
            assert data["temperature"] == 0.1
            assert data["model"] == "MiniMax-M2.5", (
                f"model was reset by partial PUT: {data.get('model')}"
            )
            assert data["provider"] == "scnet", (
                f"provider was reset by partial PUT: {data.get('provider')}"
            )
            assert data["api_base"] == "https://api.scnet.cn/api/llm/v1", (
                f"api_base was reset by partial PUT: {data.get('api_base')}"
            )
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


def test_persist_event_types_excludes_text_delta():
    """P1-5: text.delta is NOT persisted — streaming deltas are real-time via SSE.
    text.ended (final complete text) is persisted for session history replay."""
    from cscode.server.app import PERSIST_EVENT_TYPES
    assert "text.delta" not in PERSIST_EVENT_TYPES, "text.delta excluded to avoid DB bloat (P1-5)"


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
                json={"action": "read", "resource": "*", "effect": "allow"},
            )
            assert create_resp.status_code == 200
            rule = create_resp.json()
            assert "id" in rule
            assert rule["action"] == "read"
            assert rule["effect"] == "allow"
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


def test_permission_rules_update():
    """P2-3: Update (PUT) a permission rule."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            create_resp = client.post(
                "/api/permission-rules",
                json={"action": "read", "resource": "*", "effect": "allow"},
            )
            assert create_resp.status_code == 200
            rule_id = create_resp.json()["id"]

            upd_resp = client.put(
                f"/api/permission-rules/{rule_id}",
                json={"action": "write"},
            )
            assert upd_resp.status_code == 200
            assert upd_resp.json()["action"] == "write"
            assert upd_resp.json()["resource"] == "*"
            assert upd_resp.json()["effect"] == "allow"

            upd_resp = client.put(
                f"/api/permission-rules/{rule_id}",
                json={"effect": "deny"},
            )
            assert upd_resp.status_code == 200
            assert upd_resp.json()["effect"] == "deny"
            assert upd_resp.json()["action"] == "write"

            upd_resp = client.put(
                f"/api/permission-rules/{rule_id}",
                json={"resource": "/tmp/*"},
            )
            assert upd_resp.status_code == 200
            assert upd_resp.json()["resource"] == "/tmp/*"

            upd_resp = client.put(
                f"/api/permission-rules/{rule_id}",
                json={"action": "bash", "resource": "*", "effect": "deny"},
            )
            assert upd_resp.status_code == 200
            assert upd_resp.json()["action"] == "bash"
            assert upd_resp.json()["resource"] == "*"
            assert upd_resp.json()["effect"] == "deny"

            upd_resp = client.put(
                "/api/permission-rules/99999",
                json={"action": "read"},
            )
            assert upd_resp.status_code == 404
    finally:
        if db_path.exists():
            db_path.unlink()


def test_catalog_agents_includes_registry_builtins():
    """AgentRegistry built-in agents should appear in /catalog/agents."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            resp = client.get("/api/catalog/agents")
            assert resp.status_code == 200
            agents = resp.json()
            names = {a["name"] for a in agents}
            assert "Default Agent" in names
            registry_ids = {"build", "plan", "subagent"}
            agent_ids = {a["id"] for a in agents}
            assert len(registry_ids & agent_ids) >= 1
    finally:
        if db_path.exists():
            db_path.unlink()


# ═══════════════════════════════════════════════════════════════════
# P2-3: Workspace CRUD API tests
# ═══════════════════════════════════════════════════════════════════


class TestWorkspaceAPI:
    """Tests for workspace CRUD endpoints."""

    def test_list_workspaces_empty(self):
        """GET /api/workspaces returns empty list when none exist."""
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app
            with TestClient(app) as client:
                resp = client.get("/api/workspaces")
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_create_and_get_workspace(self):
        """POST then GET /api/workspaces returns the created workspace."""
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app
            with TestClient(app) as client:
                create_resp = client.post(
                    "/api/workspaces",
                    json={"name": "My Project", "path": "/home/user/project"},
                )
                assert create_resp.status_code == 200
                data = create_resp.json()
                assert data["name"] == "My Project"
                assert data["path"] == "/home/user/project"
                assert "workspace_id" in data

                ws_id = data["workspace_id"]
                get_resp = client.get(f"/api/workspaces/{ws_id}")
                assert get_resp.status_code == 200
                assert get_resp.json()["name"] == "My Project"
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_create_with_config(self):
        """POST /api/workspaces with config stores the config."""
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app
            with TestClient(app) as client:
                config = {"provider": "anthropic", "model": "claude-3"}
                resp = client.post(
                    "/api/workspaces",
                    json={"name": "Config Test", "path": "/tmp/cfg", "config": config},
                )
                assert resp.status_code == 200
                assert resp.json()["config"] == config
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_update_workspace(self):
        """PUT /api/workspaces/{id} updates workspace fields."""
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app
            with TestClient(app) as client:
                create_resp = client.post(
                    "/api/workspaces",
                    json={"name": "Old Name", "path": "/tmp/old"},
                )
                ws_id = create_resp.json()["workspace_id"]

                update_resp = client.put(
                    f"/api/workspaces/{ws_id}",
                    json={"name": "New Name", "path": "/tmp/new"},
                )
                assert update_resp.status_code == 200
                assert update_resp.json()["name"] == "New Name"
                assert update_resp.json()["path"] == "/tmp/new"
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_delete_workspace(self):
        """DELETE /api/workspaces/{id} removes the workspace."""
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app
            with TestClient(app) as client:
                create_resp = client.post(
                    "/api/workspaces",
                    json={"name": "To Delete", "path": "/tmp/delete"},
                )
                ws_id = create_resp.json()["workspace_id"]

                del_resp = client.delete(f"/api/workspaces/{ws_id}")
                assert del_resp.status_code == 204

                get_resp = client.get(f"/api/workspaces/{ws_id}")
                assert get_resp.status_code == 404
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_get_nonexistent(self):
        """GET /api/workspaces/{id} returns 404 for unknown id."""
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app
            with TestClient(app) as client:
                resp = client.get("/api/workspaces/nonexistent")
                assert resp.status_code == 404
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_create_empty_name(self):
        """POST /api/workspaces with empty name returns 400."""
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app
            with TestClient(app) as client:
                resp = client.post(
                    "/api/workspaces",
                    json={"name": "", "path": "/tmp/test"},
                )
                assert resp.status_code == 400
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_recent_workspaces(self):
        """GET /api/workspaces/recent returns ordered workspaces."""
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app
            with TestClient(app) as client:
                ws1 = client.post("/api/workspaces", json={"name": "A", "path": "/tmp/a"}).json()
                ws2 = client.post("/api/workspaces", json={"name": "B", "path": "/tmp/b"}).json()

                # Use ws1 then ws2 (ws2 should be most recent)
                client.get(f"/api/workspaces/{ws1['workspace_id']}")
                client.get(f"/api/workspaces/{ws2['workspace_id']}")

                recent = client.get("/api/workspaces/recent").json()
                assert len(recent) >= 2
                assert recent[0]["workspace_id"] == ws2["workspace_id"]
        finally:
            if db_path.exists():
                db_path.unlink()


# ---------------------------------------------------------------------------
# P1-1 / P1-2: Share API (double prefix + db init)
# ---------------------------------------------------------------------------

def test_share_list():
    """P1-1: GET /api/share returns 200 after fixing double-prefix bug."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            resp = client.get("/api/share")
            # Before fix: 404 (double prefix /api/api/share)
            # After fix: 200
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)
    finally:
        if db_path.exists():
            db_path.unlink()


def test_share_create():
    """P1-2: POST /api/share creates a share (no AttributeError from uninit db)."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            # Create a session first
            sess_resp = client.post("/api/sessions", json={"title": "ShareTest"})
            assert sess_resp.status_code == 200, f"Session create failed: {sess_resp.text}"
            sid = sess_resp.json()["id"]

            # Create share
            resp = client.post("/api/share", json={"session_id": sid, "title": "My Share"})
            # Before fix: 404 (double prefix) or 500 (AttributeError)
            # After fix: 201 or 200
            assert resp.status_code in (200, 201), f"Share create failed: {resp.status_code} {resp.text}"
            data = resp.json()
            assert "id" in data
    finally:
        if db_path.exists():
            db_path.unlink()


def test_share_get():
    """P1-2: GET /api/share/{id} returns share details."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            sess_resp = client.post("/api/sessions", json={"title": "GetTest"})
            assert sess_resp.status_code == 200
            sid = sess_resp.json()["id"]

            create_resp = client.post("/api/share", json={"session_id": sid})
            assert create_resp.status_code in (200, 201)
            share_id = create_resp.json()["id"]

            resp = client.get(f"/api/share/{share_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == share_id
            assert data["session_id"] == sid
    finally:
        if db_path.exists():
            db_path.unlink()


def test_share_delete():
    """P1-2: DELETE /api/share/{id} deletes a share."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            sess_resp = client.post("/api/sessions", json={"title": "DelTest"})
            assert sess_resp.status_code == 200
            sid = sess_resp.json()["id"]

            create_resp = client.post("/api/share", json={"session_id": sid})
            assert create_resp.status_code in (200, 201)
            share_id = create_resp.json()["id"]

            resp = client.delete(f"/api/share/{share_id}")
            assert resp.status_code == 204

            # Verify deleted
            get_resp = client.get(f"/api/share/{share_id}")
            assert get_resp.status_code == 404
    finally:
        if db_path.exists():
            db_path.unlink()


# ---------------------------------------------------------------------------
# P0: Non-streaming chat persists assistant responses
# ---------------------------------------------------------------------------


def test_messages_table_populated_after_chat(monkeypatch):
    """P0: Messages table must be populated via Projector after non-streaming chat."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server import app as server_app
        monkeypatch.setattr(
            server_app, "create_agent_v2",
            lambda config, tool_registry=None, permissions=None, **kwargs: _make_mock_agent("Hello from projector test"),
        )
        with TestClient(server_app.app) as client:
            sess = client.post("/api/sessions", json={"title": "ProjectorTest"}).json()
            sid = sess["id"]

            client.post("/api/chat", json={
                "message": "Hi",
                "session_id": sid,
            })

            from cscode.storage.db import Database
            db = Database(db_path=db_path)
            import anyio
            async def check_messages():
                await db.init()
                cursor = await db.conn.execute(
                    "SELECT role, content, event_seq FROM messages WHERE session_id = ? ORDER BY event_seq",
                    (sid,),
                )
                rows = await cursor.fetchall()
                await db.close()
                roles = [r["role"] for r in rows]
                assert "user" in roles, f"Expected user message in messages table, got {roles}"
                assert "assistant" in roles, f"Expected assistant message in messages table, got {roles}"
            anyio.run(check_messages)
    finally:
        if db_path.exists():
            db_path.unlink()


def test_config_does_not_expose_raw_api_key():
    """P0: GET /api/config must not expose raw api_key."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        from cscode.core.config import ConfigStore, load_config
        import anyio
        from cscode.storage.db import Database

        async def save_key():
            db = Database(db_path=db_path)
            await db.init()
            store = ConfigStore(db)
            cfg = load_config()
            cfg_dict = cfg.to_dict()
            cfg_dict["api_key"] = "sk-real-secret-key-12345"
            await store.save(cfg_dict)
            await db.close()

        anyio.run(save_key)

        with TestClient(app) as client:
            resp = client.get("/api/config")
            assert resp.status_code == 200
            data = resp.json()
            assert "api_key" not in data, f"api_key should not be exposed, got: {data.get('api_key')}"
    finally:
        if db_path.exists():
            db_path.unlink()


# ---------------------------------------------------------------------------
# P1: Deleted sessions must be filtered from GET /api/sessions
# ---------------------------------------------------------------------------


def test_list_sessions_filters_deleted():
    """P1: GET /api/sessions must not include deleted sessions."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            s1 = client.post("/api/sessions", json={"title": "KeepMe"}).json()
            s2 = client.post("/api/sessions", json={"title": "DeleteMe"}).json()

            del_resp = client.delete(f"/api/sessions/{s2['id']}")
            assert del_resp.status_code == 200

            # List sessions — s2 should be filtered out
            listed = client.get("/api/sessions").json()
            ids = [s["id"] for s in listed]
            assert s1["id"] in ids, f"Kept session should still appear: {ids}"
            assert s2["id"] not in ids, f"Deleted session should NOT appear: {ids}"
    finally:
        if db_path.exists():
            db_path.unlink()


# ---------------------------------------------------------------------------
# P1: Malformed JSON → 400, invalid session_id → 404
# ---------------------------------------------------------------------------


def test_chat_malformed_json_returns_400():
    """P1: POST /api/chat with malformed JSON must return 400, not 422."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            resp = client.post("/api/chat", content=b"not json at all", headers={"content-type": "application/json"})
            assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text[:200]}"
    finally:
        if db_path.exists():
            db_path.unlink()


def test_chat_invalid_session_id_returns_404():
    """P1: POST /api/chat with non-existent session_id must return 404."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={
                "message": "Hi", "session_id": "non-existent-id-12345",
            })
            assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text[:200]}"
    finally:
        if db_path.exists():
            db_path.unlink()


def _make_mock_agent(response_text: str = "Mock response"):
    """Create a mock agent whose run_with_messages fires on_event and returns text."""
    from cscode.schema.events import TextEnded

    class _MockAgent:
        async def run_with_messages(self, messages, on_event=None):
            if on_event is not None:
                await on_event(TextEnded(full_text=response_text))
            return response_text

    return _MockAgent()


def test_chat_persists_assistant_response(monkeypatch):
    """P0: POST /api/chat must persist assistant response in event store."""
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server import app as server_app
        monkeypatch.setattr(
            server_app, "create_agent_v2",
            lambda config, tool_registry=None, permissions=None, **kwargs: _make_mock_agent("Hello from mock"),
        )
        with TestClient(server_app.app) as client:
            sess = client.post("/api/sessions", json={"title": "PersistTest"}).json()
            sid = sess["id"]

            chat_resp = client.post("/api/chat", json={
                "message": "Say hello",
                "session_id": sid,
            })
            assert chat_resp.status_code == 200
            data = chat_resp.json()
            assert data["session_id"] == sid

            msgs = client.get(f"/api/sessions/{sid}/messages").json()
            assert len(msgs) == 2, f"Expected 2 messages (user+assistant), got {len(msgs)}: {msgs}"
            assert msgs[0]["role"] == "user"
            assert msgs[1]["role"] == "assistant"
            assert "Hello from mock" in msgs[1]["content"]

            from cscode.storage.event_store import EventStore
            from cscode.storage.db import Database
            db = Database(db_path=db_path)
            import anyio
            async def check_events():
                await db.init()
                store = EventStore(db)
                events = await store.read(sid)
                await db.close()
                types = [e.type for e in events]
                assert "prompt.admitted" in types, f"Missing prompt.admitted in {types}"
                assert "text.ended" in types, f"Missing text.ended (assistant response) in {types}"
            anyio.run(check_events)
    finally:
        if db_path.exists():
            db_path.unlink()
