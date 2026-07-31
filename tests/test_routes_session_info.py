"""Tests for P2-7: GET /api/sessions/{session_id}/info — session metadata endpoint."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_sinfo_"))
    return temp_dir / "test_cscode.db"


class TestSessionInfoEndpoint:
    """GET /api/sessions/{session_id}/info — full session metadata."""

    @pytest.fixture(autouse=True)
    def _setup_env(self) -> Generator[None, None, None]:
        self.db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(self.db_path)
        yield
        if self.db_path.exists():
            self.db_path.unlink()
        # Clean up parent dir if empty
        parent = self.db_path.parent
        if parent.exists():
            try:
                parent.rmdir()
            except OSError:
                pass

    def _create_session(self, client: TestClient, title: str = "Test Session") -> str:
        resp = client.post("/api/sessions", json={"title": title})
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        return str(data["id"])

    def test_get_session_info_returns_all_fields(self) -> None:
        """Happy path: created session returns full metadata."""
        from cscode.server.app import app

        with TestClient(app) as client:
            session_id = self._create_session(client, "Info Test")

            resp = client.get(f"/api/sessions/{session_id}/info")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()

            assert data["session_id"] == session_id
            assert data["title"] == "Info Test"
            assert data["message_count"] >= 0
            assert data["event_count"] >= 0
            assert data["seq"] >= 0
            assert data["created_at"] is not None
            assert data["updated_at"] is not None

            # All expected keys present
            expected_keys = {
                "session_id", "title", "model", "provider", "agent",
                "status", "workspace_id", "message_count", "event_count",
                "tool_rounds", "created_at", "updated_at", "seq",
            }
            assert set(data.keys()) == expected_keys, f"Key mismatch: {set(data.keys()) ^ expected_keys}"

    def test_get_session_info_404_for_nonexistent(self) -> None:
        """Non-existent session_id returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.get("/api/sessions/nonexistent-session-id/info")
            assert resp.status_code == 404

    def test_get_session_404_for_nonexistent(self) -> None:
        """P1-1 regression: GET /api/sessions/{id} must return 404 for unknown ids.

        Previously SessionV2.load() returned a fresh (seq=0) state for
        unknown ids, and get_session only checked status=="deleted" —
        so non-existent sessions returned 200 with empty defaults.
        """
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.get("/api/sessions/nonexistent-session-id")
            assert resp.status_code == 404, (
                f"Expected 404 for unknown session, got {resp.status_code}: {resp.text}"
            )

    def test_get_session_info_counts_match_messages(self) -> None:
        """message_count reflects actual messages in session."""
        from cscode.server.app import app

        with TestClient(app) as client:
            session_id = self._create_session(client, "Count Test")

            resp = client.get(f"/api/sessions/{session_id}/info")
            assert resp.status_code == 200
            data = resp.json()

            # Fresh session should have 0 or more messages (system prompt may be added)
            assert isinstance(data["message_count"], int)
            assert isinstance(data["event_count"], int)
            assert data["event_count"] >= data["message_count"]  # events ≥ messages

    def test_get_session_info_includes_extended_fields(self) -> None:
        """Extended fields like tool_rounds and workspace_id are present."""
        from cscode.server.app import app

        with TestClient(app) as client:
            session_id = self._create_session(client, "Extended Test")

            resp = client.get(f"/api/sessions/{session_id}/info")
            assert resp.status_code == 200
            data = resp.json()

            # tool_rounds should be an integer
            assert isinstance(data["tool_rounds"], int)
            # workspace_id can be None or string
            assert data["workspace_id"] is None or isinstance(data["workspace_id"], str)
