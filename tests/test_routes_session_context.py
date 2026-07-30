"""Tests for P1-2: GET /api/sessions/{session_id}/context."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_ctx_"))
    return temp_dir / "test_cscode.db"


class TestSessionContextEndpoint:
    """GET /api/sessions/{session_id}/context."""

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

    def _create_session(self, client: TestClient, title: str = "Ctx Test") -> str:
        resp = client.post("/api/sessions", json={"title": title})
        assert resp.status_code == 200
        return str(resp.json()["id"])

    def test_context_returns_list(self) -> None:
        """Context returns a list of message dicts."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.get(f"/api/sessions/{sid}/context")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            for msg in data:
                assert "role" in msg
                assert "content" in msg

    def test_context_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.get("/api/sessions/nonexistent-id/context")
            assert resp.status_code == 404
