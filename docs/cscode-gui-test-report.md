# CScode GUI 功能测试报告

**测试日期**: 2026-06-30
**测试环境**: macOS + Tauri 桌面应用 / React Web 前端
**测试版本**: v0.2.x
**测试范围**: GUI 全部功能、前后端接口联调、事件流处理

---

## 1. 测试概述

本次测试对 CScode 重构后的版本进行了全面的 GUI 功能测试，覆盖了所有可见按钮和交互元素，并结合后端日志深入分析了前后端接口联调情况。测试对照 opencode 架构和 CScode 技术规格书，识别功能差距和缺陷。

### 1.1 测试方法

- **GUI 黑盒测试**: 模拟用户操作，点击所有可见按钮和交互元素
- **接口联调测试**: 通过浏览器开发者工具监控网络请求，验证前后端交互
- **日志分析**: 结合后端诊断日志（`/tmp/cscode-diag.log`）定位问题根因
- **架构对比**: 对照 opencode 源码和技术规格书，识别缺失功能

### 1.2 测试环境

- **后端**: FastAPI + uvicorn (端口 8765)
- **前端**: React 18 + TypeScript + Vite (开发端口 5173)
- **数据库**: SQLite + WAL 模式
- **LLM Provider**: scnet / MiniMax-M2.5

---

## 2. 问题汇总

### 2.1 按严重程度分类

| 严重级别 | 数量 | 说明 |
|---------|------|------|
| P0 - 致命 | 5 | 核心功能不可用，阻塞主流程 |
| P1 - 重要 | 6 | 重要功能缺陷，严重影响体验 |
| P2 - 一般 | 6 | 架构缺失或体验优化项 |
| **合计** | **17** | |

### 2.2 按模块分类

| 模块 | P0 | P1 | P2 | 合计 |
|------|----|----|----|------|
| 会话管理 | 2 | 2 | 2 | 6 |
| 事件流系统 | 2 | 1 | 0 | 3 |
| API 接口 | 1 | 3 | 3 | 7 |
| UI 交互 | 1 | 0 | 1 | 2 |
| 主题系统 | 0 | 1 | 0 | 1 |
| 配置系统 | 0 | 1 | 1 | 2 |
| 权限系统 | 0 | 1 | 1 | 2 |

---

## 3. P0 级 - 致命问题

### P0-1: 缺少会话消息加载 API（`/api/sessions/{id}/messages`）

**严重级别**: P0  
**模块**: 会话管理 / API 接口

#### 现象描述
点击侧边栏中的历史会话后，主区域消息列表始终为空，无法加载历史消息。

#### 复现步骤
1. 打开应用，创建一个新会话并发送消息
2. 再创建第二个新会话
3. 在侧边栏点击第一个会话
4. 观察主区域：消息列表为空

#### 根因分析
- 前端 [Sidebar.tsx](file:///Users/mac/AI/CScode/src/cscode/web/src/components/layout/Sidebar.tsx#L55) 中 `handleSelectSession` 函数调用 `api.sessions.messages(id)`
- 该 API 对应后端路径 `GET /api/sessions/{id}/messages`
- 后端 [app.py](file:///Users/mac/AI/CScode/src/cscode/server/app.py) 完全没有实现该接口
- 请求返回 404 Not Found

#### 日志证据
```
[sidebar] fetch failed for session=...
GET /api/sessions/xxx/messages 404 Not Found
```

#### OpenCode 对比
opencode 实现了完整的消息 API：
- `GET /api/session/:sessionID/message` - 获取会话消息列表
- 路径：[message.ts](file:///Users/mac/AI/CScode/github/opencode-full/packages/protocol/src/groups/message.ts#L26)

#### 影响范围
- 用户无法查看历史会话记录
- 会话切换功能完全失效
- 多会话并行体验无从谈起

---

### P0-2: 缺少问题（Question）相关 API

**严重级别**: P0  
**模块**: 权限系统 / API 接口

#### 现象描述
QuestionDialog 组件无法正常工作，权限确认、用户输入问询等功能完全不可用。

#### 根因分析
前端 [QuestionDialog.tsx](file:///Users/mac/AI/CScode/src/cscode/web/src/components/ui/QuestionDialog.tsx#L60) 调用了以下 API，但后端均未实现：

| API 方法 | 路径 | 用途 |
|---------|------|------|
| GET | `/api/sessions/{id}/questions` | 获取待回答问题列表 |
| POST | `/api/sessions/{id}/questions/{requestId}/reply` | 回复问题 |
| POST | `/api/sessions/{id}/questions/{requestId}/reject` | 拒绝问题 |

#### OpenCode 对比
opencode 有完整的 question group：
- 路径：[question.ts](file:///Users/mac/AI/CScode/github/opencode-full/packages/protocol/src/groups/question.ts)
- 包含 list / reply / reject 等完整端点

#### 影响范围
- 工具调用时的权限确认弹窗无法显示
- 需要用户输入的功能无法工作
- 安全防线缺失，所有工具调用自动执行

---

### P0-3: 流式事件系统不完整 - 缺少 `step.started` 等关键事件

**严重级别**: P0  
**模块**: 事件流系统

#### 现象描述
发送消息后，UI 直接跳到完整回复，没有"思考中"状态，也没有流式打字效果。用户等待期间没有任何反馈。

#### 复现步骤
1. 在输入框输入消息并发送
2. 观察 UI 变化：
   - 没有"AI 正在思考..."的提示
   - 没有逐步打字的效果
   - 数秒后直接显示完整回复

#### 根因分析
后端 `_llm_event_to_dict` 函数（[app.py#L62-L78](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L62-L78)）只处理了以下 6 种事件：

```python
def _llm_event_to_dict(event: LLMEvent) -> dict:
    if isinstance(event, TextDeltaEvent):
        return {"type": "text.delta", "content": event.content}
    elif isinstance(event, TextEndedEvent):
        return {"type": "text.ended", "content": event.content}
    elif isinstance(event, ToolCallStartedEvent):
        return {"type": "tool_call.started", ...}
    elif isinstance(event, ToolCallDeltaEvent):
        return {"type": "tool_call.delta", ...}
    elif isinstance(event, ToolCallEndedEvent):
        return {"type": "tool_call.ended", ...}
    elif isinstance(event, ToolResultEvent):
        return {"type": "tool.result", ...}
```

**缺失的关键事件**:
- `step.started` - 思考步骤开始（用于显示"思考中"状态）
- `step.ended` - 思考步骤结束
- `usage` - token 使用统计
- `error` - 错误事件

前端 [useChat.ts](file:///Users/mac/AI/CScode/src/cscode/web/src/hooks/useChat.ts#L151-L160) 和 [useSessionStore.ts](file:///Users/mac/AI/CScode/src/cscode/web/src/stores/useSessionStore.ts#L167) 中的 `applyEvent` 函数虽然定义了对各种事件的处理，但由于后端不发送这些事件，相关逻辑永远不会执行。

#### 日志证据
前端日志只有 `appendMessage` 调用，没有 `applyEvent` 的逐步调用。

#### 影响范围
- 用户体验极差，等待期间无任何反馈
- 无法感知 AI 是否在正常工作
- 流式交互的核心价值丧失

---

### P0-4: 移动端侧边栏遮罩层挡住发送按钮

**严重级别**: P0  
**模块**: UI 交互

#### 现象描述
在移动端宽度（< 768px）下，侧边栏打开时发送按钮无法点击，点击被遮罩层拦截。

#### 复现步骤
1. 将浏览器窗口调整到移动端宽度（或使用移动设备）
2. 打开侧边栏（点击汉堡菜单按钮）
3. 尝试点击底部的发送按钮
4. 按钮无响应，点击被拦截

#### 根因分析
[Sidebar.tsx](file:///Users/mac/AI/CScode/src/cscode/web/src/components/layout/Sidebar.tsx#L138-L140) 中的遮罩层：

```tsx
{isOpen && (
  <div 
    className="fixed inset-0 z-20 bg-black/30 md:hidden"
    onClick={onClose}
  />
)}
```

- `fixed inset-0` 使遮罩层覆盖整个视口
- `z-20` 的层级高于聊天输入区域
- 虽然设置了 `md:hidden`，但在移动端侧边栏打开时，遮罩层会挡住底部的发送按钮

#### 测试证据
```
browser_click 失败: Click target intercepted
拦截元素: <div class="fixed inset-0 z-20 bg-black/30">
```

#### 影响范围
- 移动端用户无法发送消息
- 核心功能在移动设备上不可用

---

### P0-5: 事件数据结构不匹配 - `event.data` vs 直接字段

**严重级别**: P0  
**模块**: 事件流系统

#### 现象描述
前端 `applyEvent` 函数可能无法正确读取事件数据，导致 UI 状态更新异常。

#### 根因分析
**前端期望的数据结构**（[useSessionStore.ts](file:///Users/mac/AI/CScode/src/cscode/web/src/stores/useSessionStore.ts#L167)）：
```typescript
case 'text.delta':
  state.messages[state.messages.length - 1].content += event.data.content;
  break;
```
前端通过 `event.data.xxx` 访问事件数据。

**后端实际发送的数据结构**（[app.py#L62-L78](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L62-L78)）：
```python
{"type": "text.delta", "content": event.content}
```
后端把数据字段直接放在顶层，没有嵌套在 `data` 中。

**矛盾的持久化代码**（[app.py#L228-L245](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L228-L245)）：
```python
async def on_event(sse_event: dict, session_id: str):
    event_type = sse_event.get("type", "")
    if event_type in PERSIST_EVENT_TYPES:
        event_data = sse_event.get("data", {})  # 这里又用了 data 字段
```

这说明后端内部对事件数据结构的认知也不一致。

#### 影响范围
- 事件处理链路断裂
- UI 状态可能无法正确更新
- 持久化逻辑可能存储空数据

---

## 4. P1 级 - 重要问题

### P1-1: 主题系统错误 - `exportedColors` undefined

**严重级别**: P1  
**模块**: 主题系统

#### 现象描述
浏览器控制台报错：
```
[getThemeColors] TypeError: Cannot destructure property 'exportedColors' of 'undefined' as it is undefined.
```

#### 根因分析
ThemeProvider 或主题配置文件中 `getThemeColors` 函数的输入参数为 undefined，可能是：
- 主题配置文件加载失败
- 默认主题未正确设置
- 主题切换时状态未正确初始化

#### 影响范围
- 主题切换可能部分失效
- 控制台报错影响开发调试
- 可能导致某些 UI 组件样式异常

---

### P1-2: 缺少会话上下文 API（`/api/sessions/{id}/context`）

**严重级别**: P1  
**模块**: 会话管理 / API 接口

#### 问题描述
前端需要获取当前会话的活动上下文消息（经过压缩/裁剪后的），但后端没有提供该 API。

#### OpenCode 对比
opencode 实现了：
- `GET /api/session/:sessionID/context` - 返回活动上下文消息列表

#### 影响范围
- 前端无法显示当前上下文中实际发送给 LLM 的消息
- 调试和排查上下文问题困难

---

### P1-3: 缺少会话事件订阅 API（`/api/sessions/{id}/events`）

**严重级别**: P1  
**模块**: 会话管理 / API 接口

#### 问题描述
虽然后端有 `/api/events` SSE 端点，但路径和参数格式与前端期望的不一致，也不支持按会话订阅。

#### OpenCode 对比
opencode 实现了：
- `GET /api/session/:sessionID/event` - 会话级 SSE 事件订阅
- 支持实时推送该会话的所有事件

#### 影响范围
- 多标签页同步功能不可用
- 实时事件推送机制不完善

---

### P1-4: 中断/停止会话功能不完善

**严重级别**: P1  
**模块**: 会话管理 / API 接口

#### 现象描述
点击停止按钮后，LLM 请求可能仍在后台继续运行，没有真正中断。

#### 根因分析
后端 [app.py#L798-L808](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L798-L808) 的 `stop_session` 实现：

```python
@app.post("/api/sessions/{session_id}/stop")
async def stop_session(session_id: str):
    if session_id in _active_agent_tasks:
        task = _active_agent_tasks[session_id]
        task.cancel()
        del _active_agent_tasks[session_id]
    return {"ok": True}
```

**问题**:
1. 只取消了 Python 层面的 asyncio task
2. 没有真正中断底层的 HTTP 请求（httpx 请求可能仍在进行）
3. 没有清理 Question 等相关状态
4. 没有触发 `step.ended` 或 `error` 事件通知前端

#### OpenCode 对比
opencode 有 `session.interrupt` 端点，会完整中断执行链，包括：
- 中断 LLM 请求
- 中断工具执行
- 清理状态
- 发送中断事件

#### 影响范围
- 用户点击停止后，后台仍在消耗 token
- 停止响应不及时

---

### P1-5: 缺少 Agent/Model 切换 API

**严重级别**: P1  
**模块**: 会话管理 / API 接口

#### 问题描述
无法在会话中切换模型或 Agent 配置。

#### OpenCode 对比
opencode 实现了：
- `POST /api/session/:sessionID/agent` - 切换 Agent
- `POST /api/session/:sessionID/model` - 切换模型

#### 影响范围
- 用户无法在对话中途切换模型
- 多 Agent 协作功能无法实现

---

### P1-6: 会话消息持久化不完善

**严重级别**: P1  
**模块**: 会话管理

#### 问题描述
虽然有 EventStore 事件存储，但消息事件持久化不完整。

#### 根因分析
1. `PERSIST_EVENT_TYPES` 只包含 6 种事件类型
2. `text.delta` 等流式事件不持久化（这是合理的，因为有 text.ended）
3. 但持久化逻辑使用 `sse_event.get("data", {})` 读取数据，而事件数据在顶层（见 P0-5）
4. 可能导致持久化的数据为空

#### 影响范围
- 刷新页面后消息历史可能丢失
- 重新加载会话时消息不完整

---

## 5. P2 级 - 一般问题

### P2-1: API 路径命名不一致

**严重级别**: P2  
**模块**: API 接口

#### 问题描述
API 路径命名风格不统一：
- 前端部分用 `/api/sessions` (复数)
- opencode 用 `/api/session` (单数)
- 后端混合使用两种风格

#### 影响范围
- 维护困难，容易出错
- 新接入功能时需要反复确认路径

---

### P2-2: 配置系统不完整

**严重级别**: P2  
**模块**: 配置系统

#### 问题描述
配置项只有基本的 provider/model/api_key 等，缺少很多 opencode 有的配置：
- MCP 服务器配置
- 插件配置
- 权限规则配置
- 主题配置持久化
- 快捷键配置

#### OpenCode 对比
opencode 配置系统非常完整，支持数十种配置项的持久化和热更新。

---

### P2-3: 缺少权限系统的 UI 交互

**严重级别**: P2  
**模块**: 权限系统

#### 问题描述
- QuestionDialog 组件存在但无法工作（因缺少后端API，见 P0-2）
- 没有权限规则管理界面
- 没有"总是允许"的记忆功能
- 无法查看和管理已授权的权限规则

#### OpenCode 对比
opencode 有完整的 permission 系统，支持：
- wildcard 匹配规则
- saved rules 持久化
- 权限管理 UI

---

### P2-4: 缺少会话压缩/回滚功能

**严重级别**: P2  
**模块**: 会话管理

#### 问题描述
不支持会话压缩和回滚功能。

#### OpenCode 对比
opencode 实现了：
- `POST /api/session/:sessionID/compact` - 压缩会话（用摘要替换历史消息）
- `POST /api/session/:sessionID/revert/stage` - 回滚暂存
- `POST /api/session/:sessionID/revert/commit` - 提交回滚

---

### P2-5: 缺少文件系统（FS）API

**严重级别**: P2  
**模块**: API 接口

#### 问题描述
只有 `/api/files/search` 一个简单接口，缺少完整的文件系统 API。

#### OpenCode 对比
opencode 有完整的 fs group，包括：
- 文件读取/写入
- 目录列表
- 文件搜索
- 符号链接处理
- 文件统计信息

#### 影响范围
- 前端 @mention 文件功能可能不完善
- 工具调用中的文件操作依赖后端直接执行，无法通过 API 管理

---

### P2-6: 命令面板功能过于简单

**严重级别**: P2  
**模块**: UI 交互

#### 问题描述
[CommandPalette.tsx](file:///Users/mac/AI/CScode/src/cscode/web/src/components/ui/CommandPalette.tsx) 只有 4 个命令：
- 新建会话
- 切换主题
- 打开设置
- 切换侧边栏

#### OpenCode 对比
opencode 命令面板集成了数十个命令，涵盖：
- 会话管理
- 文件操作
- 设置项快速调整
- 主题切换
- 快捷键触发的各种操作

#### 影响范围
- 用户效率低下
- 高级功能难以发现

---

## 6. 核心根因分析

### 6.1 前后端 API 契约不统一
前端是按照 opencode 的 API 风格开发的，但后端只实现了部分接口，导致大量 404 错误。建议先统一 API 契约文档，再分头开发。

### 6.2 事件系统设计不一致
三个地方的事件数据结构不一致：
1. 后端 `_llm_event_to_dict` 输出的事件格式（顶层字段）
2. 前端 `applyEvent` 期望的事件格式（`event.data` 嵌套）
3. 持久化逻辑中的事件格式（`sse_event.get("data", {})`）

建议统一事件格式为 `{ type: string, data: object }`。

### 6.3 架构分层未完成
根据技术规格书 [technical-specification.md](file:///Users/mac/AI/CScode/docs/technical-specification.md)，CScode 应该有四层架构：

| 层级 | 状态 | 说明 |
|------|------|------|
| Schema 层 | ✅ 基本完成 | Pydantic 模型定义 |
| LLM 层 | ✅ 部分完成 | Provider 适配器、Route 系统 |
| Core 层 | 🟡 部分完成 | SessionRunner、Coordinator 存在但未完全集成 |
| App 层 | 🟡 双轨并行 | 旧 engine.py 和新 AgentV2 并存 |

### 6.4 缺少端到端测试
没有 GUI 层面的集成测试，导致 UI 交互 bug（如遮罩层挡住按钮）无法及时发现。

---

## 7. 建议修复优先级

### 第一阶段（必须修复，否则无法使用）
1. **P0-1**: 实现 `/api/sessions/{id}/messages` 接口
2. **P0-5**: 统一事件数据结构（`{ type, data }` 格式）
3. **P0-3**: 补充 `step.started` 等关键事件
4. **P0-4**: 修复移动端遮罩层挡住按钮的问题

### 第二阶段（重要功能）
5. **P0-2**: 实现 Question 相关 API 和权限系统
6. **P1-4**: 完善停止/中断功能
7. **P1-6**: 修复消息持久化
8. **P1-1**: 修复主题系统错误

### 第三阶段（架构完善）
9. **P1-2**: 实现会话上下文 API
10. **P1-3**: 实现会话事件订阅 API
11. **P1-5**: 实现 Agent/Model 切换 API
12. 其他 P2 级问题

---

## 8. 测试结论

CScode 重构版本目前处于 **基础可用但功能严重不完整** 的状态：

- ✅ 基础的单轮对话可以正常工作
- ❌ 多会话管理基本不可用（无法加载历史消息）
- ❌ 流式交互体验缺失（无思考状态、无打字效果）
- ❌ 权限系统完全缺失
- ❌ 移动端 UI 存在致命 bug

**建议**: 优先修复 P0 级的 5 个问题，使核心流程可以跑通，再逐步完善 P1 和 P2 级功能。

---

**报告生成时间**: 2026-06-30  
**测试人员**: AI 自动化测试  
**报告版本**: v1.0
