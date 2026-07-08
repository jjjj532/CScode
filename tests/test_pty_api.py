"""Tests for PTY API endpoint (Task 2.1).

Tests the POST /api/pty endpoint.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_test_db = Path(tempfile.mkdtemp(prefix="cscode_pty_api_")) / "test.db"
os.environ["CSCODE_DB_PATH"] = str(_test_db)

import cscode.server.app as _app  # noqa: E402


class TestPtyApi:

    def test_pty_endpoint_exists(self):
        with TestClient(_app.app) as client:
            resp = client.post("/api/pty", json={"action": "list"})
        assert resp.status_code == 200, resp.text

    def test_pty_list_initial(self):
        with TestClient(_app.app) as client:
            resp = client.post("/api/pty", json={"action": "list"})
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_pty_create_and_exec(self):
        with TestClient(_app.app) as client:
            create_resp = client.post("/api/pty", json={
                "action": "create",
                "shell": "/bin/bash",
            })
        assert create_resp.status_code == 200, create_resp.text
        data = create_resp.json()
        assert "session_id" in data
        session_id = data["session_id"]

        exec_resp = client.post("/api/pty", json={
            "action": "exec",
            "session_id": session_id,
            "command": "echo hello_pty_test",
        })
        assert exec_resp.status_code == 200, exec_resp.text
        exec_data = exec_resp.json()
        assert "output" in exec_data
        assert "hello_pty_test" in exec_data["output"]

        client.post("/api/pty", json={
            "action": "close",
            "session_id": session_id,
        })

    def test_pty_missing_action(self):
        with TestClient(_app.app) as client:
            resp = client.post("/api/pty", json={})
        assert resp.status_code == 422, resp.text

    def test_pty_invalid_action(self):
        with TestClient(_app.app) as client:
            resp = client.post("/api/pty", json={"action": "nonexistent"})
        assert resp.status_code in (400, 422), resp.text

    def teardown_method(self):
        if _test_db.exists():
            _test_db.unlink()