"""ToolOutputStore — persist and retrieve tool execution outputs.

Provides both the in-memory backend (ToolOutputStore) and the LLM-facing
tool (OutputStoreTool) for saving, retrieving, and listing outputs.
Supports bounded preview, file-backed overflow storage, and session cleanup.
"""

from __future__ import annotations

import pathlib
import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from cscode.tools2.base import Tool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

Action = Literal["save", "get", "list"]

MAX_LINES = 500
MAX_BYTES = 512 * 1024  # 512KB
RETENTION_SECONDS = 36000  # 10 hours


@dataclass
class BoundedOutput:
    """Result of storing a tool output, with preview and truncation info."""
    preview: str
    truncated: bool
    managed_path: str | None = None


class OutputStoreInput(BaseModel):
    action: Action = Field(..., description="Action: save, get, or list")
    key: str | None = Field(None, description="Output key (required for save/get)")
    data: Any = Field(None, description="Data to save (required for save action)")
    session_id: str | None = Field(None, description="Optional session scope")


# In-memory backend
_STORE: dict[str, dict[str, Any]] = {}


def _truncate_content(content: str) -> tuple[str, bool]:
    """Truncate content if it exceeds MAX_LINES or MAX_BYTES.

    Returns (preview, truncated).
    """
    preview = content
    truncated = False

    # Check line count
    lines = content.split("\n")
    if len(lines) > MAX_LINES:
        preview = "\n".join(lines[:MAX_LINES])
        truncated = True

    # Check byte size
    if len(preview.encode("utf-8")) > MAX_BYTES:
        preview = preview.encode("utf-8")[:MAX_BYTES].decode("utf-8", errors="replace")
        truncated = True

    return preview, truncated


class ToolOutputStore:
    """Tool output backend with bounded preview and optional file-backed storage.

    In-memory by default. Pass data_dir for file-backed overflow storage.
    """

    def __init__(self, data_dir: str | None = None) -> None:
        self._data_dir = data_dir

    def save(
        self,
        key: str,
        data: Any,
        session_id: str | None = None,
    ) -> BoundedOutput:
        """Store output with bounded preview.

        The original data is preserved in memory. A BoundedOutput preview
        is returned to inform the caller about truncation.
        If the output is large and data_dir is set, the full content
        is also written to disk.
        """
        content = str(data) if not isinstance(data, str) else data
        preview, truncated = _truncate_content(content)

        managed_path: str | None = None
        if truncated and self._data_dir:
            managed_path = self._write_to_disk(key, content, session_id)

        full_key = f"{session_id}:{key}" if session_id else key
        _STORE[full_key] = {
            "data": data,
            "preview": preview,
            "truncated": truncated,
            "managed_path": managed_path,
            "saved_at": time.time(),
            "session_id": session_id,
        }

        return BoundedOutput(
            preview=preview,
            truncated=truncated,
            managed_path=managed_path,
        )

    def get(self, key: str, session_id: str | None = None) -> dict[str, Any] | None:
        full_key = f"{session_id}:{key}" if session_id else key
        entry = _STORE.get(full_key)
        if entry is None:
            entry = _STORE.get(key)
        return entry

    def list_keys(self, session_id: str | None = None) -> list[str]:
        if session_id:
            prefix = f"{session_id}:"
            return [k.split(":", 1)[1] for k in _STORE if k.startswith(prefix)]
        return list(_STORE.keys())

    def cleanup(self, session_id: str) -> None:
        """Remove all stored outputs for a session, including disk files."""
        prefix = f"{session_id}:"
        keys_to_delete = [k for k in _STORE if k.startswith(prefix)]
        for key in keys_to_delete:
            entry = _STORE.pop(key, None)
            if entry and entry.get("managed_path") and self._data_dir:
                self._remove_disk_file(entry["managed_path"])

        # Clean up disk directory for this session
        if self._data_dir:
            session_dir = pathlib.Path(self._data_dir) / session_id
            if session_dir.exists():
                for f in session_dir.iterdir():
                    f.unlink()
                session_dir.rmdir()

    def clear(self) -> None:
        _STORE.clear()

    def _write_to_disk(self, key: str, content: str, session_id: str | None) -> str:
        """Write full content to disk, returning the file path."""
        session_part = session_id or "_global"
        store_dir = pathlib.Path(self._data_dir) / session_part  # type: ignore[arg-type]
        store_dir.mkdir(parents=True, exist_ok=True)
        file_path = store_dir / f"{key}.out"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    @staticmethod
    def _remove_disk_file(path: str) -> None:
        try:
            pathlib.Path(path).unlink(missing_ok=True)
        except OSError:
            pass


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
            result = self._backend.save(input.key, input.data, input.session_id)
            return ToolResult(success=True, data=OutputStoreOutput(
                status="saved",
                key=input.key,
                data={"preview": result.preview, "truncated": result.truncated},
            ))

        elif input.action == "get":
            if not input.key:
                return ToolResult(success=False, error="key required for get")
            entry = self._backend.get(input.key, input.session_id)
            if entry is None:
                return ToolResult(success=False, error=f"Key '{input.key}' not found")
            return ToolResult(success=True, data=OutputStoreOutput(key=input.key, data=entry.get("data")))

        elif input.action == "list":
            keys = self._backend.list_keys(input.session_id)
            return ToolResult(success=True, data=OutputStoreOutput(keys=keys))

        return ToolResult(success=False, error=f"Unknown action: {input.action}")
