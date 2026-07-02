from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class Migration:
    """A single database migration with up/down functions.

    - version: monotonically increasing integer
    - description: human-readable summary
    - upgrade: async function(conn) → None
    - downgrade: async function(conn) → None (optional, can be no-op)
    """

    version: int
    description: str
    upgrade: Callable[..., Awaitable[None]]
    downgrade: Callable[..., Awaitable[None]]


class MigrationRegistry:
    """Collects and orders migrations by version."""

    def __init__(self) -> None:
        self._migrations: dict[int, Migration] = {}

    def register(self, migration: Migration) -> None:
        if migration.version in self._migrations:
            raise ValueError(
                f"Migration version {migration.version} already registered"
            )
        self._migrations[migration.version] = migration
        logger.debug("Registered migration v%d: %s", migration.version, migration.description)

    def get(self, version: int) -> Migration | None:
        return self._migrations.get(version)

    def sorted(self) -> list[Migration]:
        return [self._migrations[v] for v in sorted(self._migrations)]

    def latest_version(self) -> int:
        return max(self._migrations, default=0)

    def __len__(self) -> int:
        return len(self._migrations)
