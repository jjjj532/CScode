from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class RemoteConfigLoader:
    @staticmethod
    def parse_config(data: dict[str, Any]) -> dict[str, Any]:
        return dict(data)

    @staticmethod
    def load_from_file(path: str) -> dict[str, Any]:
        try:
            p = Path(path)
            if not p.exists():
                return {}
            return dict(json.loads(p.read_text()))
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning("Failed to load remote config: %s", e)
            return {}
