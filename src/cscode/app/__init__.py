"""App Layer — 用户接口入口适配层。

AgentV2 提供与旧 Agent (engine.py) 兼容的 run() 接口，
内部使用全新架构（LLMClient + ToolRegistry），
使 cli.py、server/app.py 无需修改核心代码即可切换到新后端。
"""

from cscode.app.agent import AgentV2
from cscode.app.factory import create_agent_v2

__all__ = [
    "AgentV2",
    "create_agent_v2",
]
