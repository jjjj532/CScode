"""Tests for POST /api/sessions/{session_id}/export."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_exp_"))
    return temp_dir / "test_cscode.db"


class TestSessionExportEndpoint:
    """POST /api/sessions/{session_id}/export."""

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

    def _create_session(self, client: TestClient, title: str = "Export Test") -> str:
        resp = client.post("/api/sessions", json={"title": title})
        assert resp.status_code == 200
        return str(resp.json()["id"])

    def test_export_returns_json(self) -> None:
        """Export returns JSON file download."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client, "My Exported Session")
            resp = client.post(f"/api/sessions/{sid}/export")
            assert resp.status_code == 200
            assert resp.headers.get("content-type") == "application/json"
            assert "attachment" in resp.headers.get("content-disposition", "")

    def test_export_has_session_data(self) -> None:
        """Export JSON contains session metadata."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client, "Data Check")
            resp = client.post(f"/api/sessions/{sid}/export")
            data = resp.json()
            assert data["session_id"] == sid
            assert data["title"] == "Data Check"
            assert "messages" in data
            assert isinstance(data["messages"], list)

    def test_export_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.post("/api/sessions/nonexistent-id/export")
            assert resp.status_code == 404
