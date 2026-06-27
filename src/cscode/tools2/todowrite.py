"""TodoWriteTool v2 — manage task lists with typed output."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult

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

    def __init__(self, on_event: object | None = None) -> None:
        super().__init__()
        self._on_event = on_event

    async def execute(self, input: TodoWriteInput) -> ToolResult[TodoWriteOutput]:
        lines: list[str] = []
        for t in input.todos:
            marker = STATUS_MAP.get(t.status, " ")
            lines.append(f"[{marker}] {t.priority.upper()} {t.content}")

        formatted = "\n".join(lines) if lines else "No todos."
        return ToolResult(
            success=True,
            data=TodoWriteOutput(formatted=formatted, count=len(input.todos)),
            metadata={"count": str(len(input.todos))},
        )
