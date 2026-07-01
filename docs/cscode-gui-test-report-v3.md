# CScode GUI 功能测试报告 (第三轮)

**测试日期**: 2026-07-01
**测试环境**: macOS + React Web 前端 + FastAPI 后端
**测试版本**: v0.3.4
**测试范围**: GUI 全部功能、前后端接口联调、事件流处理

---

## 1. 测试概述

本轮测试对第二轮修复后的 CScode 版本进行了全面的 GUI 功能测试，重点验证了 API 接口、消息持久化、流式事件和前端交互。

### 1.1 已修复的问题

| 原始问题 | 修复状态 | 验证结果 |
|---------|---------|---------|
| P0-1: 消息 API 缺失 | ✅ 已实现 | `/api/sessions/{id}/messages` 工作正常 |
| P0-2: Question API 缺失 | ✅ 已实现 | 所有 Question 端点已添加 |
| P0-3: 流式事件缺失 | ✅ 已实现 | `step.started`/`step.ended` 已发送 |
| P0-5: 事件格式不匹配 | ✅ 已修复 | 统一为 `{type, data}` 格式 |
| P1-2/3/5: 上下文/订阅/切换 API | ✅ 已实现 | 全部端点可用 |
| P2-3/4/5: 权限/压缩/文件 API | ✅ 已实现 | 全部端点可用 |

### 1.2 测试环境

- **后端**: FastAPI + uvicorn (端口 8765) ✅
- **前端**: React 18 + Vite (端口 5173)
- **数据库**: SQLite + WAL 模式
- **代理**: nginx 占用 8080 端口（与 Vite 代理配置冲突）

---

## 2. 发现的新问题

### 🔴 P0-1: Vite 代理配置指向错误端口

**严重级别**: P0  
**模块**: 前端构建配置

#### 现象描述
前端所有 API 请求返回 nginx 404 错误，导致应用完全无法与后端通信。

#### 控制台错误
```
Failed to load resource: the server responded with a status of 404 (Not Found)
Failed to fetch sessions Error: API error 404: <html><title>404 Not Found</title>...<center>nginx/1.29.6</center>
```

#### 根因分析
[vite.config.ts](file:///Users/mac/AI/CScode/src/cscode/web/vite.config.ts#L9):
```typescript
proxy: {
  '/api': 'http://localhost:8080',   // ❌ nginx 占用此端口
  '/outputs': 'http://localhost:8080',
}
```

系统上 nginx 占用了 8080 端口：
```
mac  1074  nginx: worker process
mac   890  nginx: master process
```

而后端运行在 **8765** 端口，导致 API 请求全部发到 nginx。

#### 影响范围
- 所有 API 调用失败
- 会话列表无法加载
- 配置无法获取
- 聊天功能完全不可用

#### 修复建议
将 `vite.config.ts` 中的代理目标从 `http://localhost:8080` 改为 `http://localhost:8765`。

---

### 🔴 P0-2: `on_event` 协程未被正确 await

**严重级别**: P0  
**模块**: 事件流处理

#### 现象描述
流式响应中缺少 `text.ended` 和 `text.delta` 事件，导致：
1. 助手回复内容未被持久化
2. 前端无法显示流式打字效果
3. 消息历史中只有用户消息，没有助手回复

#### 流式响应实际输出
```
data: {"type": "step.started", "data": {}, ...}
data: {"type": "step.ended", "data": {}, ...}
data: {"type": "complete", "data": {"finish_reason": "stop"}, ...}
```

缺少 `text.delta` 和 `text.ended` 事件。

#### 数据库中的事件
```
session.created|{"title": "Test Round 3", ...}
prompt.admitted|{"prompt": "Say hello", "files": []}
step.started|{}
step.ended|{}
```

**注意**: 没有 `text.ended` 事件，所以助手回复没有被保存。

#### 根因分析
[agent.py](file:///Users/mac/AI/CScode/src/cscode/app/agent.py#L182):
```python
await on_event(event) if hasattr(on_event, "__await__") else on_event(event)
```

这段代码存在严重逻辑错误：
- `on_event` 是 `app.py` 中定义的 `async def on_event()` 函数
- 函数对象本身没有 `__await__` 属性（只有协程对象才有）
- 因此条件判断走 `else` 分支，执行 `on_event(event)`
- 这会创建一个协程对象，但**从未被 await**
- 结果：事件既没有发送到 SSE 队列，也没有被持久化

后端日志明确警告：
```
RuntimeWarning: coroutine 'chat_stream.<locals>.event_stream.<locals>.on_event' was never awaited
```

#### 影响范围
- 流式打字效果完全缺失
- 助手回复无法持久化
- 刷新页面后助手消息丢失
- 消息历史不完整

#### 修复建议
修改 [agent.py](file:///Users/mac/AI/CScode/src/cscode/app/agent.py#L182) 为：
```python
import inspect
if inspect.iscoroutinefunction(on_event):
    await on_event(event)
else:
    on_event(event)
```

或者统一将 `on_event` 改为同步回调。

---

### 🟡 P1-1: 旧数据兼容性问题

**严重级别**: P1  
**模块**: 数据迁移

#### 现象描述
旧会话的历史消息内容为空。

#### 根因分析
数据库中的旧事件使用 `"content"` 字段存储用户输入：
```
prompt.admitted|{"content": "你好，请介绍一下你自己", "files": []}
```

但代码已改为读取 `"prompt"` 字段：
```python
event.data.get("prompt", "")  # 读取 "prompt"
```

导致旧数据读取为空字符串。

#### 修复建议
在 `SessionProjector.project()` 中添加兼容逻辑：
```python
case "prompt.admitted":
    content = event.data.get("prompt") or event.data.get("content", "")
    messages.append(Message(..., parts=(TextPart(text=content),)))
```

---

### 🟡 P1-2: 发送按钮难以定位

**严重级别**: P1  
**模块**: UI 测试

#### 现象描述
Playwright 自动化测试中无法找到发送按钮。

#### 根因分析
发送按钮没有明确的文本或 aria-label，只有图标：
```
<button> (无文本, 无 aria-label)
```

#### 修复建议
为发送按钮添加 `aria-label="Send message"`。

---

### 🟡 P1-3: 主题切换按钮缺失

**严重级别**: P1  
**模块**: UI 交互

#### 现象描述
自动化测试中找不到主题切换按钮。

#### 修复建议
检查主题切换是否集成在设置面板中，或者添加专门的主题切换按钮。

---

### 🟡 P1-4: 移动端汉堡菜单缺失

**严重级别**: P1  
**模块**: 移动端适配

#### 现象描述
在 375x812 移动端视口下，找不到汉堡菜单按钮。

#### 修复建议
为移动端侧边栏切换按钮添加明确的 `aria-label="Toggle menu"`。

---

## 3. API 接口验证结果

### 3.1 全部可用 API 端点

| 方法 | 路径 | 状态 | 备注 |
|------|------|------|------|
| GET | `/api/health` | ✅ | 返回版本 0.3.4 |
| GET | `/api/sessions` | ✅ | 返回会话列表 |
| POST | `/api/sessions` | ✅ | 创建新会话 |
| DELETE | `/api/sessions/{id}` | ✅ | 删除会话 |
| PATCH | `/api/sessions/{id}` | ✅ | 更新会话标题 |
| POST | `/api/sessions/{id}/stop` | ✅ | 停止会话 |
| GET | `/api/sessions/{id}/messages` | ⚠️ | 用户消息正常，助手消息缺失 |
| GET | `/api/sessions/{id}/context` | ✅ | 返回上下文 |
| GET | `/api/sessions/{id}/events` | ✅ | SSE 事件订阅 |
| GET | `/api/sessions/{id}/questions` | ✅ | 问题列表 |
| POST | `/api/sessions/{id}/questions/{id}/reply` | ✅ | 回复问题 |
| POST | `/api/sessions/{id}/questions/{id}/reject` | ✅ | 拒绝问题 |
| POST | `/api/sessions/{id}/model` | ✅ | 切换模型 |
| POST | `/api/sessions/{id}/agent` | ✅ | 切换 Agent |
| POST | `/api/sessions/{id}/compact` | ✅ | 压缩会话 |
| POST | `/api/sessions/{id}/export` | ✅ | 导出会话 |
| POST | `/api/sessions/import` | ✅ | 导入会话 |
| GET | `/api/config` | ✅ | 获取配置 |
| POST | `/api/config` | ✅ | 更新配置 |
| GET | `/api/permission-rules` | ✅ | 权限规则列表 |
| POST | `/api/permission-rules` | ✅ | 创建权限规则 |
| DELETE | `/api/permission-rules/{id}` | ✅ | 删除权限规则 |
| GET | `/api/files/search` | ✅ | 文件搜索 |
| POST | `/api/files/read` | ✅ | 读取文件 |
| GET | `/api/files/list` | ✅ | 列出目录 |
| POST | `/api/chat` | ✅ | 聊天（非流式） |
| POST | `/api/chat/stream` | ✅ | 流式聊天 |

### 3.2 消息 API 测试结果

**新会话消息** ✅:
```json
[
  {
    "role": "user",
    "content": "Say hello",
    "id": null
  }
]
```

**旧会话消息** ❌:
```json
[
  {
    "role": "user",
    "content": "",
    "id": null
  }
]
```

---

## 4. 流式事件验证

### 4.1 事件发送顺序

实际发送的事件（存在 bug）:
```
1. step.started  ✅
2. step.ended    ✅
3. complete      ✅ (包含完整内容)
```

**缺失的事件**:
```
- text.delta    ❌ (流式打字效果)
- text.ended    ❌ (助手回复持久化)
```

### 4.2 事件持久化状态

```
session.created     ✅
prompt.admitted     ✅ (用户消息)
step.started        ✅
step.ended          ✅
text.ended          ❌ (缺失 - 助手回复)
tool.called         ❌ (未触发)
tool.success        ❌ (未触发)
```

---

## 5. GUI 元素扫描结果

### 5.1 检测到的按钮（共 11 个）

| # | 文本 | aria-label | 状态 |
|---|------|-----------|------|
| 0 | Plan | - | 正常 |
| 1 | Build | - | 正常 |
| 2 | - | Filter threads | 正常 |
| 3 | - | Sort threads | 正常 |
| 4 | - | Refresh sessions | 正常 |
| 5 | - | Create new session | 正常 |
| 6 | AI-CScode | - | 正常 |
| 7 | Settings | - | 正常 |
| 8 | Help | - | 正常 |
| 9 | - | - | ❓ 无标识 |
| 10 | - | - | ❓ 无标识 |

### 5.2 缺失的交互元素

| 元素 | 期望选择器 | 实际状态 |
|------|-----------|---------|
| 发送按钮 | `aria-label="Send"` | 无标识 |
| 主题切换 | `aria-label="Toggle theme"` | 未找到 |
| 移动端菜单 | `aria-label="Menu"` | 未找到 |
| 停止按钮 | `aria-label="Stop"` | 未找到（非流式状态） |

---

## 6. 修复优先级建议

### 第一阶段（致命 - 立即修复）

1. **修复 Vite 代理端口** ([vite.config.ts](file:///Users/mac/AI/CScode/src/cscode/web/vite.config.ts#L9))
   ```typescript
   proxy: {
     '/api': 'http://localhost:8765',  // 改为 8765
     '/outputs': 'http://localhost:8765',
   }
   ```

2. **修复 `on_event` 协程调用** ([agent.py](file:///Users/mac/AI/CScode/src/cscode/app/agent.py#L182))
   ```python
   import inspect
   if inspect.iscoroutinefunction(on_event):
       await on_event(event)
   else:
       on_event(event)
   ```

### 第二阶段（重要 - 尽快修复）

3. **修复旧数据兼容性** ([core/session.py](file:///Users/mac/AI/CScode/src/cscode/core/session.py#L84))
   ```python
   content = event.data.get("prompt") or event.data.get("content", "")
   ```

4. **为按钮添加 aria-label**
   - 发送按钮: `aria-label="Send message"`
   - 主题切换: `aria-label="Toggle theme"`
   - 移动端菜单: `aria-label="Toggle menu"`

---

## 7. 测试结论

### 7.1 整体评估

✅ **已修复**:
- 所有缺失的 API 端点已实现
- 事件数据结构已统一
- 消息 API 已可用

❌ **新发现的关键问题**:
1. **前端代理配置错误** (P0): 8080 vs 8765 端口不匹配
2. **`on_event` 协程未 await** (P0): 导致流式事件和持久化失败
3. **旧数据兼容性** (P1): `"content"` vs `"prompt"` 字段

### 7.2 修复后预期效果

修复 P0-1 和 P0-2 后，应该能够：
1. ✅ 前端正常连接后端 API
2. ✅ 会话列表正确加载
3. ✅ 聊天消息正常发送和接收
4. ✅ 流式打字效果正常显示
5. ✅ 助手回复正确持久化
6. ✅ 历史消息完整显示

---

**报告生成时间**: 2026-07-01  
**测试人员**: AI 自动化测试  
**报告版本**: v3.0
