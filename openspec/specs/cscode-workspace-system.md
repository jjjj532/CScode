# P2-3: Project/Workspace 多项目管理

## 1. 问题

当前 CScode 没有项目概念，所有 session 平铺存储。用户无法：
- 切换不同代码项目的上下文
- 按项目组织 session
- 为不同项目设置不同 LLM 配置
- 快速恢复上次在某个项目的工作

## 2. 目标

提供 Workspace 管理系统：
1. Workspace CRUD（创建、查询、更新、删除）
2. Workspace 关联 session（按 workspace 分组和筛选）
3. 最近使用项目列表（快速切换）
4. 轻量 SQLite 存储（不需要 EventStore 事件溯源）

## 3. 数据模型

### 3.1 SQLite 表

```sql
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    config_json TEXT DEFAULT '{}',
    last_used_at REAL NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
```

### 3.2 Python 模型

```python
@dataclass
class Workspace:
    workspace_id: str      # UUID
    name: str              # 项目名称（取自目录名或用户指定）
    path: str              # 项目绝对路径
    config: dict[str, object]  # 覆盖配置
    last_used_at: float    # 上次使用时间（用于排序）
    created_at: float
    updated_at: float
```

### 3.3 Session 扩展

SessionState 新增可选字段：`workspace_id: str = ""`，对应 SessionV2 创建事件的数据中可选传入。

## 4. 文件结构

```
src/cscode/core/workspace.py    ← Workspace + WorkspaceStore (新文件)
src/cscode/server/app.py        ← 添加 workspace CRUD 端点
src/cscode/storage/db.py        ← 添加 migration 008
tests/test_workspace.py         ← 新测试文件
```

## 5. API 端点

全部在 `api_router`（前缀 `/api`）：

```
GET    /workspaces              → 列出所有 workspace
POST   /workspaces              → 创建 workspace
GET    /workspaces/{id}         → 获取单个 workspace
PUT    /workspaces/{id}         → 更新 workspace
DELETE /workspaces/{id}         → 删除 workspace
GET    /workspaces/{id}/sessions → 列出该 workspace 的 session
GET    /workspaces/recent       → 最近使用的 workspace（按 last_used_at 倒序）
```

## 6. 验收标准

1. [ ] 创建 workspace 时自动设置 path（绝对路径标准化）
2. [ ] 列出所有 workspace（按 last_used_at 倒序）
3. [ ] 更新 workspace 时更新 updated_at 时间戳
4. [ ] 删除 workspace 级联？→ 不级联，session 保留 workspace_id 引用（软关联）
5. [ ] 按 workspace 筛选 session（API 层）
6. [ ] 最近使用列表最多返回 10 条
7. [ ] 迁移 008 创建 workspaces 表
8. [ ] 空 name/path 校验（创建时必需）

## 7. 不做

- 不实现 EventStore 事件溯源（workspace 是简单数据，不需要）
- 不实现文件系统监听（不自动扫描目录）
- 不实现 workspace 级别的权限
- 不实现 `.cscode` 配置文件写入（只存数据库）
