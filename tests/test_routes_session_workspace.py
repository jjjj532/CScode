"""Tests for P2-3/P2-4: POST /sessions/{id}/workspace and /move-workspace."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_ws_"))
    return temp_dir / "test_cscode.db"


class TestSessionWorkspaceEndpoints:
    """POST /api/sessions/{session_id}/workspace and /move-workspace."""

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

    def _create_session(self, client: TestClient, title: str = "WS Test") -> str:
        resp = client.post("/api/sessions", json={"title": title})
        assert resp.status_code == 200
        return str(resp.json()["id"])

    # --- associate workspace ---

    def test_associate_workspace(self) -> None:
        """POST workspace associates a session with a workspace."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(
                f"/api/sessions/{sid}/workspace",
                json={"workspace_id": "ws-abc"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    def test_associate_workspace_missing_id_returns_400(self) -> None:
        """POST without workspace_id returns 400."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(f"/api/sessions/{sid}/workspace", json={})
            assert resp.status_code == 400

    def test_associate_workspace_empty_id_returns_400(self) -> None:
        """POST with empty workspace_id returns 400."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(f"/api/sessions/{sid}/workspace", json={"workspace_id": ""})
            assert resp.status_code == 400

    def test_associate_workspace_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.post(
                "/api/sessions/nonexistent-id/workspace",
                json={"workspace_id": "ws-abc"},
            )
            assert resp.status_code == 404

    # --- move workspace ---

    def test_move_workspace(self) -> None:
        """POST move-workspace moves session to another workspace."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(
                f"/api/sessions/{sid}/move-workspace",
                json={"to_workspace_id": "ws-xyz"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    def test_move_workspace_missing_id_returns_400(self) -> None:
        """POST move-workspace without to_workspace_id returns 400."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(f"/api/sessions/{sid}/move-workspace", json={})
            assert resp.status_code == 400

    def test_move_workspace_empty_id_returns_400(self) -> None:
        """POST move-workspace with empty to_workspace_id returns 400."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.post(
                f"/api/sessions/{sid}/move-workspace",
                json={"to_workspace_id": ""},
            )
            assert resp.status_code == 400

    def test_move_workspace_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.post(
                "/api/sessions/nonexistent-id/move-workspace",
                json={"to_workspace_id": "ws-xyz"},
            )
            assert resp.status_code == 404
