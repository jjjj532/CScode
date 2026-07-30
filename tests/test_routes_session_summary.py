"""Tests for P1-8: GET /api/sessions/{session_id}/summary."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_sum_"))
    return temp_dir / "test_cscode.db"


class TestSessionSummaryEndpoint:
    """GET /api/sessions/{session_id}/summary."""

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

    def _create_session(self, client: TestClient, title: str = "Sum Test") -> str:
        resp = client.post("/api/sessions", json={"title": title})
        assert resp.status_code == 200
        return str(resp.json()["id"])

    def test_summary_returns_dict(self) -> None:
        """Summary returns a dict with session stats."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.get(f"/api/sessions/{sid}/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, dict)

    def test_summary_has_expected_keys(self) -> None:
        """Summary contains session metadata fields."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.get(f"/api/sessions/{sid}/summary")
            assert resp.status_code == 200
            data = resp.json()
            # SessionSummary.generate() should include basic stats
            assert "session_id" in data or "total_messages" in data or "message_count" in data

    def test_summary_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.get("/api/sessions/nonexistent-id/summary")
            assert resp.status_code == 404
