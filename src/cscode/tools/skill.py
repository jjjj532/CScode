from __future__ import annotations

from typing import Any

from cscode.tools.base import BaseTool, ToolResult


class SkillTool(BaseTool):
    name = "skill"
    description = "Load and invoke a specialized skill for domain-specific tasks"
    requires_permission = False
    permission_default = "allow"
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the skill to invoke",
            },
        },
        "required": ["name"],
    }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        name = args["name"]
        return ToolResult(
            success=True,
            data=f"[Skill stub] Would load skill '{name}'. Full skill dispatch coming in Phase 3.",
        )
