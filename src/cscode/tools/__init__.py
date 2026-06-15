from typing import TYPE_CHECKING

from cscode.tools.apply_patch import ApplyPatchTool
from cscode.tools.base import ToolRegistry, ToolResult
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

if TYPE_CHECKING:
    from cscode.tools.base import BaseTool


def register_all_tools(registry: ToolRegistry) -> None:
    tools: list[type[BaseTool]] = [
        ReadTool, WriteTool, EditTool, BashTool, GrepTool, GlobTool, LsTool, BrowserTool,
        WebFetchTool, WebSearchTool, TodoWriteTool, QuestionTool, SkillTool, ApplyPatchTool,
    ]
    for tool_cls in tools:
        registry.register(tool_cls())
