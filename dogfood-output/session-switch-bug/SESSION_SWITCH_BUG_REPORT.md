# Session 切换 Bug 专项测试报告

## 测试概述

**测试目的**: 验证多Session并行与LLM交互场景下，切换Session是否会导致消息丢失或任务中断

**测试方法**: Playwright端到端测试，模拟用户创建多个Session、发送消息、切换Session的完整流程

**测试时间**: 2026-07-09

**测试环境**: 
- 后端服务: http://localhost:8000 (CScode v0.3.4)
- 浏览器: Chromium (headless=False)
- 测试脚本: session_switch_test_v3.py

---

## 测试结果总览

| 测试项 | 结果 | 详情 |
|--------|------|------|
| 会话切换数据完整性 | ❌ 失败 | 'Python' 出现次数从 16 次减少到 1 次 |
| 流式响应事件处理 | ❌ 失败 | applyEvent 调用次数为 0 |
| 版本守卫机制 | ❌ 失败 | VERSION CHANGED 次数为 0 |

---

## 问题详细分析

### 问题 1: 会话切换导致消息丢失

**现象**: 
- Session A发送长消息后，'Python'出现16次
- 切换到Session B再切换回Session A后，'Python'仅剩1次
- 消息内容从完整的LLM响应变为只有用户消息

**根本原因**: `Sidebar.tsx`的`handleSelectSession`在切换会话时无条件调用`api.session.messages(id)`获取服务器消息，然后调用`setMessages(msgs, id)`覆盖本地消息。当服务器返回的数据不完整时（如流式响应还未持久化），本地已有的流式数据会被清空。

**关键代码路径**:
1. 用户点击Session A → `handleSelectSession(id)`
2. 调用 `api.session.messages(id)` 获取服务器消息
3. 调用 `setMessages(msgs, id)` 覆盖本地消息
4. 本地流式响应数据被服务器的空/不完整数据覆盖

### 问题 2: 流式响应事件未被处理

**现象**: 
- `applyEvent` 调用次数为 0
- 即使流式响应正常结束（`stream ended normally`），也没有任何事件被处理

**分析**: 流式事件（`text.delta`、`step.started`、`text.ended`等）应该通过`applyEvent`更新store，但测试期间没有任何事件被处理。这可能是因为：
- 事件类型不匹配
- 事件过滤逻辑问题
- 流式响应格式不正确

### 问题 3: 版本守卫机制失效

**现象**: 
- `VERSION CHANGED` 次数为 0
- 即使流式响应期间版本号应该增加，切换时也没有检测到版本变化

**分析**: `Sidebar.tsx`中的版本比较逻辑：
```typescript
const cachedVersion = store.sessionMessageVersion[id] || 0;
// ... fetch messages ...
const currentVersion = currentStore.sessionMessageVersion[id] || 0;
if (currentVersion > cachedVersion) {
    setMessages(msgs, id, true);  // mergeLocal=true
}
```
由于`applyEvent`未被调用，版本号从未增加，导致Version Guard永远不会触发合并逻辑。

---

## 时序分析

### 正常流程（期望）
```
1. 用户在Session A发送消息
2. LLM开始流式响应 → applyEvent 更新本地store + 增加版本号
3. 用户切换到Session B → 保留Session A的流式数据
4. 用户切换回Session A → Version Guard检测到版本变化 → 合并服务器数据和本地数据
5. Session A显示完整的LLM响应
```

### 实际流程（问题）
```
1. 用户在Session A发送消息
2. LLM开始流式响应 → applyEvent 未被调用（事件丢失）
3. 用户切换到Session B → Session A数据未被正确更新
4. 用户切换回Session A → setMessages用空服务器数据覆盖本地数据
5. Session A消息被清空
```

---

## 代码问题定位

### 问题代码位置

| 文件 | 行号 | 问题描述 |
|------|------|----------|
| `src/cscode/web/src/hooks/useChat.ts` | 154-163 | 流式事件处理逻辑可能存在问题，导致applyEvent未被调用 |
| `src/cscode/web/src/components/layout/Sidebar.tsx` | 54-71 | handleSelectSession无条件覆盖本地消息，版本守卫失效 |
| `src/cscode/web/src/stores/useSessionStore.ts` | 350-376 | setMessages在服务器数据为空时无法正确保留本地数据 |

### 关键代码段

**Sidebar.tsx - handleSelectSession**:
```typescript
const cachedVersion = store.sessionMessageVersion[id] || 0;
try {
    const msgs = await api.session.messages(id);
    const currentStore = useSessionStore.getState();
    if (currentStore.activeSessionId === id) {
        const currentVersion = currentStore.sessionMessageVersion[id] || 0;
        if (currentVersion > cachedVersion) {
            setMessages(msgs, id, true);  // 合并模式
            return;
        }
        setMessages(msgs, id);  // ❌ 直接覆盖，丢失本地流式数据
    }
}
```

**useChat.ts - 事件处理**:
```typescript
case 'text.delta':
case 'step.started':
case 'text.ended':
    if (isCurrentStream()) {
        applyEvent(capturedSid, event);  // ❌ 未被调用
    }
    break;
```

---

## 测试数据证据

### 控制台日志摘要

```
[chat] sendMessage: appending user message sid=1783586101779646000 "Please write a very detailed explanation..."
[store] appendMessage role=user ... session=1783586101779646000 total=1 version=2

# 切换后（没有任何applyEvent调用！）
[store] setMessages session=1783586123134392000 prev=0 -> fetched=0 filtered=0 result=0

# 最终状态
[chat] stream ended normally for session=1783586123134392000
```

### 消息计数变化

| 阶段 | 'Python'出现次数 | 说明 |
|------|-----------------|------|
| 发送消息后 | 16次 | LLM响应中包含多个Python相关内容 |
| 切换回Session A后 | 1次 | 仅剩用户消息中的Python |
| 等待15秒后 | 1次 | 消息未恢复 |

---

## 影响评估

**严重程度**: 🔴 严重

**业务影响**:
- 用户无法在多任务间切换查看进度
- 切换会话会导致正在进行的LLM响应丢失
- 用户体验极差，无法正常使用多会话功能

---

## 建议修复方案

### 方案 1: 修复流式事件处理（优先级最高）

检查`useChat.ts`中的事件处理逻辑，确保`applyEvent`被正确调用。可能的问题：
- 事件类型不匹配
- `isCurrentStream()`返回false
- 事件格式不正确

### 方案 2: 改进版本守卫机制

确保`applyEvent`正确增加版本号，并且`Sidebar.tsx`能够检测到版本变化。

### 方案 3: 修改setMessages合并逻辑

当服务器返回空数组时，保留本地已有的消息数据，而不是清空。

### 方案 4: 延迟加载策略

切换会话时，如果目标会话正在加载（`sessionLoading[id]`为true），则不刷新消息，等待流式响应完成后再同步。

---

## 测试截图

| 截图 | 描述 |
|------|------|
| v3-01-session-a-thinking.png | Session A发送消息后，LLM正在响应 |
| v3-02-session-b-thinking.png | Session B发送消息后 |
| v3-03-back-to-session-a.png | 切换回Session A后，消息被清空 |
| v3-04-final-state.png | 最终状态，消息未恢复 |

---

## 结论

Session切换Bug的根本原因是**流式事件处理失败**和**消息覆盖机制缺陷**的组合：

1. 流式响应的事件没有被`applyEvent`处理，导致本地store没有接收到LLM的响应数据
2. 切换会话时，`setMessages`用服务器的空数据覆盖了本地数据
3. 版本守卫机制因为版本号从未增加而失效

建议优先修复流式事件处理问题，这是导致消息丢失的核心原因。