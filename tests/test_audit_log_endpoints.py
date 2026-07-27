"""Tests for audit/error API endpoints — POST /api/logs/error and GET /api/audit-logs."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_test_"))
    return temp_dir / "test_cscode.db"


class TestLogErrorEndpoint:
    """POST /api/logs/error — frontend error ingestion."""

    def test_log_error_basic(self):
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app

            with TestClient(app) as client:
                resp = client.post("/api/logs/error", json={
                    "message": "Something broke",
                    "stack": "Error: Something broke\n    at app.js:42:10",
                    "url": "http://localhost/app.js",
                    "user_agent": "Mozilla/5.0",
                })
                assert resp.status_code == 200
                assert resp.json() == {"status": "ok"}
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_log_error_minimal_fields(self):
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app

            with TestClient(app) as client:
                resp = client.post("/api/logs/error", json={
                    "message": "minimal error",
                })
                assert resp.status_code == 200
                assert resp.json() == {"status": "ok"}
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_log_error_empty_message(self):
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app

            with TestClient(app) as client:
                resp = client.post("/api/logs/error", json={
                    "message": "",
                })
                assert resp.status_code == 200
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_log_error_with_detail(self):
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app

            with TestClient(app) as client:
                resp = client.post("/api/logs/error", json={
                    "message": "detailed error",
                    "detail": {"lineno": 42, "colno": 10},
                })
                assert resp.status_code == 200
        finally:
            if db_path.exists():
                db_path.unlink()


class TestAuditLogsEndpoint:
    """GET /api/audit-logs — paginated audit log listing."""

    def test_list_audit_logs_empty(self):
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app

            with TestClient(app) as client:
                resp = client.get("/api/audit-logs")
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_list_audit_logs_with_data(self):
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app

            with TestClient(app) as client:
                # Create a session — this triggers session.create audit log
                create_resp = client.post("/api/sessions", json={"title": "AuditTest"})
                assert create_resp.status_code == 200

                resp = client.get("/api/audit-logs")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data) >= 1
                assert data[0]["action_type"] == "session.create"
                assert data[0]["resource_type"] == "session"
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_list_audit_logs_pagination(self):
        db_path = _get_temp_db_path()
        os.environ["CSCODE_DB_PATH"] = str(db_path)
        try:
            from cscode.server.app import app

            with TestClient(app) as client:
                # Create 3 sessions to generate audit entries
                for i in range(3):
                    client.post("/api/sessions", json={"title": f"S{i}"})

                resp = client.get("/api/audit-logs?limit=2")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data) == 2
        finally:
            if db_path.exists():
                db_path.unlink()
