"""QuestionTool v2 — ask user questions with typed output."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class QuestionInput(BaseModel):
    question: str
    options: list[str] = []


class QuestionOutput(BaseModel):
    formatted: str


class QuestionTool(Tool[QuestionInput, QuestionOutput]):
    name = "question"
    description = "Ask the user a question and get their response"
    input_schema = QuestionInput
    output_schema = QuestionOutput

    async def execute(self, input: QuestionInput) -> ToolResult[QuestionOutput]:
        formatted = f"Question: {input.question}"
        if input.options:
            formatted += "\nOptions:\n" + "\n".join(
                f"  {i+1}. {o}" for i, o in enumerate(input.options)
            )
        return ToolResult(
            success=True,
            data=QuestionOutput(formatted=formatted),
        )
