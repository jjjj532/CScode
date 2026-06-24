from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from typing import Any

from cscode.tools.base import BaseTool, ToolResult

TC_PATTERN = re.compile(r"TC[_-]?(\d{3})")


class TodoWriteTool(BaseTool):
    name = "todowrite"
    description = "Create and manage a task list for the current coding session"
    requires_permission = False
    permission_default = "allow"
    parameters = {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Task description"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["content", "status", "priority"],
                },
                "description": "List of tasks to track",
            },
        },
        "required": ["todos"],
    }

    def __init__(
        self,
        on_event: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
    ):
        self.on_event = on_event

    async def execute(self, args: dict[str, Any], context: dict | None = None) -> ToolResult:
        todos = args["todos"]
        session_id = (context or {}).get("session_id", "")
        on_event = (context or {}).get("on_event") or self.on_event
        lines = []
        for t in todos:
            status_map = {"pending": " ", "in_progress": "●", "completed": "✓", "cancelled": "✗"}
            marker = status_map.get(t.get("status", "pending"), " ")
            lines.append(f"[{marker}] {t.get('priority', 'medium').upper()} {t['content']}")

            content = t.get("content", "")
            match = TC_PATTERN.search(content)
            task_id = f"TC-{match.group(1)}" if match else content[:50]
            status = t.get("status", "pending")
            if on_event:
                await on_event({
                    "type": "task_created",
                    "session_id": session_id,
                    "data": {
                        "task_id": task_id,
                        "description": content,
                        "status": status,
                    },
                })
        return ToolResult(success=True, data="\n".join(lines) if lines else "No todos.")
