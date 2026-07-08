"""Tests for P2-16: Tool external-directory — external directory permission registry.

Tests cover:
1. ExternalDirectoryStore: add/list/remove/check
2. API endpoints: GET /directories/external, POST, DELETE (standalone router)
3. Path approval checking (exact match, sub-path under approved dir)
4. Error cases: duplicate path, missing path param, bad id
5. Real app integration: verifies _external_dir_store global initialisation (P0-9)
"""

from __future__ import annotations

import httpx
import os
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx._transports.asgi import ASGITransport

from cscode.core.external_directory import ExternalDirectoryStore


class TestExternalDirectoryStore:
    def test_add_and_list(self) -> None:
        """After adding a dir, list returns it."""
        store = ExternalDirectoryStore()
        store.add("/Users/test/projects")
        dirs = store.list()
        assert len(dirs) == 1
        assert dirs[0].path == "/Users/test/projects"
        assert dirs[0].id is not None
        assert dirs[0].created_at > 0

    def test_add_multiple(self) -> None:
        """Multiple directories can be added."""
        store = ExternalDirectoryStore()
        store.add("/Users/test/a")
        store.add("/Users/test/b")
        assert len(store.list()) == 2

    def test_add_duplicate_path(self) -> None:
        """Adding the same path twice raises ValueError."""
        store = ExternalDirectoryStore()
        store.add("/Users/test/projects")
        with pytest.raises(ValueError, match="already registered"):
            store.add("/Users/test/projects")

    def test_remove_existing(self) -> None:
        """After removing a dir, it is no longer listed."""
        store = ExternalDirectoryStore()
        d = store.add("/Users/test/projects")
        assert store.remove(d.id) is True
        assert len(store.list()) == 0

    def test_remove_non_existent(self) -> None:
        """Removing a non-existent id returns False."""
        store = ExternalDirectoryStore()
        assert store.remove("non-existent") is False

    def test_is_approved_exact_match(self) -> None:
        """is_approved returns True for exact path match."""
        store = ExternalDirectoryStore()
        store.add("/Users/test/projects")
        assert store.is_approved("/Users/test/projects") is True

    def test_is_approved_sub_path(self) -> None:
        """is_approved returns True for paths under an approved dir."""
        store = ExternalDirectoryStore()
        store.add("/Users/test/projects")
        assert store.is_approved("/Users/test/projects/sub/file.txt") is True

    def test_is_approved_not_approved(self) -> None:
        """is_approved returns False for paths not under any approved dir."""
        store = ExternalDirectoryStore()
        store.add("/Users/test/a")
        assert store.is_approved("/Users/test/b") is False

    def test_is_approved_empty_store(self) -> None:
        """is_approved returns False when no dirs are approved."""
        store = ExternalDirectoryStore()
        assert store.is_approved("/any/path") is False

    def test_is_approved_trailing_slash(self) -> None:
        """Path matching handles trailing slashes consistently."""
        store = ExternalDirectoryStore()
        store.add("/Users/test/projects")
        assert store.is_approved("/Users/test/projects/") is True

    def test_clear(self) -> None:
        """Clear removes all directories."""
        store = ExternalDirectoryStore()
        store.add("/Users/test/a")
        store.add("/Users/test/b")
        store.clear()
        assert len(store.list()) == 0


class TestExternalDirectoryAPI:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        """Create a fresh FastAPI app with external-directory endpoints for each test."""
        from fastapi import APIRouter, HTTPException

        _store = ExternalDirectoryStore()

        router = APIRouter()

        @router.get("/api/directories/external")
        async def list_dirs() -> dict[str, list[dict[str, object]]]:
            dirs = _store.list()
            return {
                "directories": [
                    {"id": d.id, "path": d.path, "created_at": d.created_at} for d in dirs
                ]
            }

        @router.post("/api/directories/external")
        async def add_dir(body: dict[str, str]) -> dict[str, object]:
            path = body.get("path", "")
            if not path:
                raise HTTPException(status_code=400, detail="path is required")
            try:
                entry = _store.add(path)
                return {"id": entry.id, "path": entry.path, "created_at": entry.created_at}
            except ValueError as e:
                raise HTTPException(status_code=409, detail=str(e))

        @router.delete("/api/directories/external/{dir_id}")
        async def remove_dir(dir_id: str) -> dict[str, bool]:
            ok = _store.remove(dir_id)
            if not ok:
                raise HTTPException(status_code=404, detail="Directory not found")
            return {"ok": True}

        @router.get("/api/directories/external/check")
        async def check_dir(path: str = "") -> dict[str, bool]:
            approved = _store.is_approved(path)
            return {"approved": approved}

        _app = FastAPI()
        _app.include_router(router)
        self._app = _app
        self._store = _store

    async def _client(self) -> httpx.AsyncClient:
        transport = ASGITransport(app=self._app)
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_list_empty(self) -> None:
        async with await self._client() as c:
            resp = await c.get("/api/directories/external")
        assert resp.status_code == 200
        data = resp.json()
        assert data["directories"] == []

    @pytest.mark.asyncio
    async def test_add_and_list(self) -> None:
        async with await self._client() as c:
            resp = await c.post("/api/directories/external", json={"path": "/Users/test/projects"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == "/Users/test/projects"

        async with await self._client() as c:
            resp = await c.get("/api/directories/external")
        data = resp.json()
        assert len(data["directories"]) == 1
        assert data["directories"][0]["path"] == "/Users/test/projects"

    @pytest.mark.asyncio
    async def test_add_missing_path(self) -> None:
        async with await self._client() as c:
            resp = await c.post("/api/directories/external", json={})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_add_empty_path(self) -> None:
        async with await self._client() as c:
            resp = await c.post("/api/directories/external", json={"path": ""})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_add_duplicate(self) -> None:
        async with await self._client() as c:
            await c.post("/api/directories/external", json={"path": "/Users/test/projects"})
            resp = await c.post("/api/directories/external", json={"path": "/Users/test/projects"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_remove(self) -> None:
        async with await self._client() as c:
            add_resp = await c.post("/api/directories/external", json={"path": "/Users/test/projects"})
        dir_id = add_resp.json()["id"]

        async with await self._client() as c:
            resp = await c.delete(f"/api/directories/external/{dir_id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        async with await self._client() as c:
            resp = await c.get("/api/directories/external")
        assert len(resp.json()["directories"]) == 0

    @pytest.mark.asyncio
    async def test_remove_non_existent(self) -> None:
        async with await self._client() as c:
            resp = await c.delete("/api/directories/external/bad-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_check_endpoint_approved(self) -> None:
        async with await self._client() as c:
            await c.post("/api/directories/external", json={"path": "/Users/test/projects"})
            resp = await c.get("/api/directories/external/check", params={"path": "/Users/test/projects/sub/file.txt"})
        assert resp.status_code == 200
        assert resp.json()["approved"] is True

    @pytest.mark.asyncio
    async def test_check_endpoint_not_approved(self) -> None:
        async with await self._client() as c:
            await c.post("/api/directories/external", json={"path": "/Users/test/a"})
            resp = await c.get("/api/directories/external/check", params={"path": "/Users/test/b"})
        assert resp.status_code == 200
        assert resp.json()["approved"] is False


# ---------------------------------------------------------------------------
# P0-9 integration test: verifies _external_dir_store is properly initialised
# in the real app lifespan (not masked by local-variable shadowing).
# ---------------------------------------------------------------------------
_test_db_path_p0_9 = Path(tempfile.mkdtemp(prefix="cscode_external_dir_p0_9_")) / "test.db"


@pytest.fixture(scope="module")
def _real_app_client():
    """Set up the real FastAPI app with lifespan, yield a TestClient."""
    os.environ["CSCODE_DB_PATH"] = str(_test_db_path_p0_9)
    from cscode.server.app import app as _real_app

    from fastapi.testclient import TestClient

    with TestClient(_real_app) as c:
        yield c

    if _test_db_path_p0_9.exists():
        _test_db_path_p0_9.unlink()


class TestExternalDirectoryRealApp:
    """Tests against the real FastAPI app (not a standalone router).
    
    Verifies P0-9: the _external_dir_store global variable is correctly
    declared in lifespan's ``global`` statement.
    """

    def test_list_external_dirs_returns_200_not_503(self, _real_app_client):
        resp = _real_app_client.get("/api/directories/external")
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text}. "
            "This likely means _external_dir_store was not declared in "
            "lifespan()'s global statement."
        )

    def test_add_and_list_via_real_app(self, _real_app_client):
        add_resp = _real_app_client.post(
            "/api/directories/external",
            json={"path": "/tmp/test-p0-9"},
        )
        assert add_resp.status_code == 200, add_resp.text

        list_resp = _real_app_client.get("/api/directories/external")
        assert list_resp.status_code == 200
        dirs = list_resp.json()["directories"]
        paths = [d["path"] for d in dirs]
        assert "/tmp/test-p0-9" in paths

    def test_check_endpoint_via_real_app(self, _real_app_client):
        resp = _real_app_client.get(
            "/api/directories/external/check",
            params={"path": "/tmp/test-p0-9/sub"},
        )
        assert resp.status_code == 200
        assert resp.json()["approved"] is True
