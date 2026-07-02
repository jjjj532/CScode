"""ToolOutputStore — persist and retrieve tool execution outputs.

Provides both the in-memory backend (ToolOutputStore) and the LLM-facing
tool (OutputStoreTool) for saving, retrieving, and listing outputs.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from cscode.tools2.base import Tool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

Action = Literal["save", "get", "list"]


class OutputStoreInput(BaseModel):
    action: Action = Field(..., description="Action: save, get, or list")
    key: str | None = Field(None, description="Output key (required for save/get)")
    data: Any = Field(None, description="Data to save (required for save action)")
    session_id: str | None = Field(None, description="Optional session scope")


# In-memory backend
_STORE: dict[str, dict[str, Any]] = {}


class ToolOutputStore:
    """In-memory tool output backend.

    In production this would be backed by SQLite (via the session store)
    or a similar persistent store.
    """

    def save(self, key: str, data: Any, session_id: str | None = None) -> None:
        full_key = f"{session_id}:{key}" if session_id else key
        _STORE[full_key] = {
            "data": data,
            "saved_at": time.time(),
            "session_id": session_id,
        }

    def get(self, key: str, session_id: str | None = None) -> dict[str, Any] | None:
        full_key = f"{session_id}:{key}" if session_id else key
        entry = _STORE.get(full_key)
        if entry is None:
            # Also try without session prefix
            entry = _STORE.get(key)
        return entry

    def list_keys(self, session_id: str | None = None) -> list[str]:
        if session_id:
            prefix = f"{session_id}:"
            return [k.split(":", 1)[1] for k in _STORE if k.startswith(prefix)]
        return list(_STORE.keys())

    def clear(self) -> None:
        _STORE.clear()


class OutputStoreOutput(BaseModel):
    """Flexible output model for output store actions (save/get/list)."""
    status: str = ""
    key: str = ""
    data: Any = None
    keys: list[str] = []


class OutputStoreTool(Tool[OutputStoreInput, OutputStoreOutput]):
    """Persist and retrieve tool execution outputs."""

    name: str = "output_store"
    description: str = "Save, retrieve, or list tool execution outputs. Use 'save' to persist a result, 'get' to retrieve by key, 'list' to see all keys."
    input_schema: type[OutputStoreInput] = OutputStoreInput
    output_schema: type[OutputStoreOutput] = OutputStoreOutput

    def __init__(self) -> None:
        super().__init__()
        self._backend = ToolOutputStore()

    async def execute(self, input: OutputStoreInput) -> ToolResult[OutputStoreOutput]:
        if input.action == "save":
            if not input.key:
                return ToolResult(success=False, error="key required for save")
            self._backend.save(input.key, input.data, input.session_id)
            return ToolResult(success=True, data=OutputStoreOutput(status="saved", key=input.key))

        elif input.action == "get":
            if not input.key:
                return ToolResult(success=False, error="key required for get")
            entry = self._backend.get(input.key, input.session_id)
            if entry is None:
                return ToolResult(success=False, error=f"Key '{input.key}' not found")
            return ToolResult(success=True, data=OutputStoreOutput(key=input.key, data=entry["data"]))

        elif input.action == "list":
            keys = self._backend.list_keys(input.session_id)
            return ToolResult(success=True, data=OutputStoreOutput(keys=keys))

        return ToolResult(success=False, error=f"Unknown action: {input.action}")
