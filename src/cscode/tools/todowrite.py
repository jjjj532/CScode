from __future__ import annotations

from typing import Any

from cscode.tools.base import BaseTool, ToolResult


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

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        todos = args["todos"]
        lines = []
        for t in todos:
            status_map = {"pending": " ", "in_progress": "●", "completed": "✓", "cancelled": "✗"}
            marker = status_map.get(t.get("status", "pending"), " ")
            lines.append(f"[{marker}] {t.get('priority', 'medium').upper()} {t['content']}")
        return ToolResult(success=True, data="\n".join(lines) if lines else "No todos.")
