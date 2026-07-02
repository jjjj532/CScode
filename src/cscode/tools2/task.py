"""TaskTool — manage sub-tasks (create, list, update, complete).

The LLM invokes this tool to track progress on individual steps within
a larger plan or workflow.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from cscode.tools2.base import Tool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

Action = Literal["create", "list", "update"]


class TaskInput(BaseModel):
    action: Action = Field(..., description="Action: create, list, or update")
    task_id: str | None = Field(None, description="Task ID (required for update)")
    description: str | None = Field(None, description="Task description (required for create)")
    status: str | None = Field(None, description="New status: pending, in_progress, completed")


class TaskItem(BaseModel):
    task_id: str = ""
    description: str = ""
    status: str = ""


class TaskOutput(BaseModel):
    """Flexible output model for all task actions."""
    task_id: str = ""
    description: str = ""
    status: str = ""
    tasks: list[dict[str, str]] = []


# In-memory task store (session-scoped in production)
_TASK_STORE: dict[str, dict[str, str]] = {}


class TaskTool(Tool[TaskInput, TaskOutput]):
    """Create, list, and update sub-tasks."""

    name: str = "task"
    description: str = "Manage sub-tasks: create new tasks, list all tasks, or update task status."
    input_schema: type[TaskInput] = TaskInput
    output_schema: type[TaskOutput] = TaskOutput

    async def execute(self, input: TaskInput) -> ToolResult[TaskOutput]:
        if input.action == "create":
            if not input.description or not input.description.strip():
                return ToolResult(success=False, error="Description required for create")
            tid = str(uuid.uuid4())[:12]
            _TASK_STORE[tid] = {
                "task_id": tid,
                "description": input.description,
                "status": "pending",
            }
            return ToolResult(
                success=True,
                data=TaskOutput(task_id=tid, description=input.description, status="pending"),
            )

        elif input.action == "list":
            return ToolResult(
                success=True,
                data=TaskOutput(tasks=list(_TASK_STORE.values())),
            )

        elif input.action == "update":
            if not input.task_id:
                return ToolResult(success=False, error="task_id required for update")
            task = _TASK_STORE.get(input.task_id)
            if task is None:
                return ToolResult(success=False, error=f"Task '{input.task_id}' not found")
            if input.status:
                task["status"] = input.status
            return ToolResult(
                success=True,
                data=TaskOutput(task_id=task["task_id"], description=task["description"], status=task["status"]),
            )

        return ToolResult(success=False, error=f"Unknown action: {input.action}")
