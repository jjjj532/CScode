"""Tests for POST /api/sessions/{session_id}/compact."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_cmp_"))
    return temp_dir / "test_cscode.db"


class TestSessionCompactEndpoint:
    """POST /api/sessions/{session_id}/compact."""

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

    def _create_session(self, client: TestClient, title: str = "Cmp Test") -> str:
        resp = client.post("/api/sessions", json={"title": title})
        assert resp.status_code == 200
        return str(resp.json()["id"])

    def test_compact_fresh_session(self) -> None:
        """Compacting a fresh session succeeds (no-op)."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(f"/api/sessions/{sid}/compact")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert isinstance(data["baseline_seq"], int)

    def test_compact_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.post("/api/sessions/nonexistent-id/compact")
            assert resp.status_code == 404
