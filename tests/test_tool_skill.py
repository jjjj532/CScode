from __future__ import annotations

import pytest
from cscode.tools.skill import SkillTool


class TestSkillTool:
    def test_tool_properties(self) -> None:
        tool = SkillTool()
        assert tool.name == "skill"
        assert "name" in tool.parameters["properties"]
