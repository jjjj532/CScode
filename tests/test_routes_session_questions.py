"""Tests for P0-2: GET/POST /api/sessions/{session_id}/questions."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_q_"))
    return temp_dir / "test_cscode.db"


class TestSessionQuestionsEndpoints:
    """GET questions, POST reply, POST reject."""

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

    def _create_session(self, client: TestClient, title: str = "Q Test") -> str:
        resp = client.post("/api/sessions", json={"title": title})
        assert resp.status_code == 200
        return str(resp.json()["id"])

    def test_list_questions_empty(self) -> None:
        """Fresh session has no pending questions."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.get(f"/api/sessions/{sid}/questions")
            assert resp.status_code == 200
            assert resp.json() == []

    def test_reply_nonexistent_question_returns_404(self) -> None:
        """Replying to a non-existent question returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(
                f"/api/sessions/{sid}/questions/nonexistent-req/reply",
                json={"answers": ["yes"]},
            )
            assert resp.status_code == 404

    def test_reject_nonexistent_question_returns_404(self) -> None:
        """Rejecting a non-existent question returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(
                f"/api/sessions/{sid}/questions/nonexistent-req/reject",
            )
            assert resp.status_code == 404
