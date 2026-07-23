from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

from cscode.storage.migration import Migration, MigrationRegistry
from cscode.storage.migration_runner import MigrationRunner
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


async def _noop(conn: object = None) -> None:
    """Async no-op for migration downgrade stubs."""


# Lazy-initialized registry so built-in migrations can reference functions
# defined later in this file without forward-declaration issues.
_migration_registry: MigrationRegistry | None = None


def _get_migration_registry() -> MigrationRegistry:
    global _migration_registry
    if _migration_registry is None:
        reg = MigrationRegistry()
        reg.register(Migration(1, "create sessions and messages tables", _migration_001, _noop))
        reg.register(Migration(2, "create config table", _migration_002, _noop))
        reg.register(Migration(3, "create event store tables", _migration_003, _noop))
        reg.register(Migration(4, "create context_epochs table", _migration_004, _noop))
        reg.register(Migration(5, "create expected_tasks and task_verifications", _migration_005, _noop))
        reg.register(Migration(6, "create credentials table", _migration_006, _noop))
        reg.register(Migration(7, "create shares table", _migration_007, _noop))
        reg.register(Migration(8, "create workspaces table", _migration_008, _noop))
        reg.register(Migration(9, "add event_seq to messages table", _migration_009, _noop))
        reg.register(Migration(10, "cleanup historical text.delta events", _migration_010, _noop))
        _migration_registry = reg
    return _migration_registry


class Database:
    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".config" / "cscode" / "cscode.db"
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self.conn: aiosqlite.Connection
        logger.debug("Database path: %s", db_path)

    async def init(self) -> None:
        logger.info("Database initializing: %s", self._db_path)
        self.conn = await aiosqlite.connect(str(self._db_path))
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA busy_timeout=5000")
        await self._run_migrations()

    async def _run_migrations(self) -> None:
        runner = MigrationRunner(self.conn, _get_migration_registry())
        applied = await runner.upgrade()
        if applied:
            logger.info("Applied migrations: %s", applied)

    async def close(self) -> None:
        logger.info("Database closing: %s", self._db_path)
        await self.conn.close()

    async def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        logger.debug("Query: %s", query[:80])
        cursor = await self.conn.execute(query, params)
        row = await cursor.fetchone()
        logger.debug("Result: %s", "found" if row else "none")
        return row

    async def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        logger.debug("Query: %s", query[:80])
        cursor = await self.conn.execute(query, params)
        rows = list(await cursor.fetchall())
        logger.debug("Result: %d rows", len(rows))
        return rows

    async def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        logger.debug("Execute: %s", query[:80])
        await self.conn.execute(query, params)
        try:
            await self.conn.commit()
        except BaseException as e:
            logger.warning("Rollback after execute error: %s", e)
            try:
                await self.conn.rollback()
            except Exception:
                pass
            raise


async def _migration_001(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT 'openai',
            model TEXT NOT NULL DEFAULT 'gpt-4o',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            tool_calls TEXT,
            tool_call_id TEXT,
            name TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
    """)


async def _migration_002(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            data TEXT
        )
    """)


async def _migration_003(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS event_sequences (
            aggregate_id TEXT PRIMARY KEY,
            seq INTEGER NOT NULL DEFAULT 0
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aggregate_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            type TEXT NOT NULL,
            data TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            UNIQUE(aggregate_id, seq)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events(aggregate_id, seq)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)")



async def _migration_004(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS context_epochs (
            session_id TEXT NOT NULL,
            epoch INTEGER NOT NULL,
            baseline_seq INTEGER NOT NULL,
            snapshot TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            PRIMARY KEY (session_id, epoch)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_epochs_session ON context_epochs(session_id, epoch)")


async def _migration_005(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS expected_tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            task_id     TEXT NOT NULL,
            description TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(session_id, task_id)
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS task_verifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            task_id     TEXT NOT NULL,
            tool_name   TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'UNVERIFIED',
            verified    INTEGER NOT NULL,
            evidence    TEXT NOT NULL,
            result_summary TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(session_id, task_id, tool_name)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_tv_session ON task_verifications(session_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_tv_status ON task_verifications(session_id, status)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_et_session ON expected_tasks(session_id)")


async def _migration_006(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS credentials (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            type            TEXT NOT NULL,
            value           TEXT NOT NULL,
            provider        TEXT NOT NULL,
            created_at      REAL NOT NULL,
            updated_at      REAL NOT NULL,
            expires_at      REAL,
            rotated_at      REAL,
            previous_value  TEXT
        )
    """)


async def _migration_007(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS shares (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            title       TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            expires_at  TEXT,
            is_active   INTEGER NOT NULL DEFAULT 1
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_shares_session ON shares(session_id)")


async def _migration_009(conn: aiosqlite.Connection) -> None:
    """CQRS: add event_seq to messages table for projection ordering."""
    try:
        await conn.execute("ALTER TABLE messages ADD COLUMN event_seq INTEGER")
    except Exception:
        pass  # column already exists (SQLite has no IF NOT EXISTS for ADD COLUMN)


async def _migration_010(conn: aiosqlite.Connection) -> None:
    """Cleanup: remove historical text.delta and error events that were
    persisted before PERSIST_EVENT_TYPES filtering was properly aligned with
    the SessionProjector. text.delta events are no longer written; error
    events are now handled silently by SessionProjector, but historical ones
    are cleaned up to reduce log noise and loading latency."""
    await conn.execute("DELETE FROM events WHERE type IN ('text.delta', 'error')")


async def _migration_008(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            path            TEXT NOT NULL,
            config_json     TEXT NOT NULL DEFAULT '{}',
            last_used_at    REAL NOT NULL DEFAULT 0,
            created_at      REAL NOT NULL,
            updated_at      REAL NOT NULL
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_workspaces_used ON workspaces(last_used_at DESC)")
