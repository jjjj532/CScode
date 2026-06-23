# CScode 任务验证与追踪机制

目标：让 CScode 服务企业级软件测试，确保测试结果完全真实可信，杜绝 LLM 推断/伪造测试结果。

## 1. 整体架构

```
┌─────────────────────────────────────────────────────┐
│                    系统提示词层                        │
│  app.py: 新增 CRITICAL RULES — 禁止推断、强制证据      │
└──────────────────────┬──────────────────────────────┘
                       │ LLM 调用 Browser/Bash 工具
                       ▼
┌─────────────────────────────────────────────────────┐
│                    工具执行层                         │
│  browser.py: execute() 新增 evidence 字段             │
│  bash.py: execute() 新增 evidence 字段                │
│  → 工具返回时自动附带 verified + timestamp + evidence │
└──────────────────────┬──────────────────────────────┘
                       │ tool.success 事件（含 evidence）
                       ▼
┌─────────────────────────────────────────────────────┐
│                    事件存储层（已有）                   │
│  event_store.py: tool.success 事件新增 evidence 字段   │
└──────────────────────┬──────────────────────────────┘
                       │ 事件流
                       ▼
┌─────────────────────────────────────────────────────┐
│                    TaskTracker 投影层（新增）          │
│  core/tracker.py: 订阅 tool.success 事件              │
│  → 写入 task_verifications 投影表                     │
│  → 提供 get_execution_report() 查询接口               │
└──────────────────────┬──────────────────────────────┘
                       │ 查询
                       ▼
┌─────────────────────────────────────────────────────┐
│                    报告生成层（新增）                   │
│  API: GET /sessions/{id}/verification-report          │
│  → 返回 EXECUTED / SKIPPED / UNVERIFIED 分类报告      │
└─────────────────────────────────────────────────────┘
```

**核心原理：** 报告来自数据库投影，不是 LLM 文本。LLM 无法在报告中"编造"已执行的用例。

## 2. 数据模型

### 2.1 事件 `tool.success` 扩展字段

```python
# event_store.py — tool.success 事件新增字段
{
    "type": "tool.success",
    "tool": "browser",
    "task_id": "TC001",           # 新增：关联测试用例 ID
    "evidence": {                  # 新增：执行证据
        "screenshot": True,        # 是否有截图
        "html": True,              # 是否有 HTML 内容
        "content_length": 1234,    # 返回内容大小（0 = 空）
        "timestamp": "2026-06-23T10:30:00"
    },
    "verified": True,              # 新增：是否通过验证
    "output": "..."                # 原有：工具输出
}
```

### 2.2 新增投影表 `task_verifications`

```sql
CREATE TABLE task_verifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    task_id     TEXT NOT NULL,          -- TC001, TC002...
    tool_name   TEXT NOT NULL,          -- browser, bash...
    verified    INTEGER NOT NULL,       -- 0=未验证, 1=已验证
    evidence    TEXT NOT NULL,          -- JSON: {screenshot, html, content_length}
    result_summary TEXT,                -- 工具返回摘要（截断 500 字符）
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(session_id, task_id, tool_name)
);

CREATE INDEX idx_tv_session ON task_verifications(session_id);
```

### 2.3 新增 `expected_tasks` 表（记录用户要求的任务列表）

```sql
CREATE TABLE expected_tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    task_id     TEXT NOT NULL,          -- TC001, TC002...
    description TEXT,                   -- 用例描述
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(session_id, task_id)
);
```

## 3. TaskTracker 投影器

**文件：** `src/cscode/core/tracker.py`（新增）

```python
@dataclass
class TaskStatus:
    session_id: str
    task_id: str
    tool_name: str
    verified: bool
    evidence: dict
    result_summary: str
    timestamp: str

class TaskTracker:
    """订阅 tool.success 事件，写入 task_verifications 投影表"""

    def __init__(self, db: Database):
        self.db = db

    async def on_tool_success(self, event: dict):
        """事件回调：tool.success → 写入投影表"""
        evidence = event.get("evidence", {})
        verified = self._verify_evidence(event["tool"], evidence)

        await self.db.execute("""
            INSERT OR REPLACE INTO task_verifications
            (session_id, task_id, tool_name, verified, evidence, result_summary)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            event["session_id"],
            event.get("task_id", "unknown"),
            event["tool"],
            int(verified),
            json.dumps(evidence),
            event.get("output", "")[:500]
        ])

    def _verify_evidence(self, tool: str, evidence: dict) -> bool:
        """严格验证：浏览器操作必须有截图 AND HTML"""
        if tool == "browser":
            return evidence.get("screenshot", False) and evidence.get("html", False)
        if tool == "bash":
            return evidence.get("content_length", 0) > 0
        return bool(evidence)

    def get_execution_report(self, session_id: str) -> dict:
        """查询会话的验证报告"""
        rows = self.db.fetch_all(
            "SELECT task_id, verified, evidence, result_summary, created_at "
            "FROM task_verifications WHERE session_id = ?",
            [session_id]
        )
        executed = [r for r in rows if r["verified"]]
        unverified = [r for r in rows if not r["verified"]]

        return {
            "summary": {
                "executed": len(executed),
                "unverified": len(unverified),
                "skipped": 0  # 由 API 层根据 expected_tasks 计算
            },
            "details": [
                {
                    "task_id": r["task_id"],
                    "status": "EXECUTED" if r["verified"] else "UNVERIFIED",
                    "evidence": json.loads(r["evidence"]),
                    "timestamp": r["created_at"]
                }
                for r in rows
            ]
        }
```

**集成点：** `app.py` 启动时注册订阅：

```python
tracker = TaskTracker(db)
event_store.subscribe("tool.success", tracker.on_tool_success)
```

## 4. 系统提示词增强

**修改位置：** `src/cscode/server/app.py`，在现有系统提示词末尾追加：

```python
"""
CRITICAL RULES FOR TESTING — VIOLATION WILL BE DETECTED:
1. Every test case MUST be executed through real tool calls (browser, bash, etc.).
   Each tool call is recorded and verified. You CANNOT fake execution.
2. NEVER infer or guess test results from documentation, code, or prior knowledge.
   If you did not call a tool, the result does not exist.
3. If a test cannot be executed (no credentials, blocked URL, timeout):
   Mark it "SKIPPED: <reason>" — do NOT mark it as passed or failed.
4. For browser tests, you MUST capture BOTH screenshot AND HTML content.
   A test without both is UNVERIFIED and will not count as executed.
5. In your final response, use this format for each test case:
   [EXECUTED] TC001 — Login success — evidence: screenshot + HTML
   [SKIPPED]  TC002 — Payment test — reason: no test credentials
   [UNVERIFIED] — This status means the tool returned empty result, re-run needed
6. The verification report is generated from the database, not from your text.
   You cannot "convince" the system — only real tool calls count.
"""
```

## 5. 工具层修改

### 5.1 Browser 工具

**修改位置：** `src/cscode/tools/browser.py` 的 `execute()` 方法

```python
async def execute(self, action: str, **kwargs) -> dict:
    result = await self._execute_action(action, **kwargs)

    # 自动注入验证元数据
    result["verified"] = True
    result["timestamp"] = datetime.now().isoformat()
    result["evidence"] = {
        "screenshot": action == "screenshot" and bool(result.get("content")),
        "html": action in ("get_html", "get_text") and bool(result.get("content")),
        "content_length": len(result.get("content", "")),
    }

    # 内容获取操作：空结果 = 未验证
    if action in ("screenshot", "get_html", "get_text"):
        if not result.get("content"):
            result["verified"] = False

    return result
```

### 5.2 Bash 工具

**修改位置：** `src/cscode/tools/bash.py` 的 `execute()` 方法

```python
result["evidence"] = {
    "content_length": len(result.get("stdout", "")) + len(result.get("stderr", "")),
}
result["verified"] = result["evidence"]["content_length"] > 0
```

## 6. 报告 API

**修改位置：** `src/cscode/server/app.py`，新增路由

```python
@app.get("/sessions/{session_id}/verification-report")
async def get_verification_report(session_id: str):
    """返回基于数据库投影的验证报告，非 LLM 生成"""
    report = tracker.get_execution_report(session_id)

    # 计算 SKIPPED：用户要求的 task_ids 中不在投影表的
    all_expected = await db.fetch_all(
        "SELECT task_id FROM expected_tasks WHERE session_id = ?",
        [session_id]
    )
    expected_ids = {r["task_id"] for r in all_expected}
    recorded_ids = {d["task_id"] for d in report["details"]}
    skipped = expected_ids - recorded_ids

    report["summary"]["skipped"] = len(skipped)
    report["details"].extend([
        {"task_id": tid, "status": "SKIPPED", "evidence": {}, "timestamp": None}
        for tid in skipped
    ])

    return report
```

## 7. 会话内容乱窜修复

**修改位置：** 前端 `useChat.ts`

```typescript
const isCurrent = () => {
  const activeId = useSessionStore.getState().activeSessionId;
  return streamControllers[sid] === controller && activeId === sid;
};
```

## 8. task_id 传递机制

**问题：** `task_id`（如 TC001）如何从 LLM 调用传递到工具层，再写入事件？

**方案：** 利用现有的 `todowrite` 工具作为桥梁。

1. LLM 通过 `todowrite` 创建任务列表时，同时将任务写入 `expected_tasks` 表
2. LLM 调用 browser/bash 时，在参数中携带 `task_id`
3. 工具层从参数中提取 `task_id`，注入到返回结果中
4. `tool.success` 事件自然携带 `task_id`

**修改点：**

```python
# todowrite.py — 执行时同步写入 expected_tasks
async def execute(self, todos: list, session_id: str):
    for todo in todos:
        await db.execute(
            "INSERT OR IGNORE INTO expected_tasks (session_id, task_id, description) VALUES (?, ?, ?)",
            [session_id, todo.get("id", todo["content"][:20]), todo["content"]]
        )
    # ... 原有逻辑
```

```python
# browser.py — 从参数提取 task_id
async def execute(self, action: str, task_id: str = None, **kwargs):
    result = await self._execute_action(action, **kwargs)
    result["task_id"] = task_id  # 透传到事件
    # ... evidence 逻辑
```

## 9. 实现优先级

| 优先级 | 任务 | 涉及文件 | 理由 |
|--------|------|---------|------|
| P0 | 修复会话内容乱窜 | `useChat.ts` | 阻塞用户体验，必须先解决 |
| P1 | 增强系统提示词 | `app.py` | 最简单，立即生效 |
| P1 | TaskTracker 投影器 | `core/tracker.py`（新增） | 核心追踪能力 |
| P1 | 数据库迁移（新增表） | `storage/db.py` | 投影表 + expected_tasks 表 |
| P1 | TodoWrite 同步 expected_tasks | `tools/todowrite.py` | task_id 传递桥梁 |
| P2 | Browser 工具 evidence + task_id | `tools/browser.py` | 需要修改工具执行 |
| P2 | Bash 工具 evidence + task_id | `tools/bash.py` | 需要修改工具执行 |
| P2 | 事件 store 扩展 | `storage/event_store.py` | tool.success 新增字段 |
| P2 | 报告 API | `app.py` | 依赖 TaskTracker |
| P2 | TaskTracker 集成注册 | `app.py` | 启动时订阅事件 |

## 10. 验收标准

1. **禁止推断：** LLM 无法在没有工具调用的情况下声称测试通过
2. **证据强制：** 浏览器测试必须有截图 + HTML 才算 EXECUTED
3. **报告可信：** 报告 API 返回的数据来自数据库，不是 LLM 文本
4. **可审计：** 每个测试用例的执行状态可追溯到 `task_verifications` 表
5. **会话隔离：** 切换会话时内容不串扰
6. **持久化：** 服务重启后验证记录不丢失
