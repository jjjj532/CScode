"""Tests for P2-6: GET/PUT/DELETE /api/sessions/{session_id}/instruction."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_inst_"))
    return temp_dir / "test_cscode.db"


class TestSessionInstructionEndpoint:
    """GET/PUT/DELETE /api/sessions/{session_id}/instruction."""

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

    def _create_session(self, client: TestClient, title: str = "Inst Test") -> str:
        resp = client.post("/api/sessions", json={"title": title})
        assert resp.status_code == 200
        return str(resp.json()["id"])

    # --- GET ---

    def test_get_instruction_default_empty(self) -> None:
        """Fresh session has empty instruction."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.get(f"/api/sessions/{sid}/instruction")
            assert resp.status_code == 200
            assert resp.json() == {"instruction": ""}

    def test_get_instruction_after_set(self) -> None:
        """Get returns the previously set instruction."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)

            # Set first
            put_resp = client.put(
                f"/api/sessions/{sid}/instruction",
                json={"instruction": "Be concise. Use Chinese for replies."},
            )
            assert put_resp.status_code == 200
            assert put_resp.json()["instruction"] == "Be concise. Use Chinese for replies."

            # GET and verify
            resp = client.get(f"/api/sessions/{sid}/instruction")
            assert resp.status_code == 200
            assert resp.json()["instruction"] == "Be concise. Use Chinese for replies."

    def test_get_instruction_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.get("/api/sessions/nonexistent-id/instruction")
            assert resp.status_code == 404

    # --- PUT ---

    def test_put_instruction_creates(self) -> None:
        """PUT sets instruction text."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)

            resp = client.put(
                f"/api/sessions/{sid}/instruction",
                json={"instruction": "Reply in Korean."},
            )
            assert resp.status_code == 200
            assert resp.json()["instruction"] == "Reply in Korean."

    def test_put_instruction_updates(self) -> None:
        """PUT updates an existing instruction."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)

            client.put(f"/api/sessions/{sid}/instruction", json={"instruction": "Old instruction"})
            resp = client.put(
                f"/api/sessions/{sid}/instruction",
                json={"instruction": "Updated instruction"},
            )
            assert resp.status_code == 200
            assert resp.json()["instruction"] == "Updated instruction"

    def test_put_instruction_empty_string(self) -> None:
        """PUT with empty string clears instruction."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            client.put(f"/api/sessions/{sid}/instruction", json={"instruction": "Some text"})

            resp = client.put(f"/api/sessions/{sid}/instruction", json={"instruction": ""})
            assert resp.status_code == 200
            assert resp.json()["instruction"] == ""

    def test_put_instruction_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.put(
                "/api/sessions/nonexistent-id/instruction",
                json={"instruction": "test"},
            )
            assert resp.status_code == 404

    # --- DELETE ---

    def test_delete_instruction_clears(self) -> None:
        """DELETE clears instruction, GET returns empty after."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            client.put(f"/api/sessions/{sid}/instruction", json={"instruction": "To delete"})

            del_resp = client.delete(f"/api/sessions/{sid}/instruction")
            assert del_resp.status_code == 200
            assert del_resp.json() == {"deleted": True}

            # Verify it's gone
            get_resp = client.get(f"/api/sessions/{sid}/instruction")
            assert get_resp.json() == {"instruction": ""}

    def test_delete_instruction_idempotent(self) -> None:
        """Deleting on already-clear instruction returns 200."""
        from cscode.server.app import app

        with TestClient(app) as client:
            sid = self._create_session(client)
            resp = client.delete(f"/api/sessions/{sid}/instruction")
            assert resp.status_code == 200

    def test_delete_instruction_404_for_nonexistent(self) -> None:
        """Non-existent session returns 404 on delete."""
        from cscode.server.app import app

        with TestClient(app) as client:
            resp = client.delete("/api/sessions/nonexistent-id/instruction")
            assert resp.status_code == 404
