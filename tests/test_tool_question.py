from __future__ import annotations

import pytest
from cscode.tools.question import QuestionTool


class TestQuestionTool:
    def test_tool_properties(self) -> None:
        tool = QuestionTool()
        assert tool.name == "question"
        assert "question" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_question_returns_prompt(self) -> None:
        tool = QuestionTool()
        result = await tool.execute({"question": "What is your name?", "options": ["Alice", "Bob"]})
        assert result.success
        assert "What is your name?" in result.data
