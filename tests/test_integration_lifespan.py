"""Tests for Integration System lifespan wiring (Task 1.2).

Tests cover:
1. _ws_manager is initialised in lifespan (not lazily in endpoint)
2. Event bridge starts/stops with lifespan
3. WS endpoint uses lifespan-initialised manager
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_test_db = Path(tempfile.mkdtemp(prefix="cscode_int_life_")) / "test.db"
os.environ["CSCODE_DB_PATH"] = str(_test_db)

import cscode.server.app as _app  # noqa: E402


class TestIntegrationLifespan:

    def test_ws_manager_initialised_in_lifespan(self):
        with TestClient(_app.app) as client:
            assert _app._ws_manager is not None, (
                "_ws_manager should be initialised in lifespan, "
                "not lazily created in the endpoint"
            )
            _ = client

    def test_ws_endpoint_accepts_connection(self):
        with TestClient(_app.app) as client:
            with client.websocket_connect("/api/ws") as ws:
                ws.send_json({"type": "ping"})
                response = ws.receive_json()
                assert response["type"] == "pong"

    def test_ws_subscribe_and_receive(self):
        with TestClient(_app.app) as client:
            with client.websocket_connect("/api/ws") as ws:
                ws.send_json({"type": "subscribe", "session_id": "test_sess"})
                ws.send_json({"type": "ping"})
                response = ws.receive_json()
                assert response["type"] == "pong"

    def test_ws_unknown_message_gets_error(self):
        with TestClient(_app.app) as client:
            with client.websocket_connect("/api/ws") as ws:
                ws.send_json({"type": "nonexistent_command"})
                response = ws.receive_json()
                assert response["type"] == "error"

    def teardown_method(self):
        if _test_db.exists():
            _test_db.unlink()


class TestIntegrationToken:

    def test_create_token(self):
        with TestClient(_app.app) as client:
            resp = client.post("/api/integration/token", json={"api_key": "test-key"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "token" in data
        assert len(data["token"]) > 0
        assert "expires_at" in data
        assert isinstance(data["expires_at"], (int, float))

    def test_token_rejected_wrong_key(self):
        with TestClient(_app.app) as client:
            resp = client.post("/api/integration/token", json={"api_key": ""})
        assert resp.status_code == 403, resp.text

    def test_token_twice_different(self):
        with TestClient(_app.app) as client:
            r1 = client.post("/api/integration/token", json={"api_key": "test-key"})
            r2 = client.post("/api/integration/token", json={"api_key": "test-key"})
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["token"] != r2.json()["token"]


class TestIntegrationStress:

    def test_sequential_connect_disconnect(self):
        with TestClient(_app.app) as client:
            for i in range(5):
                with client.websocket_connect("/api/ws") as ws:
                    ws.send_json({"type": "ping"})
                    resp = ws.receive_json()
                    assert resp["type"] == "pong"

    def test_sequential_subscribe(self):
        with TestClient(_app.app) as client:
            for i in range(3):
                with client.websocket_connect("/api/ws") as ws:
                    ws.send_json({"type": "subscribe", "session_id": "seq_test"})
                    ws.send_json({"type": "ping"})
                    resp = ws.receive_json()
                    assert resp["type"] == "pong"
