from __future__ import annotations

from cscode.tools.base import ToolRegistry
from cscode.tools.apply_patch import ApplyPatchTool
from cscode.tools.bash import BashTool
from cscode.tools.browser import BrowserTool
from cscode.tools.edit import EditTool
from cscode.tools.glob import GlobTool
from cscode.tools.grep import GrepTool
from cscode.tools.ls import LsTool
from cscode.tools.question import QuestionTool
from cscode.tools.read import ReadTool
from cscode.tools.skill import SkillTool
from cscode.tools.todowrite import TodoWriteTool
from cscode.tools.webfetch import WebFetchTool
from cscode.tools.websearch import WebSearchTool
from cscode.tools.write import WriteTool

EXPECTED_TOOLS = [
    "read", "write", "edit", "bash", "grep", "glob", "ls", "browser",
    "todowrite", "skill", "question", "webfetch", "websearch", "apply_patch",
]


class TestAllToolsRegistered:
    def test_all_14_tools_registered(self):
        registry = ToolRegistry()
        registry.register(ReadTool())
        registry.register(WriteTool())
        registry.register(EditTool())
        registry.register(BashTool())
        registry.register(GrepTool())
        registry.register(GlobTool())
        registry.register(LsTool())
        registry.register(BrowserTool())
        registry.register(TodoWriteTool())
        registry.register(SkillTool())
        registry.register(QuestionTool())
        registry.register(WebFetchTool())
        registry.register(WebSearchTool())
        registry.register(ApplyPatchTool())

        registered = registry.list_tools()
        assert len(registered) == 14, f"Expected 14 tools, got {len(registered)}: {registered}"
        for tool_name in EXPECTED_TOOLS:
            assert tool_name in registered, f"Missing tool: {tool_name}"
            assert registry.get(tool_name) is not None, f"Tool {tool_name} not retrievable"

    def test_tools_have_llm_format(self):
        registry = ToolRegistry()
        registry.register(ReadTool())
        registry.register(WriteTool())
        registry.register(EditTool())
        registry.register(BashTool())
        registry.register(GrepTool())
        registry.register(GlobTool())
        registry.register(LsTool())
        registry.register(BrowserTool())
        registry.register(TodoWriteTool())
        registry.register(SkillTool())
        registry.register(QuestionTool())
        registry.register(WebFetchTool())
        registry.register(WebSearchTool())
        registry.register(ApplyPatchTool())

        llm_tools = registry.to_llm_tools()
        assert len(llm_tools) == 14, f"Expected 14 LLM tools, got {len(llm_tools)}"
        names = [t["function"]["name"] for t in llm_tools]
        for tool_name in EXPECTED_TOOLS:
            assert tool_name in names, f"Missing LLM tool: {tool_name}"

    def test_no_duplicate_tool_names(self):
        registry = ToolRegistry()
        registry.register(ReadTool())
        registry.register(WriteTool())
        registry.register(EditTool())
        registry.register(BashTool())
        registry.register(GrepTool())
        registry.register(GlobTool())
        registry.register(LsTool())
        registry.register(BrowserTool())
        registry.register(TodoWriteTool())
        registry.register(SkillTool())
        registry.register(QuestionTool())
        registry.register(WebFetchTool())
        registry.register(WebSearchTool())
        registry.register(ApplyPatchTool())

        registered = registry.list_tools()
        assert len(registered) == len(set(registered)), "Duplicate tool names found"

    async def test_tools_execute(self):
        """Verify each tool can execute without crashing."""
        import pytest

        tools = [
            (TodoWriteTool(), {"todos": [{"content": "Test", "status": "pending", "priority": "high"}]}),
            (SkillTool(), {"name": "test-skill"}),
            (QuestionTool(), {"question": "Are you sure?"}),
            (WebSearchTool(), {"query": "test"}),
            (ApplyPatchTool(), {"path": "/nonexistent", "patch_content": "--- a/test\n+++ b/test\n@@ -1 +1 @@\n-old\n+new\n"}),
        ]

        for tool, args in tools:
            result = await tool.execute(args)
            assert result is not None, f"{tool.name} returned None"
