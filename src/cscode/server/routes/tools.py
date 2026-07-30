"""Tool route handlers — tool listing endpoints.

Provides GET /tools and GET /tools/application for listing
registered application-level tools (safe, read-only tools that
bypass permission prompts).
"""

from __future__ import annotations

from fastapi import APIRouter

from cscode.core.application_tools import get_application_tools

router = APIRouter(prefix="/api")


@router.get("/tools/application")
async def list_application_tools() -> dict[str, list[str]]:
    """List all application-level tools (safe, read-only tools)."""
    return {"tools": get_application_tools()}


@router.get("/tools")
async def list_all_tools() -> dict[str, list[str]]:
    """Alias for /tools/application — list all available tools."""
    return {"tools": get_application_tools()}
