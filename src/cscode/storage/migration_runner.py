from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

from cscode.storage.migration import MigrationRegistry

logger = logging.getLogger(__name__)


class MigrationRunner:
    """Executes pending migrations with transaction support."""

    def __init__(self, conn: aiosqlite.Connection, registry: MigrationRegistry) -> None:
        self._conn = conn
        self._registry = registry

    async def _ensure_tracking_table(self) -> None:
        await self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
        )

    async def _applied_versions(self) -> set[int]:
        cursor = await self._conn.execute("SELECT version FROM schema_version")
        return {row[0] async for row in cursor}

    async def _mark_applied(self, version: int) -> None:
        await self._conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (version,)
        )

    async def _mark_unapplied(self, version: int) -> None:
        await self._conn.execute(
            "DELETE FROM schema_version WHERE version = ?", (version,)
        )

    async def upgrade(self, target_version: int | None = None) -> list[int]:
        """Apply pending migrations up to target_version (or latest)."""
        await self._ensure_tracking_table()
        applied = await self._applied_versions()
        applied_versions: list[int] = []

        for migration in self._registry.sorted():
            if target_version is not None and migration.version > target_version:
                break
            if migration.version in applied:
                logger.debug("Skipping v%d (already applied)", migration.version)
                continue
            start = time.monotonic()
            try:
                await migration.upgrade(self._conn)
                await self._mark_applied(migration.version)
                await self._conn.commit()
                elapsed = (time.monotonic() - start) * 1000
                logger.info(
                    "Migration v%d applied (%s) in %.0fms",
                    migration.version,
                    migration.description,
                    elapsed,
                )
                applied_versions.append(migration.version)
            except BaseException:
                await self._conn.rollback()
                logger.exception("Migration v%d failed, rolled back", migration.version)
                raise

        return applied_versions

    async def downgrade(self, target_version: int = 0) -> list[int]:
        """Roll back migrations to target_version."""
        await self._ensure_tracking_table()
        applied = await self._applied_versions()
        rolled_back: list[int] = []

        for migration in reversed(self._registry.sorted()):
            if migration.version <= target_version:
                break
            if migration.version not in applied:
                continue
            start = time.monotonic()
            try:
                await migration.downgrade(self._conn)
                await self._mark_unapplied(migration.version)
                await self._conn.commit()
                elapsed = (time.monotonic() - start) * 1000
                logger.info(
                    "Migration v%d rolled back (%s) in %.0fms",
                    migration.version,
                    migration.description,
                    elapsed,
                )
                rolled_back.append(migration.version)
            except BaseException:
                await self._conn.rollback()
                logger.exception(
                    "Migration v%d rollback failed, rolled back", migration.version
                )
                raise

        return rolled_back
