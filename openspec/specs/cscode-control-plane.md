# P2-4: Control-Plane 工作区管理与工作树

## 1. 问题

当前 CScode 有 Workspace（P2-3），但：
- Session 没有绑定到 workspace（所有 session 平铺）
- 无法将 session 从一个 workspace 迁移到另一个
- 没有 git worktree 管理（无法为并行任务隔离目录）
- 无法按 workspace 列出/筛选 session

## 2. 目标

提供 Control-Plane 系统：
1. **Session → Workspace 关联** — 每个 session 可关联到一个 workspace
2. **Move-Session** — 将 session 从当前 workspace 迁移到另一个
3. **Worktree 管理** — 创建、列出、删除 git worktree
4. **Workspace 路由** — 按 workspace 列出 session

## 3. 数据模型

### 3.1 SessionState 扩展

```python
# 在 SessionState 中添加：
workspace_id: str = ""  # 关联的 workspace（空字符串表示未关联）
```

### 3.2 事件扩展

新增事件类型（用于 EventStore）：
- `session.workspace.associated` — 关联 session 到 workspace
- `session.workspace.moved` — 迁移 session 到另一个 workspace

```python
@dataclass
class SessionWorkspaceAssociated:
    session_id: str
    workspace_id: str

@dataclass
class SessionWorkspaceMoved:
    session_id: str
    from_workspace_id: str
    to_workspace_id: str
```

### 3.3 Worktree 管理（纯工具类，无持久化）

```python
@dataclass
class WorktreeInfo:
    path: str          # worktree 绝对路径
    branch: str        # 关联的分支
    hash: str          # HEAD commit hash
    bare: bool         # 是否 bare repo
    detached: bool     # 是否 detached HEAD

class WorktreeManager:
    """Git worktree 管理工具类。
    
    直接调用 git worktree 命令，无需数据库。
    """
```

## 4. API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workspaces/{id}/sessions` | 列出 workspace 下的所有 session |
| PUT | `/api/sessions/{id}/workspace` | 设置 session 的 workspace 关联 |
| POST | `/api/sessions/{id}/move-workspace` | 将 session 迁移到另一个 workspace |
| GET | `/api/worktrees` | 列出所有 worktree |
| POST | `/api/worktrees` | 创建新 worktree |
| DELETE | `/api/worktrees` | 删除指定 worktree |

## 5. 验收标准

1. Session 创建时可选关联 workspace（通过 create 参数）
2. 可以通过 API 将 session 关联到 workspace
3. 可以将 session 从一个 workspace 迁移到另一个（move-session）
4. 可以按 workspace 列出 session
5. 可以创建、列出、删除 git worktree
6. 所有操作经过 EventStore 事件溯源
