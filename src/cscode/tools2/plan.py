"""PlanTool — creates structured task plans from a goal.

The LLM invokes this tool to break a high-level goal into ordered,
actionable steps before beginning implementation work.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from cscode.tools2.base import Tool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class PlanInput(BaseModel):
    goal: str = Field(..., description="The high-level goal or objective to plan for")
    context: str | None = Field(None, description="Optional context/constraints to inform the plan")


class PlanStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str
    status: str = "pending"


class PlanOutput(BaseModel):
    plan_id: str
    steps: list[PlanStep]
    summary: str = ""


class PlanTool(Tool[PlanInput, PlanOutput]):
    """Break a goal into ordered, actionable steps."""

    name: str = "plan"
    description: str = "Create a structured plan from a goal. Breaks the goal into ordered, actionable steps."
    input_schema: type[PlanInput] = PlanInput
    output_schema: type[PlanOutput] = PlanOutput

    async def execute(self, input: PlanInput) -> ToolResult[PlanOutput]:
        if not input.goal.strip():
            return ToolResult(
                success=False,
                error="Goal cannot be empty",
            )

        steps = self._decompose(input.goal, input.context)
        plan_id = str(uuid.uuid4())[:12]
        return ToolResult(
            success=True,
            data=PlanOutput(
                plan_id=plan_id,
                steps=[PlanStep(description=s) for s in steps],
                summary=f"Plan '{input.goal[:60]}' created with {len(steps)} steps",
            ),
        )

    @staticmethod
    def _decompose(goal: str, context: str | None) -> list[str]:
        """Decompose a goal into generic ordered steps.

        This is a template decomposition. In production, the LLM or a
        planner model would produce these steps. For now we generate a
        reasonable default sequence.
        """
        base = [
            f"Analyze requirements for: {goal}",
            f"Design solution for: {goal}",
            f"Implement core logic for: {goal}",
            f"Test and verify: {goal}",
            f"Document and review: {goal}",
        ]
        if context:
            base.insert(1, f"Review context: {context}")
        return base
