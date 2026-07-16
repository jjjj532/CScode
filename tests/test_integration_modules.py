"""Integration tests for P0/P1 module API endpoints.

Tests cover:
  - P0-3: Session Input Inbox (/inbox)
  - P0-8: Provider Status (/providers/status)
  - P1-1: Credential CRUD (/credentials)
  - P1-4: Catalog (/catalog)
  - P1-11: Background Jobs (/jobs)
  - P0-4: File Attachments (/files/attach)
  - P1-12: Locale (/locale)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Module-level setup: set CSCODE_DB_PATH so the app lifespan initialises _db
# ---------------------------------------------------------------------------
_test_db_path = Path(tempfile.mkdtemp(prefix="cscode_integration_")) / "test.db"
os.environ["CSCODE_DB_PATH"] = str(_test_db_path)

from cscode.server.app import app  # noqa: E402 — must happen after env var

_client_instance = TestClient(app)


def setup_module() -> None:
    """Enter the TestClient context manager to trigger lifespan startup."""
    _client_instance.__enter__()


def teardown_module() -> None:
    """Exit TestClient context manager and clean up the database."""
    _client_instance.__exit__(None, None, None)
    if _test_db_path.exists():
        _test_db_path.unlink()


client = _client_instance


# ─── P0-3: Session Input Inbox ────────────────────────────────────────


class TestInputInbox:
    """Test /sessions/{id}/inbox endpoints."""

    def _create_session(self) -> str:
        resp = client.post("/api/sessions", json={"title": "inbox-test"}, headers={"Content-Type": "application/json"})
        # Session creation returns 200 (no status_code override on the endpoint)
        assert resp.status_code == 200, resp.text
        return resp.json()["id"]

    def test_get_inbox_empty(self) -> None:
        sess_id = self._create_session()
        resp = client.get(f"/api/sessions/{sess_id}/inbox")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending"] == []
        assert data["processing_id"] is None

    def test_enqueue_and_get(self) -> None:
        sess_id = self._create_session()
        resp = client.post(
            f"/api/sessions/{sess_id}/inbox",
            json={"content": "hello world"},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "hello world"

        # Verify it shows up in pending
        resp = client.get(f"/api/sessions/{sess_id}/inbox")
        assert len(resp.json()["pending"]) == 1

    def test_enqueue_empty_content(self) -> None:
        sess_id = self._create_session()
        resp = client.post(
            f"/api/sessions/{sess_id}/inbox",
            json={"content": ""},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_cancel_pending(self) -> None:
        sess_id = self._create_session()
        resp = client.post(
            f"/api/sessions/{sess_id}/inbox",
            json={"content": "cancel-me"},
            headers={"Content-Type": "application/json"},
        )
        inp_id = resp.json()["id"]

        resp = client.delete(f"/api/sessions/{sess_id}/inbox/{inp_id}")
        assert resp.status_code == 200
        assert resp.json()["cancelled"] is True

        # Verify cancelled
        resp = client.get(f"/api/sessions/{sess_id}/inbox")
        assert len(resp.json()["pending"]) == 0

    def test_clear_inbox(self) -> None:
        sess_id = self._create_session()
        client.post(f"/api/sessions/{sess_id}/inbox", json={"content": "a"}, headers={"Content-Type": "application/json"})
        client.post(f"/api/sessions/{sess_id}/inbox", json={"content": "b"}, headers={"Content-Type": "application/json"})

        resp = client.delete(f"/api/sessions/{sess_id}/inbox")
        assert resp.status_code == 204

        resp = client.get(f"/api/sessions/{sess_id}/inbox")
        assert len(resp.json()["pending"]) == 0

    def test_inbox_nonexistent_session(self) -> None:
        """Nonexistent session returns an empty inbox (not an error)."""
        resp = client.get("/api/sessions/nonexistent/inbox")
        assert resp.status_code == 200
        assert resp.json()["pending"] == []
        assert resp.json()["processing_id"] is None


# ─── P0-8: Provider Status ────────────────────────────────────────────


class TestProviderStatus:
    """Test /providers/status endpoint."""

    def test_list_all_providers(self) -> None:
        resp = client.get("/api/providers/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        assert "openai" in data["providers"]
        assert "anthropic" in data["providers"]

    def test_specific_provider(self) -> None:
        resp = client.get("/api/providers/status", params={"provider": "ollama"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "ollama"
        assert "status" in data


# ─── P1-1: Credential CRUD ────────────────────────────────────────────


class TestCredentialCRUD:
    """Test /credentials CRUD endpoints."""

    def test_create_and_list(self) -> None:
        resp = client.post("/api/credentials", json={
            "name": "test-key",
            "type": "api_key",
            "value": "sk-test123",
            "provider": "openai",
        }, headers={"Content-Type": "application/json"})
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        cred_id = resp.json()["id"]

        resp = client.get("/api/credentials")
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()]
        assert cred_id in ids

    def test_get_credential(self) -> None:
        resp = client.post("/api/credentials", json={
            "name": "get-test",
            "type": "api_key",
            "value": "sk-get-test",
            "provider": "anthropic",
        }, headers={"Content-Type": "application/json"})
        cred_id = resp.json()["id"]

        resp = client.get(f"/api/credentials/{cred_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-test"
        # Value should be masked
        assert "*" in resp.json()["display_value"]

    def test_get_not_found(self) -> None:
        resp = client.get("/api/credentials/nonexistent")
        assert resp.status_code == 404

    def test_update_credential(self) -> None:
        resp = client.post("/api/credentials", json={
            "name": "update-test",
            "type": "api_key",
            "value": "sk-old",
            "provider": "custom",
        }, headers={"Content-Type": "application/json"})
        cred_id = resp.json()["id"]

        resp = client.put(f"/api/credentials/{cred_id}", json={
            "name": "updated-name",
        }, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200

        resp = client.get(f"/api/credentials/{cred_id}")
        assert resp.json()["name"] == "updated-name"

    def test_delete_credential(self) -> None:
        resp = client.post("/api/credentials", json={
            "name": "delete-test",
            "type": "api_key",
            "value": "sk-delete",
            "provider": "custom",
        }, headers={"Content-Type": "application/json"})
        cred_id = resp.json()["id"]

        resp = client.delete(f"/api/credentials/{cred_id}")
        assert resp.status_code == 204

        resp = client.get(f"/api/credentials/{cred_id}")
        assert resp.status_code == 404

    def test_rotate_credential(self) -> None:
        resp = client.post("/api/credentials", json={
            "name": "rotate-test",
            "type": "api_key",
            "value": "sk-original",
            "provider": "custom",
        }, headers={"Content-Type": "application/json"})
        cred_id = resp.json()["id"]

        resp = client.post(f"/api/credentials/{cred_id}/rotate", json={
            "new_value": "sk-rotated",
        }, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        assert "rotated_at" in resp.json()

    def test_rotate_same_value_raises(self) -> None:
        resp = client.post("/api/credentials", json={
            "name": "rotate-same",
            "type": "api_key",
            "value": "sk-same",
            "provider": "custom",
        }, headers={"Content-Type": "application/json"})
        cred_id = resp.json()["id"]

        resp = client.post(f"/api/credentials/{cred_id}/rotate", json={
            "new_value": "sk-same",
        }, headers={"Content-Type": "application/json"})
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_filter_by_provider(self) -> None:
        client.post("/api/credentials", json={
            "name": "filter-a",
            "type": "api_key",
            "value": "sk-a",
            "provider": "provider-a",
        }, headers={"Content-Type": "application/json"})
        client.post("/api/credentials", json={
            "name": "filter-b",
            "type": "api_key",
            "value": "sk-b",
            "provider": "provider-b",
        }, headers={"Content-Type": "application/json"})

        resp = client.get("/api/credentials", params={"provider": "provider-a"})
        providers = [c["provider"] for c in resp.json()]
        assert all(p == "provider-a" for p in providers)


# ─── P1-4: Catalog ────────────────────────────────────────────────────


class TestCatalog:
    """Test /catalog endpoints."""

    def test_list_models(self) -> None:
        resp = client.get("/api/catalog/models")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        models = resp.json()
        assert len(models) > 0
        assert any(m["id"] == "gpt-4o" for m in models)

    def test_list_models_by_provider(self) -> None:
        resp = client.get("/api/catalog/models", params={"provider": "anthropic"})
        assert resp.status_code == 200
        models = resp.json()
        assert all(m["provider"] == "anthropic" for m in models)

    def test_search_models(self) -> None:
        resp = client.get("/api/catalog/models", params={"search": "claude"})
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) > 0

    def test_list_providers(self) -> None:
        resp = client.get("/api/catalog/providers")
        assert resp.status_code == 200
        providers = resp.json()
        assert any(p["id"] == "openai" for p in providers)

    def test_list_agents(self) -> None:
        resp = client.get("/api/catalog/agents")
        assert resp.status_code == 200
        agents = resp.json()
        assert any(a["id"] == "default" for a in agents)


# ─── P1-11: Background Jobs ───────────────────────────────────────────


class TestBackgroundJobs:
    """Test /jobs endpoints."""

    def test_enqueue_and_list(self) -> None:
        resp = client.post("/api/jobs", json={
            "job_type": "test-job",
            "params": {"key": "value"},
        }, headers={"Content-Type": "application/json"})
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        job_id = resp.json()["id"]

        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        ids = [j["id"] for j in resp.json()]
        assert job_id in ids

    def test_get_job(self) -> None:
        resp = client.post("/api/jobs", json={"job_type": "get-test"}, headers={"Content-Type": "application/json"})
        job_id = resp.json()["id"]

        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["job_type"] == "get-test"
        assert resp.json()["status"] == "pending"

    def test_get_job_not_found(self) -> None:
        resp = client.get("/api/jobs/nonexistent")
        assert resp.status_code == 404

    def test_cancel_job(self) -> None:
        resp = client.post("/api/jobs", json={"job_type": "cancel-test"}, headers={"Content-Type": "application/json"})
        job_id = resp.json()["id"]

        resp = client.post(f"/api/jobs/{job_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["cancelled"] is True

        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.json()["status"] == "cancelled"

    def test_filter_by_job_type(self) -> None:
        client.post("/api/jobs", json={"job_type": "type-a"}, headers={"Content-Type": "application/json"})
        client.post("/api/jobs", json={"job_type": "type-b"}, headers={"Content-Type": "application/json"})

        resp = client.get("/api/jobs", params={"job_type": "type-a"})
        types = [j["job_type"] for j in resp.json()]
        assert all(t == "type-a" for t in types)


# ─── P0-4: File Attachments ───────────────────────────────────────────


class TestFileAttachments:
    """Test /files/attach endpoint."""

    def test_attach_text_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("print('hello')\n")
            f.flush()
            path = f.name

        try:
            resp = client.post("/api/files/attach", json={"path": path})
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"].endswith(".py")
            assert data["is_text"] is True
            assert data["is_image"] is False
            assert data["size"] > 0
        finally:
            Path(path).unlink(missing_ok=True)

    def test_attach_missing_file(self) -> None:
        resp = client.post("/api/files/attach", json={"path": "/tmp/nonexistent-file-xyz-123"})
        assert resp.status_code == 404

    def test_attach_without_path(self) -> None:
        resp = client.post("/api/files/attach", json={})
        assert resp.status_code == 400


# ─── P1-12: Locale ────────────────────────────────────────────────────


class TestLocale:
    """Test /locale endpoints."""

    def test_get_locale(self) -> None:
        resp = client.get("/api/locale")
        assert resp.status_code == 200
        assert "locale" in resp.json()

    def test_set_locale(self) -> None:
        resp = client.post("/api/locale", json={"locale": "zh"}, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        assert resp.json()["locale"] == "zh"

        resp = client.post("/api/locale", json={"locale": "en"}, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        assert resp.json()["locale"] == "en"


# ─── P2-5: Sync — Event Sync ──────────────────────────────────────────


class TestSyncAPI:
    """Test /sync/events and /sync/push endpoints."""

    def test_get_sync_events_after_id(self) -> None:
        """GET /sync/events with high after_id returns empty (no events beyond)."""
        # Use after_id=999999 to ensure no events match (module-level shared DB has events from earlier tests)
        resp = client.get("/api/sync/events", params={"after_id": 999999})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_sync_events_after_sync(self) -> None:
        """GET /sync/events returns events after a session creation."""
        client.post("/api/sessions", json={"title": "sync-test"}, headers={"Content-Type": "application/json"})
        resp = client.get("/api/sync/events", params={"after_id": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["aggregate_id"] is not None
        assert data[0]["type"] is not None

    def test_push_sync_events(self) -> None:
        """POST /sync/push stores pushed events."""
        resp = client.post("/api/sync/push", json={
            "events": [
                {
                    "aggregate_id": "test_push_agg",
                    "seq": 1,
                    "type": "test.event",
                    "data": {"msg": "hello"},
                }
            ],
        }, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        assert resp.json()["pushed"] == 1

        # Verify the event was stored
        resp = client.get("/api/sync/events", params={"after_id": 0})
        matching = [e for e in resp.json() if e["aggregate_id"] == "test_push_agg"]
        assert len(matching) >= 1


# ─── P2-4: Control Plane — Workspace Move + Worktrees ──────────────────


class TestControlPlane:
    """Test /sessions/{id}/move-workspace endpoint."""

    def _create_workspace(self) -> str:
        resp = client.post("/api/workspaces", json={
            "name": "cp-test",
            "path": "/tmp/cp-test",
        }, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200, resp.text
        return resp.json()["workspace_id"]

    def _create_session(self) -> str:
        resp = client.post("/api/sessions", json={
            "title": "cp-session",
            "model": "gpt-4",
            "provider": "openai",
        }, headers={"Content-Type": "application/json"})
        # Session creation returns {"id": "...", "title": "..."}
        assert resp.status_code == 200, resp.text
        return str(resp.json()["id"])

    def test_move_workspace(self) -> None:
        """Move session from ws1 to ws2 works."""
        ws1 = self._create_workspace()
        ws2 = self._create_workspace()
        sess = self._create_session()

        resp = client.post(
            f"/api/sessions/{sess}/workspace",
            json={"workspace_id": ws1},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200, resp.text

        resp = client.post(
            f"/api/sessions/{sess}/move-workspace",
            json={"to_workspace_id": ws2},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200, resp.text

        resp1 = client.get(f"/api/workspaces/{ws1}/sessions")
        assert resp1.status_code == 200
        assert len(resp1.json()) == 0

        resp2 = client.get(f"/api/workspaces/{ws2}/sessions")
        assert resp2.status_code == 200
        session_ids = [s["session_id"] for s in resp2.json()]
        assert sess in session_ids

    def test_move_workspace_missing_to_workspace_id(self) -> None:
        """Missing to_workspace_id returns 400."""
        sess = self._create_session()
        resp = client.post(
            f"/api/sessions/{sess}/move-workspace",
            json={},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_move_workspace_not_found(self) -> None:
        """Non-existent session returns 404."""
        resp = client.post(
            "/api/sessions/nonexistent/move-workspace",
            json={"to_workspace_id": "ws-1"},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 404


class TestWorktreeAPI:
    """Test /worktrees endpoints."""

    def test_list_worktrees(self) -> None:
        """GET /worktrees returns a list (may be empty outside git repo)."""
        resp = client.get("/api/worktrees")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_create_worktree_missing_path_400(self) -> None:
        """POST /worktrees without path returns 400."""
        resp = client.post(
            "/api/worktrees",
            json={},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_delete_worktree_missing_path_400(self) -> None:
        """DELETE /worktrees without path returns 400."""
        resp = client.request("DELETE", "/api/worktrees", json={},
                              headers={"Content-Type": "application/json"})
        assert resp.status_code == 400


# ─── P2-3: Workspace Sessions ────────────────────────────────────────────


class TestWorkspaceSessions:
    """Test /workspaces/{id}/sessions endpoints."""

    def _create_workspace(self) -> str:
        resp = client.post("/api/workspaces", json={
            "name": "ws-test",
            "path": "/tmp/ws-test",
        }, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200, resp.text
        return resp.json()["workspace_id"]

    def _create_session(self) -> str:
        resp = client.post("/api/sessions", json={"title": "ws-session"}, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200, resp.text
        return resp.json()["id"]

    def test_list_sessions_empty(self) -> None:
        """New workspace has no sessions."""
        ws_id = self._create_workspace()
        resp = client.get(f"/api/workspaces/{ws_id}/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_sessions_with_session(self) -> None:
        """Workspace with associated session returns that session."""
        ws_id = self._create_workspace()
        sess_id = self._create_session()

        # Associate the session with the workspace
        resp = client.post(
            f"/api/sessions/{sess_id}/workspace",
            json={"workspace_id": ws_id},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200, resp.text

        resp = client.get(f"/api/workspaces/{ws_id}/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        session_ids = [s["session_id"] for s in data]
        assert sess_id in session_ids

    def test_list_sessions_not_found(self) -> None:
        """Non-existent workspace returns 404."""
        resp = client.get("/api/workspaces/nonexistent/sessions")
        assert resp.status_code == 404


# ─── P2-2: WebSocket endpoint ──────────────────────────────────────────────


class TestWebSocketEndpoint:

    def test_ping_pong(self) -> None:
        with client.websocket_connect("/api/ws") as ws:
            ws.send_json({"type": "ping"})
            resp = ws.receive_json()
            assert resp["type"] == "pong"

    def test_unknown_message_type(self) -> None:
        with client.websocket_connect("/api/ws") as ws:
            ws.send_json({"type": "unknown_type"})
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert "unknown" in resp.get("data", {}).get("message", "").lower()

    def test_multiple_clients(self) -> None:
        with client.websocket_connect("/api/ws") as ws1:
            with client.websocket_connect("/api/ws") as ws2:
                ws1.send_json({"type": "ping"})
                ws2.send_json({"type": "ping"})
                r1 = ws1.receive_json()
                r2 = ws2.receive_json()
                assert r1["type"] == "pong"
                assert r2["type"] == "pong"

    def test_disconnect_then_reconnect(self) -> None:
        with client.websocket_connect("/api/ws") as ws:
            ws.send_json({"type": "ping"})
            resp = ws.receive_json()
            assert resp["type"] == "pong"
        with client.websocket_connect("/api/ws") as ws2:
            ws2.send_json({"type": "ping"})
            resp = ws2.receive_json()
            assert resp["type"] == "pong"
