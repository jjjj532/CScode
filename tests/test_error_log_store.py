"""Tests for ErrorLogStore — frontend error ingestion for monitoring."""

from __future__ import annotations

import json
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from cscode.server.audit_log import ErrorLogStore
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
async def store(db: Database) -> ErrorLogStore:
    return ErrorLogStore(db)


class TestErrorLogStore:
    async def test_record_inserts_row(self, store: ErrorLogStore) -> None:
        await store.record(message="Something broke", url="http://localhost/app.js")
        rows = await store.list()
        assert len(rows) == 1
        assert rows[0]["message"] == "Something broke"
        assert rows[0]["url"] == "http://localhost/app.js"

    async def test_record_with_stack_and_detail(self, store: ErrorLogStore) -> None:
        detail: dict[str, object] = {}
        detail["lineno"] = 42
        detail["colno"] = 10
        await store.record(
            message="TypeError: null is not an object",
            stack="TypeError at line 42: null is not an object",
            url="http://localhost/app.js",
            user_agent="Mozilla/5.0",
            detail=detail,
        )
        rows = await store.list()
        assert len(rows) == 1
        assert "TypeError" in rows[0]["stack"]
        parsed = json.loads(rows[0]["detail"])
        assert parsed["lineno"] == 42
        assert rows[0]["user_agent"] == "Mozilla/5.0"

    async def test_record_empty_message(self, store: ErrorLogStore) -> None:
        await store.record(message="")
        rows = await store.list()
        assert len(rows) == 1
        assert rows[0]["message"] == ""

    async def test_list_pagination(self, store: ErrorLogStore) -> None:
        for i in range(10):
            await store.record(message=f"error_{i}")
        all_rows = await store.list(limit=5)
        assert len(all_rows) == 5
        # Most recent first
        ids = [r["message"] for r in all_rows]
        assert ids == [f"error_{i}" for i in range(9, 4, -1)]

    async def test_list_empty(self, store: ErrorLogStore) -> None:
        rows = await store.list()
        assert rows == []

    async def test_list_offset(self, store: ErrorLogStore) -> None:
        for i in range(5):
            await store.record(message=f"err_{i}")
        page2 = await store.list(limit=2, offset=2)
        assert len(page2) == 2
        ids = [r["message"] for r in page2]
        assert ids == ["err_2", "err_1"]

    async def test_record_timestamp_is_set(self, store: ErrorLogStore) -> None:
        await store.record(message="timed_error")
        rows = await store.list()
        assert rows[0]["created_at"] > 0

    async def test_default_detail_is_json_object(self, store: ErrorLogStore) -> None:
        await store.record(message="no detail")
        rows = await store.list()
        parsed = json.loads(rows[0]["detail"])
        assert isinstance(parsed, dict)
