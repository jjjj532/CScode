"""P1-1: Credential System — secure credential storage with CRUD + rotation.

Provides a Credential dataclass and CredentialStore backed by SQLite.
Supports API keys, OAuth tokens, and custom credential types with
value rotation and history tracking.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from cscode.storage.db import Database
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

# ─── Valid types ─────────────────────────────────────────────────────

VALID_TYPES: frozenset[str] = frozenset({"api_key", "oauth_token", "custom"})

# ─── Credential model ────────────────────────────────────────────────


@dataclass
class Credential:
    """A stored credential (API key, OAuth token, etc.).

    Attributes:
        id: Unique identifier (auto-generated).
        name: Human-readable label.
        type: Credential type (api_key, oauth_token, custom).
        value: The secret value.
        provider: Associated provider (openai, anthropic, etc.) or "custom".
        created_at: Unix timestamp of creation.
        updated_at: Unix timestamp of last update.
        expires_at: Optional expiry timestamp.
        rotated_at: Timestamp of last rotation (None if never rotated).
        previous_value: Previous value after rotation (None after first set).
    """

    id: str
    name: str
    type: str
    value: str
    provider: str
    created_at: float = 0.0
    updated_at: float = 0.0
    expires_at: float | None = None
    rotated_at: float | None = None
    previous_value: str | None = None

    @property
    def is_expired(self) -> bool:
        """Check if the credential has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @property
    def display_value(self) -> str:
        """Masked value for display (shows prefix + mask)."""
        if len(self.value) <= 6:
            return self.value
        prefix = self.value[:4]
        return f"{prefix}{'*' * (len(self.value) - 6)}{self.value[-2:]}"


# ─── CredentialStore ─────────────────────────────────────────────────


class CredentialStore:
    """SQLite-backed credential store.

    All mutations are persisted immediately.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # ─── Create ──────────────────────────────────────────────────────

    async def create(
        self,
        name: str,
        type: str,
        value: str,
        provider: str,
        expires_at: float | None = None,
    ) -> Credential:
        """Create a new credential.

        Args:
            name: Human-readable label (must be non-empty).
            type: One of api_key, oauth_token, custom.
            value: The secret value (must be non-empty).
            provider: Provider name or "custom".
            expires_at: Optional expiry Unix timestamp.

        Returns:
            The newly created Credential.

        Raises:
            ValueError: If name/type/value are invalid.
        """
        if not name.strip():
            msg = "Credential name cannot be empty"
            raise ValueError(msg)
        if type not in VALID_TYPES:
            msg = f"Invalid credential type '{type}'. Valid: {', '.join(sorted(VALID_TYPES))}"
            raise ValueError(msg)
        if not value:
            msg = "Credential value cannot be empty"
            raise ValueError(msg)

        cred_id = f"cred_{uuid.uuid4().hex[:12]}"
        now = time.time()

        await self._db.execute(
            """INSERT INTO credentials (id, name, type, value, provider, created_at, updated_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (cred_id, name, type, value, provider, now, now, expires_at),
        )

        logger.info("Credential created: id=%s name=%s type=%s", cred_id, name, type)

        return Credential(
            id=cred_id,
            name=name,
            type=type,
            value=value,
            provider=provider,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )

    # ─── Get ─────────────────────────────────────────────────────────

    async def get(self, cred_id: str) -> Credential | None:
        """Fetch a credential by ID.

        Returns:
            The Credential if found, None otherwise.
        """
        if not cred_id:
            return None
        row = await self._db.fetchone(
            "SELECT * FROM credentials WHERE id = ?", (cred_id,),
        )
        if row is None:
            return None
        return self._row_to_credential(row)

    # ─── List ────────────────────────────────────────────────────────

    async def list(
        self,
        provider: str | None = None,
        cred_type: str | None = None,
    ) -> list[Credential]:
        """List credentials with optional filters.

        Args:
            provider: If set, filter by provider name.
            cred_type: If set, filter by credential type.

        Returns:
            List of matching Credentials (newest first).
        """
        where_clauses: list[str] = []
        params: list[Any] = []

        if provider is not None:
            where_clauses.append("provider = ?")
            params.append(provider)
        if cred_type is not None:
            where_clauses.append("type = ?")
            params.append(cred_type)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        rows = await self._db.fetchall(
            f"SELECT * FROM credentials {where_sql} ORDER BY created_at DESC",
            tuple(params),
        )
        return [self._row_to_credential(r) for r in rows]

    # ─── Update ──────────────────────────────────────────────────────

    async def update(
        self,
        cred_id: str,
        name: str | None = None,
        value: str | None = None,
        expires_at: float | None = None,
    ) -> Credential | None:
        """Update a credential's mutable fields.

        Args:
            cred_id: Credential ID.
            name: New name (None to keep unchanged).
            value: New value (None to keep unchanged).
            expires_at: New expiry (None to keep unchanged).

        Returns:
            The updated Credential, or None if not found.
        """
        existing = await self.get(cred_id)
        if existing is None:
            return None

        now = time.time()
        new_name = name if name is not None else existing.name
        new_value = value if value is not None else existing.value
        # Explicit sentinel for expires_at since None is a valid value
        new_expires = expires_at if "expires_at" in locals() and expires_at is not None else existing.expires_at
        if expires_at is ...:
            new_expires = existing.expires_at

        await self._db.execute(
            "UPDATE credentials SET name=?, value=?, expires_at=?, updated_at=? WHERE id=?",
            (new_name, new_value, new_expires, now, cred_id),
        )

        logger.info("Credential updated: id=%s", cred_id)
        return await self.get(cred_id)

    # ─── Delete ──────────────────────────────────────────────────────

    async def delete(self, cred_id: str) -> bool:
        """Delete a credential by ID.

        Returns:
            True if deleted, False if not found.
        """
        existing = await self.get(cred_id)
        if existing is None:
            return False

        await self._db.execute(
            "DELETE FROM credentials WHERE id = ?", (cred_id,),
        )
        logger.info("Credential deleted: id=%s name=%s", cred_id, existing.name)
        return True

    # ─── Rotate ──────────────────────────────────────────────────────

    async def rotate(self, cred_id: str, new_value: str) -> Credential | None:
        """Rotate a credential value, preserving the previous value.

        Args:
            cred_id: Credential ID.
            new_value: The new secret value (must differ from current).

        Returns:
            The rotated Credential, or None if not found.

        Raises:
            ValueError: If new_value equals the current value.
        """
        existing = await self.get(cred_id)
        if existing is None:
            return None
        if new_value == existing.value:
            msg = "New value must differ from current value"
            raise ValueError(msg)

        now = time.time()
        await self._db.execute(
            """UPDATE credentials
               SET value=?, previous_value=?, rotated_at=?, updated_at=?
               WHERE id=?""",
            (new_value, existing.value, now, now, cred_id),
        )

        logger.info("Credential rotated: id=%s name=%s", cred_id, existing.name)
        return await self.get(cred_id)

    # ─── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _row_to_credential(row: Any) -> Credential:
        """Convert a database row to a Credential."""
        return Credential(
            id=str(row["id"]),
            name=str(row["name"]),
            type=str(row["type"]),
            value=str(row["value"]),
            provider=str(row["provider"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            expires_at=row["expires_at"] if row["expires_at"] is not None else None,
            rotated_at=row["rotated_at"] if "rotated_at" in row.keys() and row["rotated_at"] is not None else None,
            previous_value=row["previous_value"] if "previous_value" in row.keys() else None,
        )
