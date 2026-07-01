# CScode GUI 功能测试报告 (第二轮)

**测试日期**: 2026-06-30 (第二轮)
**测试环境**: macOS + React Web 前端 + FastAPI 后端
**测试版本**: v0.3.4
**测试范围**: GUI 全部功能、前后端接口联调、事件流处理

---

## 1. 测试概述

本轮测试对修复后的 CScode 版本进行了全面的 GUI 功能测试和 API 接口验证。

### 1.1 修复状态概览

| 原始问题 | 修复状态 | 备注 |
|---------|---------|------|
| P0-1: 缺少消息 API | ✅ 已实现 | `/api/sessions/{id}/messages` 已添加 |
| P0-2: 缺少 Question API | ✅ 已实现 | questions 相关 API 已添加 |
| P0-3: 缺少流式事件 | ✅ 已实现 | `step.started` 等事件已添加 |
| P0-4: 移动端遮罩层 | ❓ 未测试 | 需要实际移动端测试 |
| P0-5: 事件数据结构不匹配 | ✅ 已修复 | 统一使用 `{type, data}` 格式 |
| P1-2: 上下文 API | ✅ 已实现 | `/api/sessions/{id}/context` 已添加 |
| P1-3: 事件订阅 API | ✅ 已实现 | `/api/sessions/{id}/events` 已添加 |
| P1-5: Agent/Model 切换 | ✅ 已实现 | 已添加对应 API |
| P2-3: 权限规则 API | ✅ 已实现 | 已添加 CRUD 接口 |
| P2-4: 会话压缩 API | ✅ 已实现 | `/api/sessions/{id}/compact` 已添加 |
| P2-5: 文件系统 API | ✅ 已实现 | `/api/files/read`, `/api/files/list` 已添加 |

### 1.2 测试环境

- **后端**: FastAPI + uvicorn (端口 8765) ✅ 正常运行
- **前端**: React 18 + Vite (端口 5173)
- **数据库**: SQLite + WAL 模式
- **工具注册**: 14 个工具已注册

---

## 2. 发现的新问题

### 2.1 配置问题 (P0)

#### 问题: 前端代理配置端口错误

**严重级别**: P0
**模块**: 前端配置

**现象描述**
前端开发服务器代理配置指向错误的后端端口，导致前端无法与后端通信，所有 API 请求返回 500 错误。

**问题代码**
[vite.config.ts](file:///Users/mac/AI/CScode/src/cscode/web/vite.config.ts#L9-L10):
```typescript
proxy: {
  '/api': 'http://localhost:8080',  // ❌ 错误：应该是 8765
  '/outputs': 'http://localhost:8080',
},
```

**实际后端端口**
后端运行在 `http://localhost:8765`，而不是 8080。

**影响范围**
- 前端所有 API 调用失败
- 会话列表无法加载
- 配置信息无法获取
- 聊天功能无法使用

**修复建议**
将 `vite.config.ts` 中的代理目标从 `http://localhost:8080` 改为 `http://localhost:8765`。

---

### 2.2 消息持久化问题 (P0)

#### 问题: 用户消息字段名不匹配导致内容为空

**严重级别**: P0
**模块**: 会话管理 / 事件持久化

**现象描述**
虽然消息 API 已实现，但返回的用户消息内容为空 (`"content": ""`)。

**问题代码**

1. 存储端 ([app.py#L428](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L428)):
```python
await _event_store.append(str(session_v2.session_id), [
    {"type": "prompt.admitted", "data": {"content": message, "files": attached_filenames}}
    #                                   ^^^^^^^ 存储字段是 "content"
])
```

2. 读取端 ([core/session.py#L84](file:///Users/mac/AI/CScode/src/cscode/core/session.py#L84)):
```python
case "prompt.admitted":
    messages.append(
        Message(
            id=None,
            role=MessageRole.USER,
            parts=(TextPart(text=str(event.data.get("prompt", ""))),),
            #                                ^^^^^^ 读取字段是 "prompt"
        )
    )
```

**API 返回示例**
```json
[
  {
    "role": "user",
    "content": "",  // ❌ 为空
    "id": null
  }
]
```

**根因分析**
- 存储时使用字段名 `"content"`
- 读取时使用字段名 `"prompt"`
- 字段名不匹配导致读取到空值

**影响范围**
- 历史消息内容丢失
- 会话切换后消息为空
- 无法查看对话历史

**修复建议**
统一字段名为 `"content"` 或 `"prompt"`（建议使用 `"content"` 以保持与其他事件的一致性）。

---

## 3. API 接口测试结果

### 3.1 正常工作的 API

| API | 方法 | 路径 | 状态 | 备注 |
|-----|------|------|------|------|
| Health | GET | `/api/health` | ✅ 正常 | 返回版本 0.3.4 |
| Sessions | GET | `/api/sessions` | ✅ 正常 | 返回会话列表 |
| Config | GET | `/api/config` | ✅ 正常 | 返回配置信息 |
| Messages | GET | `/api/sessions/{id}/messages` | ⚠️ 部分正常 | 字段名不匹配 |
| Questions | GET | `/api/sessions/{id}/questions` | ✅ 正常 | 返回空数组 |
| Questions Reply | POST | `/api/sessions/{id}/questions/{id}/reply` | ✅ 已实现 | - |
| Questions Reject | POST | `/api/sessions/{id}/questions/{id}/reject` | ✅ 已实现 | - |
| Stop Session | POST | `/api/sessions/{id}/stop` | ✅ 已实现 | - |
| Create Session | POST | `/api/sessions` | ✅ 已实现 | - |
| Delete Session | DELETE | `/api/sessions/{id}` | ✅ 已实现 | - |
| Context | GET | `/api/sessions/{id}/context` | ✅ 已实现 | - |
| Switch Model | POST | `/api/sessions/{id}/model` | ✅ 已实现 | - |
| Switch Agent | POST | `/api/sessions/{id}/agent` | ✅ 已实现 | - |
| Compact | POST | `/api/sessions/{id}/compact` | ✅ 已实现 | - |
| Permission Rules | GET/POST/DELETE | `/api/permission-rules` | ✅ 已实现 | - |
| Files Search | GET | `/api/files/search` | ✅ 已实现 | - |
| Files Read | POST | `/api/files/read` | ✅ 已实现 | - |
| Files List | GET | `/api/files/list` | ✅ 已实现 | - |

### 3.2 测试的 API 响应示例

**GET /api/sessions**
```json
[
  {
    "id": "1782648710123227000",
    "title": "测试会话",
    "provider": "openai",
    "model": "MiniMax-M2.5",
    "created_at": 1782648710.123244,
    "updated_at": 1782693411.4227982
  }
]
```

**GET /api/config**
```json
{
  "provider": "scnet",
  "model": "MiniMax-M2.5",
  "api_base": "https://api.scnet.cn/api/llm/v1",
  "api_key": "sk-sp-...",
  "max_tokens": 4096,
  "temperature": 0.3,
  "top_p": 1.0,
  "system_prompt": null
}
```

**GET /api/sessions/{id}/messages (有问题的响应)**
```json
[
  {
    "role": "user",
    "content": "",  // ⚠️ 内容为空
    "id": null
  }
]
```

---

## 4. GUI 功能测试结果

### 4.1 Playwright 自动化测试结果

```
Test 1: Navigate to app
Page title: CScode - AI Coding Assistant
Main content area visible: True

Test 2: Check sidebar
Sidebar found: [role="navigation"]

Test 3: Test new chat button
Found 1 elements matching '[aria-label*="new"], [aria-label*="chat"]'

Test 4: Find input box
Found 1 input(s): textarea
Successfully typed in input

Test 7: Check API calls
Total API requests: 8
  GET http://localhost:5173/api/health
  GET http://localhost:5173/api/sessions      // ❌ 500 错误
  GET http://localhost:5173/api/config         // ❌ 500 错误

Console errors: 12
  [error] Failed to load resource: the server responded with a status of 500 (Internal Server Error)
```

### 4.2 测试通过的 UI 元素

| 元素 | 选择器 | 状态 |
|------|--------|------|
| 页面标题 | CScode - AI Coding Assistant | ✅ |
| 主内容区 | main, [role="main"] | ✅ |
| 侧边栏 | [role="navigation"] | ✅ |
| 新建会话按钮 | [aria-label*="new"] | ✅ |
| 输入框 | textarea | ✅ |
| 设置按钮 | button:has-text("Settings") | ✅ |

---

## 5. 事件流测试结果

### 5.1 事件格式 (已修复)

后端发送的事件格式已统一为：
```json
{
  "type": "text.delta",
  "data": {
    "content": "Hello"
  },
  "session_id": "xxx"
}
```

### 5.2 持久化的事件类型

```python
PERSIST_EVENT_TYPES = frozenset({
    "step.started",  ✅
    "text.ended",    ✅
    "step.ended",    ✅
    "tool.called",   ✅
    "tool.success",  ✅
    "tool.failed",   ✅
    "error",         ✅
    // 注意: "prompt.admitted" 不在列表中，但它在代码中直接持久化
})
```

---

## 6. 修复建议优先级

### 第一阶段 (必须立即修复)

1. **P0-1**: 修复 `vite.config.ts` 中的代理端口配置
   - 将 `http://localhost:8080` 改为 `http://localhost:8765`

2. **P0-2**: 修复消息持久化字段名不匹配
   - 统一 `app.py` 存储和 `core/session.py` 读取的字段名
   - 建议：将 `core/session.py` 第 84 行的 `"prompt"` 改为 `"content"`

### 第二阶段 (建议修复)

3. **P2-1**: 添加 `prompt.admitted` 到 `PERSIST_EVENT_TYPES`
   - 确保用户消息通过 `on_event` 统一持久化
   - 或者保持当前直接持久化方式（已有兜底）

4. **UI 测试**: 在移动端宽度下测试遮罩层行为
   - 之前的遮罩层挡住发送按钮问题需要实际测试验证

---

## 7. 测试结论

### 7.1 整体评估

✅ **已修复的问题**:
- 大部分 P0/P1/P2 级 API 接口已实现
- 事件流格式已统一为 `{type, data}` 结构
- 工具注册正常工作 (14 个工具)
- 后端服务稳定运行

❌ **仍需修复的问题**:
- **前端代理配置端口错误** (P0): 导致前端无法与后端通信
- **消息字段名不匹配** (P0): 导致历史消息内容为空

### 7.2 修复后预期效果

修复这两个问题后，应该能够：
1. ✅ 前端正常调用所有 API
2. ✅ 会话列表正常加载
3. ✅ 聊天消息正常发送和接收
4. ✅ 历史消息正常显示

---

**报告生成时间**: 2026-06-30
**测试人员**: AI 自动化测试 + 手动验证
**报告版本**: v2.0
