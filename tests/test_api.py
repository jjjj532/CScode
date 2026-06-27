from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    """Create a temporary directory and return a database path for testing."""
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_"))
    return temp_dir / "test_cscode.db"


def test_get_config():
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            response = client.get("/api/config")
            assert response.status_code == 200
            data = response.json()
            assert "provider" in data
            assert "model" in data
    finally:
        if db_path.exists():
            db_path.unlink()


def test_create_session():
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        from cscode.server.app import app
        with TestClient(app) as client:
            response = client.post("/api/sessions", json={"title": "Test Session"})
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert data["title"] == "Test Session"
    finally:
        if db_path.exists():
            db_path.unlink()
