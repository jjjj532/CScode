from __future__ import annotations

from pathlib import Path

import aiosqlite


class Database:
    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".config" / "cscode" / "cscode.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = Path(db_path)
        self.conn: aiosqlite.Connection

    async def init(self) -> None:
        self.conn = await aiosqlite.connect(str(self._db_path))
        self.conn.row_factory = aiosqlite.Row
        await self._run_migrations()

    async def _run_migrations(self) -> None:
        async with self.conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
        ):
            pass
        cursor = await self.conn.execute("SELECT MAX(version) FROM schema_version")
        row = await cursor.fetchone()
        current_version = row[0] if row[0] is not None else 0

        migrations = [_migration_001, _migration_002]
        for i, migration in enumerate(migrations, start=1):
            if i > current_version:
                await migration(self.conn)
                await self.conn.execute("INSERT INTO schema_version (version) VALUES (?)", (i,))
        await self.conn.commit()

    async def close(self) -> None:
        await self.conn.close()

    async def fetchone(self, query: str, params: tuple = ()) -> aiosqlite.Row | None:
        cursor = await self.conn.execute(query, params)
        return await cursor.fetchone()

    async def execute(self, query: str, params: tuple = ()) -> None:
        await self.conn.execute(query, params)
        await self.conn.commit()


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
