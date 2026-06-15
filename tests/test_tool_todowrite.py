from __future__ import annotations

import pytest
from cscode.tools.todowrite import TodoWriteTool


class TestTodoWriteTool:
    def test_tool_properties(self) -> None:
        tool = TodoWriteTool()
        assert tool.name == "todowrite"
        assert "todos" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_create_todos(self) -> None:
        tool = TodoWriteTool()
        result = await tool.execute({
            "todos": [
                {"content": "Task 1", "status": "pending", "priority": "high"},
                {"content": "Task 2", "status": "completed", "priority": "medium"},
            ]
        })
        assert result.success
        assert "Task 1" in result.data
        assert "Task 2" in result.data
