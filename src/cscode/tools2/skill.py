"""SkillTool v2 — invoke skills with typed output."""

from __future__ import annotations

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult


class SkillInput(BaseModel):
    name: str


class SkillOutput(BaseModel):
    message: str


class SkillTool(Tool[SkillInput, SkillOutput]):
    name = "skill"
    description = "Load and invoke a specialized skill for domain-specific tasks"
    input_schema = SkillInput
    output_schema = SkillOutput

    async def execute(self, input: SkillInput) -> ToolResult[SkillOutput]:
        return ToolResult(
            success=True,
            data=SkillOutput(
                message=f"[Skill stub] Would load skill '{input.name}'."
            ),
        )
