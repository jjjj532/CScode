"""TodoWriteTool v2 — manage task lists with typed output."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult

if TYPE_CHECKING:
    from cscode.storage.db import Database

TC_PATTERN = re.compile(r"TC[_-]?(\d{3})")
STATUS_MAP = {"pending": " ", "in_progress": "●", "completed": "✓", "cancelled": "✗"}


class TodoItem(BaseModel):
    content: str
    status: Literal["pending", "in_progress", "completed", "cancelled"] = "pending"
    priority: Literal["high", "medium", "low"] = "medium"


class TodoWriteInput(BaseModel):
    todos: list[TodoItem]


class TodoWriteOutput(BaseModel):
    formatted: str
    count: int


class TodoWriteTool(Tool[TodoWriteInput, TodoWriteOutput]):
    name = "todowrite"
    description = "Create and manage a task list for the current coding session"
    input_schema = TodoWriteInput
    output_schema = TodoWriteOutput

    def __init__(self, on_event: Callable[..., Awaitable[None]] | None = None) -> None:
        super().__init__()
        self._on_event = on_event

    async def execute(
        self, input: TodoWriteInput, context: dict[str, Any] | None = None
    ) -> ToolResult[TodoWriteOutput]:
        session_id = (context or {}).get("session_id", "")
        db: "Database | None" = (context or {}).get("db")
        on_event = (context or {}).get("on_event") or self._on_event

        for t in input.todos:
            match = TC_PATTERN.search(t.content)
            task_id = f"TC-{match.group(1)}" if match else t.content[:50]
            if db and session_id:
                try:
                    await db.execute(
                        "INSERT OR IGNORE INTO expected_tasks (session_id, task_id, description, priority) VALUES (?, ?, ?, ?)",
                        (session_id, task_id, t.content, t.priority),
                    )
                except Exception:
                    pass
            if callable(on_event):
                await on_event({
                    "type": "task_created",
                    "session_id": session_id,
                    "data": {
                        "task_id": task_id,
                        "description": t.content,
                        "status": t.status,
                    },
                })

        lines = []
        for t in input.todos:
            marker = STATUS_MAP.get(t.status, " ")
            lines.append(f"[{marker}] {t.priority.upper()} {t.content}")

        formatted = "\n".join(lines) if lines else "No todos."
        return ToolResult(
            success=True,
            data=TodoWriteOutput(formatted=formatted, count=len(input.todos)),
            metadata={"count": str(len(input.todos))},
        )
