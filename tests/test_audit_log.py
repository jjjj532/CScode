"""Tests for AuditLogStore — audit logging for enterprise monitoring."""

from __future__ import annotations

import json
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from cscode.server.audit_log import AuditLogStore
from cscode.storage.db import Database


@pytest.fixture
async def db() -> AsyncGenerator[Database, None]:
    tmp = Path(tempfile.mktemp(suffix=".db"))
    database = Database(str(tmp))
    await database.init()
    yield database
    await database.close()
    if tmp.exists():
        tmp.unlink()


@pytest.fixture
async def store(db: Database) -> AuditLogStore:
    return AuditLogStore(db)


class TestAuditLogStore:
    async def test_record_inserts_row(self, store: AuditLogStore) -> None:
        await store.record(
            action_type="session.create",
            resource_type="session",
            resource_id="sess_001",
        )
        rows = await store.list()
        assert len(rows) == 1
        assert rows[0]["action_type"] == "session.create"
        assert rows[0]["resource_type"] == "session"
        assert rows[0]["resource_id"] == "sess_001"

    async def test_record_with_detail(self, store: AuditLogStore) -> None:
        detail = {"provider": "openai", "model": "gpt-4"}
        await store.record(
            action_type="config.update",
            resource_type="config",
            detail=detail,
        )
        rows = await store.list()
        assert len(rows) == 1
        parsed = json.loads(rows[0]["detail"])
        assert parsed["provider"] == "openai"

    async def test_record_with_ip_and_user_agent(self, store: AuditLogStore) -> None:
        await store.record(
            action_type="session.delete",
            resource_type="session",
            resource_id="sess_002",
            ip_address="10.0.0.1",
            user_agent="CScode/1.0",
        )
        rows = await store.list()
        assert rows[0]["ip_address"] == "10.0.0.1"
        assert rows[0]["user_agent"] == "CScode/1.0"

    async def test_list_pagination(self, store: AuditLogStore) -> None:
        for i in range(10):
            await store.record(
                action_type="test",
                resource_type="test",
                resource_id=f"r_{i}",
            )
        all_rows = await store.list(limit=5)
        assert len(all_rows) == 5
        # Most recent first
        ids = [r["resource_id"] for r in all_rows]
        assert ids == [f"r_{i}" for i in range(9, 4, -1)]

    async def test_list_empty(self, store: AuditLogStore) -> None:
        rows = await store.list()
        assert rows == []

    async def test_list_offset(self, store: AuditLogStore) -> None:
        for i in range(5):
            await store.record(
                action_type="test",
                resource_type="test",
                resource_id=f"r_{i}",
            )
        page2 = await store.list(limit=2, offset=2)
        assert len(page2) == 2
        ids = [r["resource_id"] for r in page2]
        assert ids == ["r_2", "r_1"]

    async def test_record_timestamp_is_set(self, store: AuditLogStore) -> None:
        await store.record(
            action_type="test",
            resource_type="test",
        )
        rows = await store.list()
        assert rows[0]["created_at"] > 0
