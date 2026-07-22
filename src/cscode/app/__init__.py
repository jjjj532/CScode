"""App Layer — 用户接口入口适配层。

AgentV2 提供 Agent run() 接口，
内部使用 LLMClient + ToolRegistry 架构，
使 cli.py、server/app.py 无需修改核心代码即可使用新后端。
"""

from cscode.app.agent import AgentV2
from cscode.app.factory import build_full_tool_registry, create_agent_v2

__all__ = [
    "AgentV2",
    "build_full_tool_registry",
    "create_agent_v2",
]
