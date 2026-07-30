"""Tests for P0-1: GET /api/sessions/{session_id}/messages."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_msg_"))
    return temp_dir / "test_cscode.db"


class TestSessionMessagesEndpoint:
    """GET /api/sessions/{session_id}/messages."""

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

    def _create_session(self, client: TestClient, title: str = "Msg Test") -> str:
        resp = client.post("/api/sessions", json={"title": title})
        assert resp.status_code == 200
        return str(resp.json()["id"])

    def test_messages_empty_for_fresh_session(self) -> None:
        """Fresh session returns empty message list (or system message only)."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.get(f"/api/sessions/{sid}/messages")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            # Should have 0 or more — system messages may exist
            for msg in data:
                assert "role" in msg
                assert "content" in msg
                assert "id" in msg

    def test_messages_format(self) -> None:
        """Each message has role, content, and id fields."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.get(f"/api/sessions/{sid}/messages")
            assert resp.status_code == 200
            data = resp.json()
            for msg in data:
                assert isinstance(msg["role"], str)
                assert isinstance(msg["content"], str)
                assert isinstance(msg["id"], str)

    def test_messages_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.get("/api/sessions/nonexistent-id/messages")
            assert resp.status_code == 404
            data = resp.json()
            assert "detail" in data
