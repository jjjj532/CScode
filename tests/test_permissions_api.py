"""G-7 收尾：GET /api/permission/request REST 端点（spec 偏差 #5）。

验证：待处理请求列表可经 REST 暴露，reply 三态决议生效。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from cscode.server.app import app


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CSCODE_DB_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


def test_list_pending_requests_returns_empty(client: TestClient) -> None:
    resp = client.get("/api/permission/request")
    assert resp.status_code == 200
    assert resp.json() == []


def test_reply_to_unknown_request_returns_404(client: TestClient) -> None:
    resp = client.post("/api/permission/request/nonexistent/reply", json={"mode": "once"})
    assert resp.status_code == 404


def test_reply_requires_valid_mode(client: TestClient) -> None:
    resp = client.post("/api/permission/request/xyz/reply", json={"mode": "bogus"})
    assert resp.status_code == 422


async def test_ask_then_list_then_reply_flow(client: TestClient) -> None:
    """验收标准 2：队列经 REST 可见，reply 决议后出队。"""
    from cscode.core.permission_v2 import SavedRules, SessionPermission
    from cscode.server.state import state
    from cscode.storage.db import Database

    backup_db = state.db
    backup_manager = state.permission_manager
    db = Database(":memory:")
    state.db = db  # type: ignore[assignment]
    state.permission_manager = SessionPermission(SavedRules(db))

    req_id = await state.permission_manager.ask("sess-1", "bash", "ls")

    resp = client.get("/api/permission/request")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["request_id"] == req_id
    assert body[0]["session_id"] == "sess-1"
    assert body[0]["action"] == "bash"
    assert body[0]["resource"] == "ls"

    reply = client.post(f"/api/permission/request/{req_id}/reply", json={"mode": "once"})
    assert reply.status_code == 200
    assert reply.json()["status"] == "ok"

    resp2 = client.get("/api/permission/request")
    assert resp2.json() == []

    state.db = backup_db  # type: ignore[assignment]
    state.permission_manager = backup_manager