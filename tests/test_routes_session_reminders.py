"""Tests for P2-14: GET/POST /api/sessions/{session_id}/reminders."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_rem_"))
    return temp_dir / "test_cscode.db"


class TestSessionRemindersEndpoint:
    """GET/POST /api/sessions/{session_id}/reminders."""

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

    def _create_session(self, client: TestClient, title: str = "Rem Test") -> str:
        resp = client.post("/api/sessions", json={"title": title})
        assert resp.status_code == 200
        return str(resp.json()["id"])

    # --- GET ---

    def test_list_reminders_default_empty(self) -> None:
        """Fresh session has empty reminders list."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.get(f"/api/sessions/{sid}/reminders")
            assert resp.status_code == 200
            data = resp.json()
            assert "reminders" in data
            assert data["reminders"] == []

    def test_list_reminders_after_add(self) -> None:
        """List includes reminder after adding one."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            client.post(f"/api/sessions/{sid}/reminders", json={"text": "Check tests"})
            resp = client.get(f"/api/sessions/{sid}/reminders")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["reminders"]) == 1
            assert data["reminders"][0]["text"] == "Check tests"

    def test_list_reminders_multiple(self) -> None:
        """Multiple reminders are listed in order."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            client.post(f"/api/sessions/{sid}/reminders", json={"text": "First"})
            client.post(f"/api/sessions/{sid}/reminders", json={"text": "Second"})
            resp = client.get(f"/api/sessions/{sid}/reminders")
            assert resp.status_code == 200
            data = resp.json()
            texts = [r["text"] for r in data["reminders"]]
            assert "First" in texts
            assert "Second" in texts

    def test_list_reminders_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.get("/api/sessions/nonexistent-id/reminders")
            assert resp.status_code == 404

    # --- POST ---

    def test_add_reminder_creates(self) -> None:
        """POST adds a reminder with text."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(
                f"/api/sessions/{sid}/reminders",
                json={"text": "Fix edge case"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["text"] == "Fix edge case"
            assert "id" in data

    def test_add_reminder_empty_text_returns_400(self) -> None:
        """POST with empty text returns 400."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(f"/api/sessions/{sid}/reminders", json={"text": ""})
            assert resp.status_code == 400

    def test_add_reminder_missing_text_returns_400(self) -> None:
        """POST with missing text field returns 400."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(f"/api/sessions/{sid}/reminders", json={})
            assert resp.status_code == 400

    def test_add_reminder_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.post(
                "/api/sessions/nonexistent-id/reminders",
                json={"text": "test"},
            )
            assert resp.status_code == 404
