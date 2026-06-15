from __future__ import annotations

from typing import Any

from cscode.tools.base import BaseTool, ToolResult


class QuestionTool(BaseTool):
    name = "question"
    description = "Ask the user a question and get their response"
    requires_permission = False
    permission_default = "allow"
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask the user",
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Available options (leave empty for free text)",
            },
        },
        "required": ["question"],
    }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        question = args["question"]
        options = args.get("options", [])

        if options:
            formatted = f"Question: {question}\nOptions:\n" + "\n".join(f"  {i+1}. {o}" for i, o in enumerate(options))
        else:
            formatted = f"Question: {question}"

        return ToolResult(
            success=True,
            data=formatted + "\n[Question tool requires human response — waiting for input in interactive mode]",
        )
