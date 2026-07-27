"""AuditLogStore + ErrorLogStore — enterprise audit logging and error monitoring.

- AuditLogStore: Records key operations (session create/delete, config update, etc.)
- ErrorLogStore: Ingests frontend JS errors for monitoring.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from cscode.utils.logging import get_logger

if TYPE_CHECKING:
    from cscode.storage.db import Database

logger = get_logger(__name__)


class ErrorLogStore:
    """Stores frontend JavaScript errors for monitoring."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(
        self,
        message: str,
        stack: str = "",
        url: str = "",
        user_agent: str = "",
        detail: dict[str, object] | None = None,
    ) -> None:
        now = time.time()
        detail_json = json.dumps(detail or {})
        await self._db.execute(
            "INSERT INTO error_logs (created_at, message, stack, url, user_agent, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (now, message, stack, url, user_agent, detail_json),
        )
        logger.warning("Error logged: %s (url=%s)", message[:80], url)

    async def list(
        self, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        rows = await self._db.fetchall(
            "SELECT id, created_at, message, stack, url, user_agent, detail "
            "FROM error_logs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(r) for r in rows]


class AuditLogStore:
    """SQLite-backed audit log for key operations.

    Thread-safe when using aiosqlite (single connection at a time).
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(
        self,
        action_type: str,
        resource_type: str,
        resource_id: str | None = None,
        detail: dict[str, object] | None = None,
        ip_address: str = "",
        user_agent: str = "",
    ) -> None:
        """Record an audit log entry.

        Args:
            action_type: e.g. session.create, session.delete, config.update
            resource_type: e.g. session, config, tool
            resource_id: ID of the affected resource (optional).
            detail: Extra context as a dict (will be JSON-serialized).
            ip_address: Client IP address (optional).
            user_agent: Client User-Agent string (optional).
        """
        now = time.time()
        detail_json = json.dumps(detail or {})

        await self._db.execute(
            "INSERT INTO audit_logs (created_at, action_type, resource_type, resource_id, detail, ip_address, user_agent) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, action_type, resource_type, resource_id, detail_json, ip_address, user_agent),
        )
        logger.debug(
            "AuditLog: action=%s resource=%s/%s",
            action_type, resource_type, resource_id,
        )

    async def list(
        self, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List audit log entries, most recent first.

        Args:
            limit: Max rows to return (default 50).
            offset: Pagination offset (default 0).

        Returns:
            List of dicts with keys: id, created_at, action_type, resource_type,
            resource_id, detail, ip_address, user_agent.
        """
        rows = await self._db.fetchall(
            "SELECT id, created_at, action_type, resource_type, resource_id, "
            "detail, ip_address, user_agent "
            "FROM audit_logs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(r) for r in rows]
