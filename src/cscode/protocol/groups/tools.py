"""Tool endpoint contracts — typed API shapes for tool listing.

These types define the request/response shapes for tool-related endpoints.
No FastAPI dependency — pure contract definitions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolListParams:
    """Query parameters for GET /api/tools.

    Currently no required parameters — reserved for future filtering.
    """
    pass


@dataclass(frozen=True, slots=True)
class ToolDefinitionResponse:
    """Response shape for a single tool definition in list endpoints."""

    name: str
    """Unique tool name."""
    description: str
    """Description of what the tool does."""
    input_schema: dict[str, object]
    """JSON Schema describing the expected input parameters."""
