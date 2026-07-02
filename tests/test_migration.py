from __future__ import annotations

import os
import tempfile

import aiosqlite
import pytest

from cscode.storage.data_migration import DataMigration
from cscode.storage.migration import Migration, MigrationRegistry
from cscode.storage.migration_runner import MigrationRunner


def _temp_db() -> str:
    return tempfile.mktemp(suffix=".db")


async def _noop(conn: object = None) -> None:
    """Async no-op for migration downgrade stubs."""


@pytest.mark.asyncio
async def test_migration_registry_orders_by_version():
    """S0.2.1: Migrations are ordered by version number."""
    reg = MigrationRegistry()
    reg.register(Migration(2, "second", _noop, _noop))
    reg.register(Migration(1, "first", _noop, _noop))
    assert [m.version for m in reg.sorted()] == [1, 2]


@pytest.mark.asyncio
async def test_migration_registry_prevents_duplicate_version():
    """S0.2.1: Duplicate version raises ValueError."""
    reg = MigrationRegistry()
    reg.register(Migration(1, "first", _noop, _noop))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(Migration(1, "dup", _noop, _noop))


@pytest.mark.asyncio
async def test_migration_upgrade_creates_table():
    """S0.2.2: Running upgrade creates the expected schema."""
    db_path = _temp_db()
    try:
        conn = await aiosqlite.connect(db_path)

        async def up(conn):
            await conn.execute("CREATE TABLE IF NOT EXISTS test_mig (id INTEGER PRIMARY KEY, val TEXT)")

        reg = MigrationRegistry()
        reg.register(Migration(1, "create test table", up, _noop))

        runner = MigrationRunner(conn, reg)
        await runner.upgrade()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_mig'"
        )
        row = await cursor.fetchone()
        assert row is not None, "test_mig table should exist after upgrade"
        await conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_migration_downgrade_drops_table():
    """S0.2.2: Running downgrade reverses the schema change."""
    db_path = _temp_db()
    try:
        conn = await aiosqlite.connect(db_path)

        async def up(conn):
            await conn.execute("CREATE TABLE IF NOT EXISTS test_down (id INTEGER PRIMARY KEY)")

        async def down(conn):
            await conn.execute("DROP TABLE IF EXISTS test_down")

        reg = MigrationRegistry()
        reg.register(Migration(1, "test", up, down))

        runner = MigrationRunner(conn, reg)
        await runner.upgrade()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_down'"
        )
        assert await cursor.fetchone() is not None

        await runner.downgrade(0)
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_down'"
        )
        assert await cursor.fetchone() is None
        await conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_migration_idempotent():
    """S0.2.2: Running upgrade twice only applies migration once."""
    db_path = _temp_db()
    try:
        conn = await aiosqlite.connect(db_path)
        call_count = 0

        async def up(conn):
            nonlocal call_count
            call_count += 1

        reg = MigrationRegistry()
        reg.register(Migration(1, "countable", up, _noop))

        runner = MigrationRunner(conn, reg)
        await runner.upgrade()
        await runner.upgrade()
        assert call_count == 1, "Migration should only run once"
        await conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_migration_failure_rollback():
    """S0.2.2: Failed migration does not mark version as applied."""
    db_path = _temp_db()
    try:
        conn = await aiosqlite.connect(db_path)

        async def up_ok(conn):
            await conn.execute("CREATE TABLE IF NOT EXISTS pre_mig (id INTEGER PRIMARY KEY)")

        async def up_fail(conn):
            raise RuntimeError("Migration failed intentionally")

        reg = MigrationRegistry()
        reg.register(Migration(1, "good", up_ok, _noop))
        reg.register(Migration(2, "bad", up_fail, _noop))

        runner = MigrationRunner(conn, reg)
        with pytest.raises(RuntimeError, match="Migration failed intentionally"):
            await runner.upgrade()
        cursor = await conn.execute("SELECT MAX(version) FROM schema_version")
        row = await cursor.fetchone()
        assert row is not None and (row[0] or 0) == 1, (
            "Version 2 should not be recorded after failure"
        )
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pre_mig'"
        )
        assert await cursor.fetchone() is not None
        await conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_data_migration():
    """S0.2.3: Data migration can run Python code to transform existing data."""
    db_path = _temp_db()
    try:
        conn = await aiosqlite.connect(db_path)

        async def up(conn):
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS users "
                "(id INTEGER PRIMARY KEY, name TEXT, old_field TEXT)"
            )

        transform_called = False

        class RenameField(DataMigration):
            version = 2
            description = "rename old_field to new_field"

            async def upgrade(self, conn):
                nonlocal transform_called
                transform_called = True
                await conn.execute(
                    "ALTER TABLE users RENAME COLUMN old_field TO new_field"
                )

        reg = MigrationRegistry()
        reg.register(Migration(1, "create users", up, _noop))
        reg.register(RenameField().to_migration())

        runner = MigrationRunner(conn, reg)
        await runner.upgrade()
        assert transform_called, "DataMigration.upgrade() should be called"
        cursor = await conn.execute("PRAGMA table_info(users)")
        cols = {row[1] async for row in cursor}
        assert "new_field" in cols, "new_field should exist after data migration"
        assert "old_field" not in cols, "old_field should be renamed"
        await conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_migration_applied_in_order():
    """S0.2.2: Migrations are applied in version order."""
    db_path = _temp_db()
    try:
        conn = await aiosqlite.connect(db_path)
        order: list[int] = []

        async def up_1(conn):
            order.append(1)
        async def up_3(conn):
            order.append(3)
        async def up_2(conn):
            order.append(2)

        reg = MigrationRegistry()
        reg.register(Migration(3, "third", up_3, _noop))
        reg.register(Migration(1, "first", up_1, _noop))
        reg.register(Migration(2, "second", up_2, _noop))

        runner = MigrationRunner(conn, reg)
        await runner.upgrade()
        assert order == [1, 2, 3], f"Migrations applied in wrong order: {order}"
        await conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_migration_target_version():
    """S0.2.2: upgrade(target_version) only applies up to that version."""
    db_path = _temp_db()
    try:
        conn = await aiosqlite.connect(db_path)
        applied: list[int] = []

        async def up_1(conn):
            applied.append(1)
        async def up_2(conn):
            applied.append(2)
        async def up_3(conn):
            applied.append(3)

        reg = MigrationRegistry()
        reg.register(Migration(1, "one", up_1, _noop))
        reg.register(Migration(2, "two", up_2, _noop))
        reg.register(Migration(3, "three", up_3, _noop))

        runner = MigrationRunner(conn, reg)
        await runner.upgrade(target_version=2)
        assert applied == [1, 2], f"Expected only v1, v2 applied, got: {applied}"
        await conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
