from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class ShareManager:
    def __init__(self) -> None:
        self._shares: dict[str, dict[str, Any]] = {}

    def create_share(self, session_id: str, title: str = "", public: bool = True) -> dict[str, Any]:
        share_id = str(uuid.uuid4())
        share = {
            "share_id": share_id,
            "session_id": session_id,
            "title": title,
            "public": public,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "views": 0,
        }
        self._shares[share_id] = share
        logger.info("Created share %s for session %s", share_id, session_id)
        return share

    def get_share(self, share_id: str) -> dict[str, Any] | None:
        return self._shares.get(share_id)

    def delete_share(self, share_id: str) -> bool:
        if share_id in self._shares:
            del self._shares[share_id]
            return True
        return False

    def list_shares(self) -> list[dict[str, Any]]:
        return list(self._shares.values())

    def set_visibility(self, share_id: str, public: bool) -> bool:
        share = self._shares.get(share_id)
        if share is None:
            return False
        share["public"] = public
        return True
