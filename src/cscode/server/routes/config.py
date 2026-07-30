"""Config route handlers — configuration endpoints.

Provides /config/reference for reading the config key schema.
The main config CRUD endpoints (GET/POST/PUT /config) remain in app.py
due to deep coupling with app state globals.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/config/reference")
async def get_config_reference() -> list[dict[str, str]]:
    """P2-10: Return schema of all known config keys with types, defaults, descriptions."""
    from cscode.core.config import CONFIG_KEY_META

    return [
        {
            "key": k,
            "type": v.get("type", "string"),
            "default": v.get("default", ""),
            "description": v.get("description", ""),
        }
        for k, v in sorted(CONFIG_KEY_META.items())
    ]
