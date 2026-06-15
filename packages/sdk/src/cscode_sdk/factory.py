from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CScodeApp:
    version: str = "0.2.10"
    config: dict[str, Any] | None = None


def create_cscode(config: dict[str, Any] | None = None) -> CScodeApp:
    """Create a CScode application instance.

    Args:
        config: Optional dictionary with configuration overrides.

    Returns:
        A CScodeApp instance with version info and config.
    """
    return CScodeApp(config=config)
