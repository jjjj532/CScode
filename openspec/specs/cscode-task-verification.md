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
    task_id     TEXT NOT NULL,          -- TC-001, TC-002...
    tool_name   TEXT NOT NULL,          -- browser, bash...
    status      TEXT NOT NULL DEFAULT 'UNVERIFIED',  -- EXECUTED, FAILED, UNVERIFIED
    verified    INTEGER NOT NULL,       -- 0=未验证, 1=已验证
    evidence    TEXT NOT NULL,          -- JSON: {screenshot_path, html, content_length}
    result_summary TEXT,                -- 工具返回摘要（截断 500 字符）
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(session_id, task_id, tool_name)
);

CREATE INDEX idx_tv_session ON task_verifications(session_id);
CREATE INDEX idx_tv_status ON task_verifications(session_id, status);
```

**证据存储策略：** 截图/大内容存储到文件系统（`/tmp/cscode-outputs/evidence/`），数据库只存文件路径，避免表膨胀。截图表名格式为 `{session_id}_{task_id}_screenshot.png`，防止跨会话冲突。

```python
# evidence JSON 示例
{
    "screenshot_path": "/tmp/cscode-outputs/evidence/sess-abc_TC-001_screenshot.png",
    "html": true,
    "html_length": 1234,
    "content_length": 1234,
    "timestamp": "2026-06-23T10:30:00"
}
```

**证据目录：** 在 `app.py` 启动时预创建 `/tmp/cscode-outputs/evidence/`，不由 screenshot action 动态创建。旧证据文件不清除，由用户按需手动清理。

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

### 3.1 集成方式

**关键发现：** `EventStore.subscribe()` 是按 `aggregate_id`（session_id）订阅的，不支持按事件类型全局订阅。因此 TaskTracker 通过 `app.py` 的 `on_event` 回调集成，而非 EventStore 订阅。

```
engine.py _emit() → app.py on_event() → EventStore.append() + TaskTracker.handle_event()
```

### 3.2 核心实现

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from cscode.storage.db import Database


@dataclass
class TaskStatus:
    session_id: str
    task_id: str
    tool_name: str
    status: str  # EXECUTED, FAILED, UNVERIFIED, SKIPPED
    evidence: dict = field(default_factory=dict)
    result_summary: str = ""
    timestamp: str = ""


class TaskTracker:
    """通过 on_event 回调接收工具事件，写入 task_verifications 投影表"""

    def __init__(self, db: Database):
        self.db = db

    async def handle_event(self, session_id: str, event: dict[str, Any]) -> None:
        """处理 tool.success 和 tool.failed 事件"""
        evt_type = event.get("type", "")
        if evt_type not in ("tool.success", "tool.failed"):
            return

        data = event.get("data", {})
        args = data.get("args", {})
        metadata = data.get("metadata", {})

        task_id = args.get("task_id") or metadata.get("task_id", "")
        if not task_id:
            return  # 非测试任务，跳过

        tool_name = data.get("name", "unknown")

        if evt_type == "tool.success":
            evidence_raw = metadata.get("evidence", "{}")
            evidence = json.loads(evidence_raw) if isinstance(evidence_raw, str) else evidence_raw
            verified = self._verify_evidence(tool_name, evidence)
            status = "EXECUTED" if verified else "UNVERIFIED"
            result_summary = data.get("result", "")[:500]
        else:
            # tool.failed
            evidence = {}
            verified = False
            status = "FAILED"
            result_summary = data.get("error", "")[:500]

        await self.db.execute(
            """INSERT OR REPLACE INTO task_verifications
               (session_id, task_id, tool_name, status, verified, evidence, result_summary)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [session_id, task_id, tool_name, status, int(verified),
             json.dumps(evidence), result_summary]
        )

    def _verify_evidence(self, tool: str, evidence: dict) -> bool:
        """严格验证：浏览器操作必须有截图 AND HTML；Bash 必须有输出"""
        if tool == "browser":
            return bool(evidence.get("screenshot_path")) and evidence.get("html", False)
        if tool == "bash":
            return evidence.get("content_length", 0) > 0
        return bool(evidence)

    async def get_execution_report(self, session_id: str) -> dict:
        """查询会话的验证报告"""
        rows = await self.db.fetchall(
            "SELECT task_id, status, verified, evidence, result_summary, created_at "
            "FROM task_verifications WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        executed = [r for r in rows if r["status"] == "EXECUTED"]
        failed = [r for r in rows if r["status"] == "FAILED"]
        unverified = [r for r in rows if r["status"] == "UNVERIFIED"]

        return {
            "summary": {
                "executed": len(executed),
                "failed": len(failed),
                "unverified": len(unverified),
                "skipped": 0  # 由 API 层根据 expected_tasks 计算
            },
            "details": [
                {
                    "task_id": r["task_id"],
                    "status": r["status"],
                    "evidence": json.loads(r["evidence"]) if r["evidence"] else {},
                    "result_summary": r["result_summary"],
                    "timestamp": r["created_at"]
                }
                for r in rows
            ]
        }
```

### 3.3 集成点（app.py on_event 回调中）

```python
# app.py，on_event 回调函数内（约第 461 行），在 EventStore.append 之后添加：
async def on_event(event: dict[str, Any]) -> None:
    await queue.put(event)
    if _event_store is not None:
        # ... 原有 EventStore.append 逻辑 ...
    # 新增：通知 TaskTracker
    if _tracker is not None:
        await _tracker.handle_event(session_id, event)
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
5. task_id format MUST be: TC-XXX (XXX is 3-digit number, e.g. TC-001, TC-002).
   Use this format consistently in todowrite and all tool calls.
6. In your final response, use this format for each test case:
   [EXECUTED]   TC-001 — Login success — evidence: screenshot + HTML
   [FAILED]     TC-002 — Login failure — error: timeout
   [SKIPPED]    TC-003 — Payment test — reason: no test credentials
   [UNVERIFIED] TC-004 — Empty page — re-run needed
7. The verification report is generated from the database, not from your text.
   You cannot "convince" the system — only real tool calls count.
"""
```

## 5. 工具层修改

### 5.1 Browser 工具

**修改位置：** `src/cscode/tools/browser.py`

**参数 schema 新增 task_id：**

```python
class BrowserTool(BaseTool):
    parameters = {
        "type": "object",
        "properties": {
            "action": {...},
            "task_id": {"type": "string", "description": "Test case ID (format: TC-XXX) for tracking"},
            # ... 其他字段不变
        },
        "required": ["action"],
    }
```

**execute() 注入 evidence 到 metadata：**

```python
import json
from datetime import datetime, timezone

EVIDENCE_DIR = "/tmp/cscode-outputs/evidence"

async def execute(self, args: dict[str, Any]) -> ToolResult:
    task_id = args.get("task_id", "")
    # ... 原有执行逻辑 ...
    
    # 截图操作：保存到 evidence 目录，文件名含 session_id 防冲突
    if action == "screenshot":
        evidence_path = path
        if task_id:
            os.makedirs(EVIDENCE_DIR, exist_ok=True)
            session_id = args.get("_session_id", "")
            evidence_path = os.path.join(EVIDENCE_DIR, f"{session_id}_{task_id}_screenshot.png")
        # ... 截图保存到 evidence_path ...
    
    # 构建 evidence（存路径，不存内容）
    evidence = {
        "screenshot_path": evidence_path if action == "screenshot" else "",
        "html": action in ("get_html", "get_text") and bool(result.data),
        "html_length": len(result.data) if action in ("get_html", "get_text") else 0,
        "content_length": len(result.data),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    # 浏览器验证：必须有截图路径 AND HTML 内容
    verified = bool(evidence["screenshot_path"]) and evidence["html"]
    
    result.metadata["task_id"] = task_id
    result.metadata["evidence"] = json.dumps(evidence)
    result.metadata["verified"] = str(verified)
    return result
```

**证据目录预创建：** 在 `app.py` 启动时，`/tmp/cscode-outputs` 创建之后：

```python
EVIDENCE_DIR = "/tmp/cscode-outputs/evidence"
os.makedirs(EVIDENCE_DIR, exist_ok=True)
```

**浏览器截图验证规则：** 单次工具调用必须同时有 `screenshot_path` 和 `html=True` 才算 EXECUTED。LLM 需要分别调用 screenshot 和 get_text/get_html 两个操作，两个操作分别记录到 `task_verifications` 表，各自独立验证。一个截图操作只记录 `screenshot_path`（html=False），一个 get_text 操作只记录 `html=True`（screenshot_path=""），**没有一个单项操作能单独通过验证**——LLM 必须同时执行两者。

### 5.2 Bash 工具

**修改位置：** `src/cscode/tools/bash.py`

```python
import json

class BashTool(BaseTool):
    parameters = {
        "type": "object",
        "properties": {
            "command": {...},
            "timeout": {...},
            "task_id": {"type": "string", "description": "Test case ID (format: TC-XXX) for tracking"},
        },
        "required": ["command"],
    }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        task_id = args.get("task_id", "")
        # ... 原有执行逻辑 ...
        
        # 注入 evidence 到 metadata
        content_length = len(stdout) + len(stderr) if exit_code == 0 else 0
        result.metadata["task_id"] = task_id
        result.metadata["evidence"] = json.dumps({
            "content_length": content_length,
            "exit_code": exit_code,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        result.metadata["verified"] = str(content_length > 0)
        return result
```

## 6. 报告 API

**修改位置：** `src/cscode/server/app.py`，新增路由

```python
@app.get("/sessions/{session_id}/verification-report")
async def get_verification_report(session_id: str):
    """返回基于数据库投影的验证报告，非 LLM 生成"""
    report = await _tracker.get_execution_report(session_id)

    # 计算 SKIPPED：用户要求的 task_ids 中不在投影表的
    all_expected = await _db.fetchall(
        "SELECT task_id FROM expected_tasks WHERE session_id = ?",
        (session_id,),
    )
    expected_ids = {r["task_id"] for r in all_expected}
    recorded_ids = {d["task_id"] for d in report["details"]}
    skipped = expected_ids - recorded_ids

    report["summary"]["skipped"] = len(skipped)
    report["details"].extend([
        {"task_id": tid, "status": "SKIPPED", "evidence": {}, "result_summary": "", "timestamp": None}
        for tid in skipped
    ])

    return report
```

## 7. 会话内容乱窜修复

**问题：** 当用户快速切换会话时，旧会话的 SSE 事件可能被应用到新激活的会话，导致内容串扰。

**根因：** `useChat.ts` 的 `isCurrent()` 只检查 `streamControllers[sid] === controller`，不检查 `activeSessionId`。当用户切换到新会话后，旧流的 controller 仍在 map 中，事件会错误地应用到当前激活的会话。

**修改位置：** `src/cscode/web/src/hooks/useChat.ts`，第 137 行

```typescript
// 修改前：
const isCurrent = () => streamControllers[sid] === controller;

// 修改后：
const isCurrent = () => {
  const activeId = useSessionStore.getState().activeSessionId;
  return streamControllers[sid] === controller && activeId === sid;
};
```

## 8. task_id 传递机制（完整数据流）

### 8.1 整体流程

```
LLM 调用 todowrite(id="TC001", ...)
    ↓
TodoWriteTool.execute() → INSERT INTO expected_tasks (session_id, task_id, description)
    ↓
LLM 调用 browser(action="screenshot", task_id="TC001")
    ↓
BrowserTool.execute() → 提取 task_id，注入 ToolResult.metadata
    ↓
engine.py 发送 tool.success 事件 → data 包含 task_id + evidence
    ↓
EventStore.append() → 写入 events 表（data 字段为 JSON）
    ↓
TaskTracker.on_tool_success() → 写入 task_verifications 投影表
```

### 8.2 关键决策

| 决策点 | 方案 | 理由 |
|--------|------|------|
| task_id 生成 | LLM 自己生成（如 TC-001） | 灵活，LLM 可按用例编号命名 |
| TodoWriteTool 注入 session_id | 通过构造函数注入 db 连接，从调用上下文获取 session_id | TodoWriteTool 本身不持有 session_id，需外部注入 |
| TodoWriteTool 注入 db | 构造函数注入 Database 实例 | 与现有架构一致（EventStore 同样注入 Database） |
| tool.success 事件扩展 | 修改 engine.py 的 _emit 调用，将 fn_args + metadata 传入 data | 现有事件只含 name + result[:200]，需扩展 |
| TaskTracker 获取 session_id | 从事件的 aggregate_id 提取 | EventStore 的 aggregate_id 即 session_id |

### 8.3 修改点

**todowrite.py — 注入 db + 同步写入 expected_tasks：**

```python
class TodoWriteTool(BaseTool):
    def __init__(self, db: Database | None = None):
        self._db = db

    async def execute(self, args: dict[str, Any], context: dict | None = None) -> ToolResult:
        todos = args["todos"]
        session_id = context.get("session_id", "") if context else ""
        # 同步写入 expected_tasks（如果有 db 连接）
        if self._db and session_id:
            for t in todos:
                task_id = t.get("id", "")
                if task_id:
                    await self._db.execute(
                        "INSERT OR IGNORE INTO expected_tasks (session_id, task_id, description) "
                        "VALUES (?, ?, ?)",
                        (session_id, task_id, t["content"])
                    )
        # ... 原有格式化逻辑
```

**注意：** `context` 参数需要 `ToolRegistry.execute_tool_call()` 支持传递上下文。修改 `tools/base.py`：

```python
# ToolRegistry 新增 context 参数
async def execute_tool_call(self, tool_call: dict[str, Any], context: dict | None = None) -> ToolResult:
    fn_info = tool_call.get("function", {})
    name = fn_info.get("name", "")
    raw_args = fn_info.get("arguments", "{}")
    if isinstance(raw_args, str):
        import json
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError as e:
            return ToolResult(success=False, data="", error=f"Failed to parse arguments for tool '{name}': {e}")
    else:
        args = raw_args

    tool = self.get(name)
    if tool is None:
        return ToolResult(success=False, data="", error=f"Unknown tool: {name}")
    
    # 传递 context 给工具（如果工具支持）
    import inspect
    sig = inspect.signature(tool.execute)
    if "context" in sig.parameters:
        return await tool.execute(args, context=context)
    return await tool.execute(args)
```

**engine.py 调用处传入 context：**

```python
# engine.py run_loop_events 中（约第 414 行）
context = {"session_id": aggregate_id}  # 从 engine 上下文获取
tool_result = await self.registry.execute_tool_call(tool_call, context=context)
```

**browser.py — 参数 schema 新增 task_id + execute 注入 metadata：**

```python
class BrowserTool(BaseTool):
    parameters = {
        "type": "object",
        "properties": {
            "action": {...},
            "task_id": {"type": "string", "description": "Optional test case ID for tracking"},
            # ... 其他字段不变
        },
        "required": ["action"],
    }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        task_id = args.get("task_id")
        # ... 原有执行逻辑 ...
        # 在返回前注入 evidence 到 metadata
        result.metadata["task_id"] = task_id or ""
        result.metadata["evidence"] = json.dumps({...})
        result.metadata["verified"] = str(verified)
        return result
```

**engine.py — tool.success 和 tool.failed 事件扩展（run_loop_events 方法，约第 414-418 行）：**

```python
# 修改前：
tool_result = await self.registry.execute_tool_call(tool_call)
if tool_result.success:
    await _emit({"type": "tool.success", "data": {"name": func_name, "result": (tool_result.data or "")[:200]}})
else:
    await _emit({"type": "tool.failed", "data": {"name": func_name, "error": (tool_result.error or "")[:200]}})

# 修改后：
context = {"session_id": aggregate_id}  # 从 engine 上下文获取
tool_result = await self.registry.execute_tool_call(tool_call, context=context)
if tool_result.success:
    await _emit({"type": "tool.success", "data": {
        "name": func_name,
        "result": (tool_result.data or "")[:200],
        "args": fn_args,                              # 包含 task_id
        "metadata": tool_result.metadata,              # 包含 evidence, verified
    }})
else:
    await _emit({"type": "tool.failed", "data": {
        "name": func_name,
        "error": (tool_result.error or "")[:200],
        "args": fn_args,                              # 包含 task_id
        "metadata": tool_result.metadata,
    }})
```

**注意：** `aggregate_id` 需要从 engine 上下文获取。`run_loop_events` 目前不持有 session_id，需要添加参数或从 messages 中提取。建议在 `Agent` 类中添加 `session_id` 属性，在 `app.py` 调用前设置。

```python
# Agent 类新增属性
class Agent:
    session_id: str = ""

# app.py 调用前设置
_agent.session_id = session_id
```

**TaskTracker 从事件提取数据：**

```python
async def on_tool_success(self, event: Event):
    """事件回调：tool.success → 写入投影表"""
    data = event.data
    args = data.get("args", {})
    metadata = data.get("metadata", {})
    
    task_id = args.get("task_id") or metadata.get("task_id", "unknown")
    if task_id == "unknown":
        return  # 非测试任务，跳过
    
    evidence = json.loads(metadata.get("evidence", "{}"))
    verified = metadata.get("verified") == "True"
    
    await self.db.execute(
        "INSERT OR REPLACE INTO task_verifications ...",
        [event.aggregate_id, task_id, data["name"], int(verified), ...]
    )

## 9. 实现优先级

| 优先级 | 任务 | 涉及文件 | 理由 |
|--------|------|---------|------|
| P0 | 修复会话内容乱窜 | `web/src/hooks/useChat.ts` | 阻塞用户体验，必须先解决 |
| P1 | 增强系统提示词 | `server/app.py` | 最简单，立即生效 |
| P1 | TaskTracker 投影器 | `core/tracker.py`（新增） | 核心追踪能力 |
| P1 | 数据库迁移 v005（新增表） | `storage/db.py` | task_verifications + expected_tasks 表 |
| P1 | TodoWrite 注入 db + context 传递 | `tools/todowrite.py`, `tools/base.py`, `core/engine.py` | task_id 传递桥梁 |
| P2 | Browser 工具 evidence + task_id | `tools/browser.py` | 参数 schema + execute 修改 |
| P2 | Bash 工具 evidence + task_id | `tools/bash.py` | 参数 schema + execute 修改 |
| P2 | engine.py tool.success/failed 事件扩展 | `core/engine.py` | 传递 args + metadata 到事件 |
| P2 | 报告 API | `server/app.py` | 依赖 TaskTracker |
| P2 | TaskTracker 集成（on_event 回调） | `server/app.py` | 在现有 on_event 中调用 tracker |

## 10. 潜在风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM 不生成 task_id | 追踪失败，工具调用不记录 | 系统提示词强制要求；缺少 task_id 的工具调用跳过不记录 |
| task_id 格式不统一 | 报告混乱 | 系统提示词强制 TC-XXX 格式 |
| task_id 重复 | 数据覆盖 | UNIQUE(session_id, task_id, tool_name) + INSERT OR REPLACE |
| 截图/HTML 为空 | 验证失败 | 标记为 UNVERIFIED，提示重新执行 |
| 大量事件影响性能 | 查询变慢 | status 索引 + 截图存文件系统 + 定期归档 |
| tool.failed 丢失追踪 | 失败用例无记录 | tool.failed 事件同样携带 task_id，写入 status=FAILED |
| TodoWriteTool 无 session_id | expected_tasks 写入失败 | 通过 ToolRegistry context 参数传递 |
| 截图文件跨会话冲突 | 后一个会话覆盖前一个的截图 | 文件名格式 `{session_id}_{task_id}_screenshot.png` |
| `get_execution_report` 同步/异步不一致 | 运行时 `await` 调用同步方法会崩溃 | 改为 `async def`，API 调用加 `await` |
| 证据目录未预创建 | 截图操作找不到目录 | app.py 启动时 `os.makedirs(EVIDENCE_DIR, exist_ok=True)` |

## 11. 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| 1 | **禁止推断：** LLM 无法在没有工具调用的情况下声称测试通过 | 系统提示词约束 + 报告来自数据库 |
| 2 | **证据强制：** 浏览器测试必须有截图 + HTML 才算 EXECUTED | `_verify_evidence()` 双重检查 |
| 3 | **报告可信：** 报告 API 返回的数据来自数据库，不是 LLM 文本 | GET /sessions/{id}/verification-report 直接查表 |
| 4 | **可审计：** 每个测试用例的执行状态可追溯到 task_verifications 表 | 数据库查询可验证 |
| 5 | **会话隔离：** 切换会话时内容不串扰 | isCurrent() 增加 activeSessionId 检查 |
| 6 | **持久化：** 服务重启后验证记录不丢失 | SQLite 持久化存储 |
| 7 | **任务追踪完整性：** 所有带 task_id 的工具调用都能在 task_verifications 表中找到记录 | 端到端测试验证 |
| 8 | **验证准确性：** 空结果的工具调用被正确标记为 UNVERIFIED | 单元测试验证 |
| 9 | **失败追踪：** tool.failed 事件同样记录到投影表，status=FAILED | 单元测试验证 |
| 10 | **性能：** 1000 条验证记录查询时间 < 100ms | 索引优化 + 性能测试 |
