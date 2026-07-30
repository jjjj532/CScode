"""CScode Protocol Layer — API contract definitions.

This layer sits between schema (pure types) and server/routes (FastAPI).
It defines the request/response shapes for all API endpoints without
depending on FastAPI, Starlette, or any web framework.

Dependency order: schema → protocol → server/routes
"""

from __future__ import annotations

from cscode.protocol.errors import ErrorDetail, ErrorResponse
from cscode.protocol.groups.config import (
    ConfigItem,
    ConfigReferenceItem,
    ConfigResponse,
    ConfigUpdateRequest,
)
from cscode.protocol.groups.sessions import (
    CreateSessionRequest,
    RunStateRequest,
    RunStateResponse,
    SessionListParams,
    SessionResponse,
)
from cscode.protocol.groups.tools import (
    ToolDefinitionResponse,
    ToolListParams,
)

__all__ = [
    "ErrorDetail",
    "ErrorResponse",
    # sessions
    "SessionListParams",
    "CreateSessionRequest",
    "SessionResponse",
    "RunStateRequest",
    "RunStateResponse",
    # tools
    "ToolListParams",
    "ToolDefinitionResponse",
    # config
    "ConfigItem",
    "ConfigResponse",
    "ConfigUpdateRequest",
    "ConfigReferenceItem",
]
