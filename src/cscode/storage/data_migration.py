from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

from cscode.storage.migration import Migration


class DataMigration(ABC):
    """Base class for data migrations (Python-scripted transforms).

    Subclasses must set class-level `version` and `description`, and
    implement `upgrade()`.
    """

    version: int
    description: str = ""

    @abstractmethod
    async def upgrade(self, conn: aiosqlite.Connection) -> None:
        """Apply the data transformation."""
        ...

    async def downgrade(self, conn: aiosqlite.Connection) -> None:
        """Reverse the data transformation (optional, default no-op)."""

    def to_migration(self) -> Migration:
        return Migration(
            version=self.version,
            description=self.description or f"Data migration v{self.version}",
            upgrade=self.upgrade,
            downgrade=self.downgrade,
        )
