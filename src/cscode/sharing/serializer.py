from __future__ import annotations

import json
from typing import Any

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class SessionSerializer:
    def export_json(self, session_data: dict[str, Any]) -> str:
        return json.dumps(session_data, indent=2, default=str)

    def import_json(self, data: str) -> dict[str, Any] | None:
        try:
            result: dict[str, Any] = json.loads(data)
            return result
        except json.JSONDecodeError as e:
            logger.warning("Failed to import session JSON: %s", e)
            return None
