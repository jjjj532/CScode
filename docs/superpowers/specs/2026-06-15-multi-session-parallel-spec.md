# Spec: Multi-Session Parallel Support

## Objective

实现多会话并行支持，允许用户同时运行多个独立的 Agent 会话，每个会话有独立的状态、消息历史和工具执行环境。

### 用户故事
- 开发者可以在同一终端启动多个并行会话
- 每个会话有独立的 ID、名称、LLM 提供商和模型选择
- 会话间状态隔离，互不影响
- 可以列出、切换、终止任意会话
- 会话可中断后恢复

### 成功标准
- [ ] 可同时运行多个会话 (默认上限 5 个)
- [ ] 每个会话有独立的消息历史
- [ ] 会话间工具执行隔离
- [ ] 可通过命令列出、切换、终止会话
- [ ] 会话持久化到 SQLite
- [ ] 可恢复历史会话

## Tech Stack
- Python 3.11+
- asyncio 并发
- SQLite (已有)
- Click CLI

## Commands

```bash
# 查看所有会话
cs session list

# 创建新会话
cs session new --name "debug-api"

# 切换到指定会话
cs session use <session-id>

# 终止会话
cs session kill <session-id>

# 会话内命令
> /sessions          # 列出所有会话
> /switch <id>       # 切换会话
> /kill <id>        # 终止会话
> /new               # 创建新会话
```

## Project Structure

```
src/cscode/
├── core/
│   ├── session_manager.py   # 新增: 会话管理器
│   └── engine.py            # 修改: 支持会话ID
├── storage/
│   ├── session.py           # 修改: 增强会话存储
│   └── db.py                # 修改: 会话表结构
└── cli.py                   # 修改: 新增 session 命令组
```

## Code Style

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SessionStatus(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    TERMINATED = "terminated"


@dataclass
class Session:
    id: str
    title: str
    provider: str
    model: str
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class SessionManager:
    """管理多个并行会话的容器类"""

    def __init__(self, max_sessions: int = 5):
        self._sessions: dict[str, Session] = {}
        self._active_session_id: str | None = None
        self._max_sessions = max_sessions

    def create(self, title: str = "", provider: str = "openai", model: str = "gpt-4o") -> Session: ...
    def get(self, session_id: str) -> Session | None: ...
    def list(self) -> list[Session]: ...
    def set_active(self, session_id: str) -> bool: ...
    def get_active(self) -> Session | None: ...
    def remove(self, session_id: str) -> bool: ...
```

## Testing Strategy

| 层级 | 框架 | 位置 |
|------|------|------|
| 单元测试 | pytest | `tests/test_session_manager.py` |
| 并发测试 | pytest-asyncio | 并发会话创建/切换 |

覆盖率目标: > 85%

## Boundaries
- **Always**: 会话上限检查、状态验证、空会话ID处理
- **Ask first**: 修改数据库 schema、改变并发模型
- **Never**: 删除活跃会话的消息历史、允许超过上限

## Success Criteria

1. `cs session list` 显示所有会话 (含状态)
2. `cs session new` 创建新会话并自动切换
3. `cs session use <id>` 切换到指定会话
4. `cs session kill <id>` 终止指定会话
5. 多会话可并行运行 (通过后台任务)
6. 会话状态持久化到 SQLite

## Open Questions
- 是否需要支持会话间消息转发?
- 是否需要支持会话链接分享?
