"""CScode Tool System v2 — 全新构建，接口驱动。

遵循 schema → llm → core → app 依赖顺序，使用 schema/tool.py 的类型定义。
旧 src/cscode/tools/ 不动，此目录是新实现。
"""

from cscode.tools2.apply_patch import ApplyPatchTool
from cscode.tools2.base import Tool, ToolResult
from cscode.tools2.bash import BashTool
from cscode.tools2.browser import BrowserTool
from cscode.tools2.edit import EditTool
from cscode.tools2.glob import GlobTool
from cscode.tools2.grep import GrepTool
from cscode.tools2.ls import LsTool
from cscode.tools2.question import QuestionTool
from cscode.tools2.read import ReadTool
from cscode.tools2.registry import ToolRegistry
from cscode.tools2.skill import SkillTool
from cscode.tools2.todowrite import TodoWriteTool
from cscode.tools2.webfetch import WebFetchTool
from cscode.tools2.websearch import WebSearchTool
from cscode.tools2.write import WriteTool

__all__ = [
    "Tool",
    "ToolResult",
    "ToolRegistry",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "BashTool",
    "GrepTool",
    "GlobTool",
    "LsTool",
    "WebFetchTool",
    "WebSearchTool",
    "TodoWriteTool",
    "QuestionTool",
    "SkillTool",
    "ApplyPatchTool",
    "BrowserTool",
]
