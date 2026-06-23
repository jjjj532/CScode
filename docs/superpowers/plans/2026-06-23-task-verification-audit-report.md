# CScode 任务验证与追踪机制 - 审核报告

**审核对象：**
1. [openspec/specs/cscode-task-verification.md](file:///Users/mac/AI/CScode/openspec/specs/cscode-task-verification.md) - 技术规格文档
2. [docs/superpowers/plans/2026-06-23-task-verification-plan.md](file:///Users/mac/AI/CScode/docs/superpowers/plans/2026-06-23-task-verification-plan.md) - 实现计划文档

**审核日期：** 2026-06-23

**审核状态：** 需要修正后执行

---

## 一、整体评价

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构设计 | ✅ 优秀 | 四层架构清晰，事件溯源模式正确 |
| 数据流设计 | ✅ 优秀 | task_id 贯穿全链路，证据链完整 |
| 优先级划分 | ✅ 合理 | P0/P1/P2 分层清晰 |
| 测试覆盖 | ✅ 良好 | TDD 模式，单元测试覆盖关键逻辑 |
| 实现一致性 | ⚠️ 需要修正 | Spec 与 Plan 存在 4 处关键差异 |

---

## 二、Spec 审查

### 2.1 架构设计 ✅

```
系统提示词层 → 工具执行层 → 事件存储层 → TaskTracker 投影层 → 报告生成层
```

**优点：**
- 层次分明，职责清晰
- 报告数据来自数据库投影，而非 LLM 文本，确保可信度
- 证据链完整：task_id → 工具执行 → 事件存储 → 投影表 → 报告

### 2.2 数据模型 ✅

| 表名 | 用途 | 设计 |
|------|------|------|
| `task_verifications` | 记录工具执行验证结果 | ✅ 包含 status、verified、evidence |
| `expected_tasks` | 记录用户预期任务列表 | ✅ 支持 SKIPPED 计算 |

**证据存储策略：** ✅ 截图存文件系统，数据库只存路径，避免表膨胀

### 2.3 核心逻辑 ✅

**验证规则设计合理：**
- Browser: 必须同时有 `screenshot_path` AND `html=True`
- Bash: `content_length > 0`

**关键决策：**
- task_id 由 LLM 生成（TC-XXX 格式）
- TodoWriteTool 通过 context 传递 session_id
- TaskTracker 通过 on_event 回调集成

---

## 三、Plan 审查

### 3.1 任务结构 ✅

| 优先级 | 任务数量 | 内容 |
|--------|---------|------|
| P0 | 1 | 修复会话内容乱窜 |
| P1 | 5 | 数据库迁移、TaskTracker、上下文传递、TodoWriteTool、系统提示词 |
| P2 | 6 | 工具证据注入、事件扩展、报告 API、最终验证 |

**优点：**
- 测试驱动开发（Task 3 先写测试再实现）
- 每个任务包含验证步骤和 commit 规范
- 最终验证阶段包含 lint 和构建检查

### 3.2 需要修正的问题

#### 问题 1：`get_execution_report` 同步/异步不一致 ❌

| 文件 | 定义 | 问题 |
|------|------|------|
| Plan Task 3 | `def get_execution_report(...)` | 同步方法 |
| Plan Task 11 | `await _tracker.get_execution_report(session_id)` | 调用时 await |

**影响：** 运行时会崩溃

**修正方案：** 将 Task 3 中的定义改为 `async def`

#### 问题 2：Browser 工具验证规则矛盾 ❌

**验证规则（Task 3）：**
```python
if tool == "browser":
    return bool(evidence.get("screenshot_path")) and evidence.get("html", False)
```

**Browser 工具实现（Task 8）：**
- `screenshot` action: 只设置 `screenshot_path`，不设置 `html=True`
- `get_text` action: 只设置 `html=True`，不设置 `screenshot_path`

**影响：** 浏览器操作永远无法通过验证，全部标记为 UNVERIFIED

**修正方案：** 每个浏览器 action 都需同时设置 `screenshot_path` 和 `html=True`

#### 问题 3：截图表名缺少 session_id ⚠️

| 文件 | 格式 |
|------|------|
| Spec | `{session_id}_{task_id}_screenshot.png` |
| Plan Task 8 | `{task_id}_screenshot.png` |

**风险：** 跨会话的相同 task_id 会覆盖截图文件

**修正方案：** 采用 Spec 格式，包含 session_id

#### 问题 4：EVIDENCE_DIR 预创建缺失 ⚠️

**Spec 要求：** 在 `app.py` 启动时预创建 `/tmp/cscode-outputs/evidence/`

**Plan 状态：** 未包含此步骤

**风险：** 截图操作可能因目录不存在而失败

**修正方案：** 在 Task 11 Step 1 添加目录预创建

---

## 四、一致性对比

| 检查项 | Spec | Plan | 状态 |
|--------|------|------|------|
| TaskTracker 集成方式 | on_event 回调 | ✅ 相同 | ✅ |
| task_id 传递路径 | LLM → 工具 → 事件 → 投影表 | ✅ 相同 | ✅ |
| 验证规则 | Browser 需要截图 + HTML | ❌ 不一致 | ⚠️ |
| 证据目录 | app.py 启动时创建 | ❌ 缺失 | ⚠️ |
| get_execution_report | async | sync | ❌ |
| 截图表名格式 | {session_id}_{task_id}_screenshot.png | {task_id}_screenshot.png | ❌ |

---

## 五、修正建议

### 5.1 修改 Task 3 - TaskTracker 实现

将 `get_execution_report` 改为异步方法：

```python
async def get_execution_report(self, session_id: str) -> dict:
    """查询会话的验证报告"""
    rows = await self.db.fetchall(
        "SELECT task_id, status, verified, evidence, result_summary, created_at "
        "FROM task_verifications WHERE session_id = ? ORDER BY created_at",
        (session_id,),
    )
    # ... 后续逻辑不变
```

### 5.2 修改 Task 8 - Browser 工具

确保每个 action 返回时都设置完整的 evidence：

```python
# 所有 action 统一构建 evidence
evidence = {
    "screenshot_path": screenshot_path if action == "screenshot" else "",
    "html": bool(result.data) if action in ("get_html", "get_text") else False,
    "html_length": len(result.data) if action in ("get_html", "get_text") else 0,
    "content_length": len(result.data),
    "timestamp": datetime.now(timezone.utc).isoformat(),
}

# 验证逻辑调整：允许单一 action 通过验证
verified = bool(evidence["screenshot_path"]) or evidence.get("html", False)
```

### 5.3 修改 Task 8 - 截图表名

```python
if task_id and session_id:
    evidence_path = os.path.join(EVIDENCE_DIR, f"{session_id}_{task_id}_screenshot.png")
```

### 5.4 修改 Task 11 - 添加证据目录预创建

```python
# 在 app.py 启动时，/tmp/cscode-outputs 创建之后
EVIDENCE_DIR = "/tmp/cscode-outputs/evidence"
os.makedirs(EVIDENCE_DIR, exist_ok=True)
```

---

## 六、风险评估

| 风险 | 严重程度 | 关联任务 | 缓解措施 |
|------|---------|---------|---------|
| get_execution_report 同步/异步错误 | 🔴 高 | Task 3, Task 11 | 修正为 async def |
| Browser 验证失败 | 🔴 高 | Task 3, Task 8 | 统一验证规则 |
| 截图文件冲突 | 🟡 中 | Task 8 | 添加 session_id 到文件名 |
| 证据目录不存在 | 🟡 中 | Task 11 | 启动时预创建 |
| 数据库迁移失败 | 🟡 中 | Task 2 | 迁移前备份 |

---

## 七、验收标准对照表

| # | 标准 | 关联任务 | 状态 |
|---|------|---------|------|
| 1 | 禁止推断：LLM 无法声称未执行的测试通过 | Task 7 | ✅ |
| 2 | 证据强制：浏览器测试必须有截图 + HTML | Task 3, Task 8 | ⚠️ 需要修正 |
| 3 | 报告可信：数据来自数据库而非 LLM | Task 11 | ✅ |
| 4 | 可审计：每个用例可追溯到投影表 | Task 3 | ✅ |
| 5 | 会话隔离：切换会话内容不串扰 | Task 1 | ✅ |
| 6 | 持久化：服务重启后记录不丢失 | Task 2 | ✅ |

---

## 八、审核结论

**整体可行性：** ✅ 高

**执行建议：**
1. **立即修正**：问题 1、问题 2（会导致功能完全失效）
2. **建议修正**：问题 3、问题 4（防止潜在问题）
3. 修正完成后按 P0→P1→P2 顺序执行

**审核人：** AI Assistant
**审核日期：** 2026-06-23