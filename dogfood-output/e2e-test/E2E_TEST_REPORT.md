# CScode 企业级端到端测试报告

**测试时间**: 2026-07-09
**测试方式**: Playwright 自动化 + 截图分析 + 代码审查
**测试环境**: http://localhost:8000
**AI 模型**: MiniMax-M2.5 (custom)
**测试目标**: 覆盖所有 GUI 功能，验证数据一致性，发现潜在问题

---

## 一、测试总结

| 指标 | 数值 |
|------|------|
| 测试用例数 | 10 个 |
| 功能模块覆盖 | 15+ 个 |
| 截图证据 | 15 张 |
| 发现问题数 | 5 个 |
| P0 阻断性 | 1 个 |
| P1 严重 | 2 个 |
| P2 一般 | 2 个 |

---

## 二、测试结果概览

### ✅ 通过的测试

| 测试项 | 状态 | 说明 |
|--------|------|------|
| 应用加载 | ✅ | 正常加载，标题正确显示 |
| 元素可见性 | ✅ | 输入框、新建会话、设置按钮均可见 |
| 会话创建 | ✅ | 点击后成功创建新会话 |
| 会话切换 | ✅ | 可以在会话之间切换 |
| 消息输入 | ✅ | 输入框正常接收文本 |
| 消息发送 | ✅ | Enter 发送消息成功 |
| LLM 响应 | ✅ | MiniMax-M2.5 正常响应 |
| 中文支持 | ✅ | 中文输入和显示正常 |
| 设置面板 | ✅ | 打开/关闭正常 |
| 模式切换 | ✅ | Plan/Build 切换正常 |

---

## 三、发现的问题

### ISSUE-001: P0 - Session 切换导致消息丢失（架构级 Bug）

**严重程度**: P0 - 阻断性
**影响场景**: 多 Session 并行执行时用户切换 Session

**问题描述**:
两个 session 并行执行任务时，用户手动点击左侧 session 栏切换观察不同 session 的任务进展，切换过程中 session 中 LLM 的反馈信息被清除。

**根因分析**:

这是架构级设计缺陷，涉及 5 个代码问题：

| # | 问题 | 位置 |
|---|------|------|
| 1 | `setMessages` 直接替换消息列表（无合并） | useSessionStore.ts:339-354 |
| 2 | `setMessages` 不更新 `sessionMessageVersion` | useSessionStore.ts:339-354 |
| 3 | `applyEvent` 不更新 `sessionMessageVersion` | useSessionStore.ts:166-313 |
| 4 | Version Guard 形同虚设 | Sidebar.tsx:54-58 |
| 5 | catch 分支直接清空消息 | Sidebar.tsx:64-75 |

**触发时序**:
```
Session A 正在接收 LLM 流式响应
  -> applyEvent('text.delta') 更新消息（但不更新 version）
用户切换回 Session A
  -> handleSelectSession() 发起 api.session.messages()
  -> 服务器返回旧消息（不包含流式中的内容）
  -> Version Guard 因 version 未变而失效
  -> setMessages() 直接替换消息列表
  -> 本地累积的流式消息被覆盖！
```

**修复建议**:
1. 让 `applyEvent` 和 `setMessages` 正确更新 `sessionMessageVersion`
2. 或将 `setMessages` 改为合并逻辑，保留本地有但服务器没有的消息

**相关代码**:
- [useSessionStore.ts:166-313](file:///Users/mac/AI/CScode/src/cscode/web/src/stores/useSessionStore.ts#L166-L313)
- [useSessionStore.ts:339-354](file:///Users/mac/AI/CScode/src/cscode/web/src/stores/useSessionStore.ts#L339-L354)
- [Sidebar.tsx:54-58](file:///Users/mac/AI/CScode/src/cscode/web/src/components/layout/Sidebar.tsx#L54-L58)
- [Sidebar.tsx:64-75](file:///Users/mac/AI/CScode/src/cscode/web/src/components/layout/Sidebar.tsx#L64-L75)

**详细分析报告**: [SESSION_SWITCH_BUG_REPORT.md](file:///Users/mac/AI/CScode/dogfood-output/SESSION_SWITCH_BUG_REPORT.md)

---

### ISSUE-002: P1 - Share API 路径重复前缀 (404)

**严重程度**: P1 - 严重
**影响功能**: 会话分享功能完全不可用

**问题描述**:
前端调用 `GET /api/share` 返回 404 Not Found。

**根因**:
后端 `api_router` 已配置 `prefix="/api"`，但 share 相关路由又写了 `/api/share` 前缀，导致实际路径变成 `/api/api/share`。

**受影响路由**:
- `GET /api/share` → `/api/api/share` (404)
- `POST /api/share` → `/api/api/share` (404)
- `GET /api/share/{share_id}` → `/api/api/share/{share_id}` (404)
- `DELETE /api/share/{share_id}` → `/api/api/share/{share_id}` (404)

**位置**: [app.py:1284-1340](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L1284-L1340)

**修复建议**:
将路由路径中的 `/api/` 前缀去掉：
```python
# 错误写法
@api_router.get("/api/share")

# 正确写法
@api_router.get("/share")
```

---

### ISSUE-003: P1 - Share API 500 错误 (Database 未初始化)

**严重程度**: P1 - 严重
**影响功能**: 即使路径正确，分享功能也报错

**问题描述**:
每次请求都创建新的 `Database()` 对象，但没有调用 `await db.init()`，导致 `self.conn` 未初始化。

**错误堆栈**:
```
AttributeError: 'Database' object has no attribute 'conn'
```

**位置**: [app.py:1284-1340](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L1284-L1340)

**修复建议**:
在 lifespan 中初始化全局 `_share_store`，或使用全局 `_db` 对象。

---

### ISSUE-004: P2 - 面板初始化静默失败

**严重程度**: P2 - 一般
**影响功能**: 用户无法知道功能是否正常

**问题描述**:
`ShareDialog.tsx`、`CredentialPanel.tsx`、`SyncPanel.tsx` 在初始化失败时静默忽略错误：

```typescript
try {
    const data = await request('/api/...');
} catch {
    // 静默忽略
}
```

**影响位置**:
- [ShareDialog.tsx:28-34](file:///Users/mac/AI/CScode/src/cscode/web/src/components/ShareDialog.tsx#L28-L34)
- [CredentialPanel.tsx:31-37](file:///Users/mac/AI/CScode/src/cscode/web/src/components/CredentialPanel.tsx#L31-L37)
- [SyncPanel.tsx:29-37](file:///Users/mac/AI/CScode/src/cscode/web/src/components/SyncPanel.tsx#L29-L37)

---

### ISSUE-005: P2 - 侧边栏会话列表显示问题

**严重程度**: P2 - 一般
**影响体验**: 会话列表显示混乱

**问题描述**:
从截图可以看到侧边栏存在多个 "New Session" 条目，缺乏自动命名或时间戳组织，用户难以区分。

**建议改进**:
- 添加会话自动命名（基于首个问题或时间）
- 添加时间戳或日期分组
- 添加会话搜索功能

---

## 四、截图证据

| 截图 | 说明 |
|------|------|
| [01-initial-load.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/01-initial-load.png) | 应用初始加载 |
| [02-new-session.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/02-new-session.png) | 创建新会话 |
| [03-session-switch.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/03-session-switch.png) | 会话切换 |
| [04-input-message.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/04-input-message.png) | 输入消息 |
| [05-message-sent.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/05-message-sent.png) | 消息发送成功，LLM Thinking |
| [06-llm-response.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/06-llm-response.png) | LLM 响应中 |
| [07-session-a-before-switch.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/07-session-a-before-switch.png) | Session A 切换前 |
| [09-session-a-after-switch.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/09-session-a-after-switch.png) | Session A 切换后 |
| [10-export.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/10-export.png) | 导出功能 |
| [11-settings-panel.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/11-settings-panel.png) | 设置面板 |
| [12-mode-toggle.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/12-mode-toggle.png) | 模式切换 |
| [13-concurrent-sessions.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/13-concurrent-sessions.png) | 并发 Session |
| [14-keyboard-shortcuts.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/14-keyboard-shortcuts.png) | 键盘快捷键 |
| [15-chinese-support.png](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/screenshots/15-chinese-support.png) | 中文支持 |

---

## 五、功能模块测试详情

### 5.1 会话管理

| 功能 | 状态 | 说明 |
|------|------|------|
| 创建会话 | ✅ | 点击 + 按钮创建新会话 |
| 切换会话 | ✅ | 点击会话项切换 |
| 删除会话 | ⚠️ | hover 显示删除按钮，但未测试实际删除 |
| 导出会话 | ✅ | 导出功能正常 |
| 会话重命名 | ⚠️ | 未测试 |

### 5.2 聊天功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 输入消息 | ✅ | 输入框正常工作 |
| 发送消息 | ✅ | Enter 发送成功 |
| LLM 响应 | ✅ | MiniMax-M2.5 正常响应 |
| 流式显示 | ✅ | "Thinking..." 动画显示 |
| 消息持久化 | ⚠️ | 需要验证刷新后消息是否保留 |

### 5.3 设置面板

| 功能 | 状态 | 说明 |
|------|------|------|
| 打开设置 | ✅ | 点击 Settings 按钮 |
| Provider 选择 | ✅ | 下拉选择正常 |
| API Key 输入 | ✅ | 密码框正常 |
| 保存设置 | ⚠️ | 未测试保存功能 |
| 关闭设置 | ✅ | 关闭按钮正常 |

### 5.4 模式切换

| 功能 | 状态 | 说明 |
|------|------|------|
| Plan 模式 | ✅ | 切换正常 |
| Build 模式 | ✅ | 切换正常 |

### 5.5 中文支持

| 功能 | 状态 | 说明 |
|------|------|------|
| 中文输入 | ✅ | 输入框支持中文 |
| 中文显示 | ✅ | 消息正常显示中文 |
| 中文会话导出 | ✅ | 导出功能支持中文标题 |

---

## 六、建议优先级

### 高优先级（立即修复）

1. **ISSUE-001**: 修复 Session 切换数据丢失问题 — 影响核心使用场景
2. **ISSUE-002**: 修复 Share API 路径重复前缀 — 影响分享功能可用性
3. **ISSUE-003**: 修复 Share API Database 未初始化 — 影响分享功能可用性

### 中优先级

4. **ISSUE-004**: 添加面板错误提示 — 当前静默失败，用户无感知
5. **ISSUE-005**: 改进会话列表显示 — 提升用户体验

---

## 七、测试产出物

| 文件 | 说明 |
|------|------|
| [e2e-test-report.json](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/e2e-test-report.json) | 测试结果 JSON |
| [e2e_full_test.py](file:///Users/mac/AI/CScode/dogfood-output/e2e-test/e2e_full_test.py) | 测试脚本 |
| `screenshots/` | 15 张测试截图 |
| [SESSION_SWITCH_BUG_REPORT.md](file:///Users/mac/AI/CScode/dogfood-output/SESSION_SWITCH_BUG_REPORT.md) | Session 切换 Bug 详细分析 |

---

## 八、结论

### 核心发现

1. **Session 切换数据丢失是架构级设计缺陷** — Version Guard 机制未正确实现
2. **Share API 存在两个严重问题** — 路径前缀重复 + Database 未初始化
3. **核心聊天功能正常** — MiniMax-M2.5 响应正常，流式显示正常
4. **中文支持良好** — 输入、显示、导出均正常

### 建议修复顺序

1. 先修复 ISSUE-001（Session 切换数据丢失）— 需要重构 Version Guard 机制
2. 再修复 ISSUE-002 和 ISSUE-003（Share API）— 路由和初始化问题
3. 最后处理 P2 问题（错误提示、UI 改进）

---

*报告生成时间: 2026-07-09*