from __future__ import annotations

import asyncio
import logging
from typing import Any

from cscode.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


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

    async def execute(self, args: dict[str, Any], context: dict[str, Any] | None = None) -> ToolResult:
        question = args["question"]
        options = args.get("options", [])

        pending_questions = (context or {}).get("pending_questions")
        session_id = (context or {}).get("session_id", "")
        tool_call_id = (context or {}).get("tool_call_id", "")

        if pending_questions is None:
            logger.warning("PendingQuestions registry not available, falling back to sync mode")
            formatted = f"Question: {question}\nOptions:\n" + "\n".join(f"  {i+1}. {o}" for i, o in enumerate(options)) if options else f"Question: {question}"
            return ToolResult(success=True, data=formatted)

        # Format: opencode-style Deferred blocking
        # Register with the pending questions registry and BLOCK until answered
        questions_payload = [{
            "question": question,
            "options": options or [],
        }]

        try:
            answers = await pending_questions.register(
                session_id=session_id,
                tool_call_id=tool_call_id,
                questions=questions_payload,
            )

            formatted = (
                f"Question: {question}\n"
            )
            if options:
                formatted += "Options:\n" + "\n".join(f"  {i+1}. {o}" for i, o in enumerate(options)) + "\n"
            formatted += f"User's answer(s): {', '.join(answers) if answers else 'Unanswered'}"

            return ToolResult(success=True, data=formatted)

        except asyncio.CancelledError:
            return ToolResult(
                success=False,
                data="",
                error="Question was cancelled by user",
            )
