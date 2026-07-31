"""Tool route handlers — tool listing endpoints.

Provides GET /tools (full registered tool registry) and
GET /tools/application (safe, read-only tools that bypass
permission prompts).
"""

from __future__ import annotations

from fastapi import APIRouter

from cscode.core.application_tools import get_application_tools
from cscode.server.state import state

router = APIRouter(prefix="/api")


@router.get("/tools/application")
async def list_application_tools() -> dict[str, list[str]]:
    """List all application-level tools (safe, read-only tools)."""
    return {"tools": get_application_tools()}


@router.get("/tools")
async def list_all_tools() -> dict[str, list[str]]:
    """List all available tools from the full tool registry."""
    registry = state.tool_registry
    if registry is not None:
        tools = registry.list_tools()
        if tools:
            return {"tools": tools}
    return {"tools": get_application_tools()}
