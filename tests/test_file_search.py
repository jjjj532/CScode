from __future__ import annotations

from fastapi.testclient import TestClient

from cscode.server.app import app


class TestFileSearch:
    def test_file_search_returns_results(self):
        with TestClient(app) as client:
            response = client.get("/api/files/search?q=app.py")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) > 0
            assert any("app.py" in f for f in data)

    def test_file_search_no_query_returns_empty(self):
        with TestClient(app) as client:
            response = client.get("/api/files/search?q=")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_file_search_nonexistent(self):
        with TestClient(app) as client:
            response = client.get("/api/files/search?q=xyznonexistent12345")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 0

    def test_file_search_glob_pattern(self):
        with TestClient(app) as client:
            response = client.get("/api/files/search?q=*.py")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) > 0
            assert all(f.endswith(".py") for f in data)
