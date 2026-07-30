"""Tests for P2-12: GET /api/sessions/{session_id}/overflow."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_ovf_"))
    return temp_dir / "test_cscode.db"


class TestSessionOverflowEndpoint:
    """GET /api/sessions/{session_id}/overflow."""

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

    def _create_session(self, client: TestClient, title: str = "Ovf Test") -> str:
        resp = client.post("/api/sessions", json={"title": title})
        assert resp.status_code == 200
        return str(resp.json()["id"])

    def test_overflow_returns_expected_keys(self) -> None:
        """Overflow returns overflowing, near_overflow, message_count, threshold."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.get(f"/api/sessions/{sid}/overflow")
            assert resp.status_code == 200
            data = resp.json()
            assert "overflowing" in data
            assert "near_overflow" in data
            assert "message_count" in data
            assert "threshold" in data

    def test_overflow_fresh_session(self) -> None:
        """Fresh session is not overflowing."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.get(f"/api/sessions/{sid}/overflow")
            data = resp.json()
            assert data["overflowing"] is False
            assert data["near_overflow"] is False
            assert isinstance(data["message_count"], int)

    def test_overflow_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.get("/api/sessions/nonexistent-id/overflow")
            assert resp.status_code == 404
