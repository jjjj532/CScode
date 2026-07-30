"""Tests for P1-5: POST /sessions/{id}/model and POST /sessions/{id}/agent."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_sw_"))
    return temp_dir / "test_cscode.db"


class TestSessionSwitchEndpoints:
    """POST /api/sessions/{session_id}/model and /agent."""

    @pytest.fixture(autouse=True)
    def _setup_env(self) -> Generator[None, None, None]:
        self.db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(self.db_path)
        yield
        if self.db_path.exists():
            self.db_path.unlink()
        parent = self.db_path.parent
        if parent.exists():
            try:
                parent.rmdir()
            except OSError:
                pass

    def _create_session(self, client: TestClient, title: str = "Switch Test") -> str:
        resp = client.post("/api/sessions", json={"title": title})
        assert resp.status_code == 200
        return str(resp.json()["id"])

    # --- Model ---

    def test_switch_model(self) -> None:
        """POST model switches the session model."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(f"/api/sessions/{sid}/model", json={"model": "gpt-4"})
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    def test_switch_model_default_to_current(self) -> None:
        """POST without model keeps current."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(f"/api/sessions/{sid}/model", json={})
            assert resp.status_code == 200

    def test_switch_model_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.post("/api/sessions/nonexistent-id/model", json={"model": "gpt-4"})
            assert resp.status_code == 404

    # --- Agent ---

    def test_switch_agent(self) -> None:
        """POST agent switches the session agent."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(f"/api/sessions/{sid}/agent", json={"agent": "coder"})
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    def test_switch_agent_default_to_auto(self) -> None:
        """POST without agent defaults to 'auto'."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(f"/api/sessions/{sid}/agent", json={})
            assert resp.status_code == 200

    def test_switch_agent_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.post("/api/sessions/nonexistent-id/agent", json={"agent": "coder"})
            assert resp.status_code == 404
