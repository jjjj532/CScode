# CScode Session 切换 Bug 深度分析报告

**报告时间**: 2026-07-09
**严重程度**: P0 - 阻断性
**影响场景**: 多 Session 并行执行时用户切换 Session

---

## 一、Bug 现象

用户报告：
1. 两个 session 并行执行任务，与 LLM 交互
2. 用户手动点击左侧 session 栏切换观察不同 session 的任务进展
3. **切换过程中，session 中 LLM 的反馈信息被清除**
4. 如果不手动切换，静止等待，session 中会正常显示 LLM 反馈
5. 现象：手动切换 session 会导致任务被重置

---

## 二、测试验证结果

### 2.1 自动化测试日志证据

```
setMessages 调用次数: 12
  [store] setMessages session=1783580508557700000 prev=0 -> fetched=0 filtered=0
  [store] setMessages session=1783580508557700000 prev=0 -> fetched=0 filtered=0
  [sidebar] setMessages done for session=1783580508557700000
  [store] setMessages session=1783580513590371000 prev=0 -> fetched=0 filtered=0
  [store] setMessages session=1783580513590371000 prev=0 -> fetched=0 filtered=0
  [sidebar] setMessages done for session=1783580513590371000
  [store] setMessages session=1783580508557700000 prev=2 -> fetched=1 filtered=1  <-- BUG!
  [sidebar] setMessages done for session=1783580508557700000
  [store] setMessages session=1783580513590371000 prev=2 -> fetched=2 filtered=2
  [sidebar] setMessages done for session=1783580513590371000
```

**关键证据**:
- `Session A`: `prev=2 -> fetched=1 filtered=1`
  - 本地有 **2 条消息**（user 提问 + assistant 部分回复）
  - 服务器返回 **1 条消息**（只包含已持久化的 user 消息）
  - `setMessages` **用 1 条消息覆盖了 2 条消息**，导致 assistant 回复丢失！

---

## 三、Root Cause Analysis（根本原因分析）

### 3.1 问题链

```
用户切换 Session A
  -> handleSelectSession() 调用
    -> api.session.messages(id) 发起请求
      -> 请求期间，后台 LLM 流继续推送 text.delta 事件
        -> applyEvent() 更新 sessionMessages（但不更新 version）
    -> 请求完成，服务器返回消息列表（不包含正在流式传输中的消息）
      -> setMessages(msgs, id) 直接替换消息列表
        -> 本地累积的流式消息被服务器旧数据覆盖！
```

### 3.2 代码层面根因

#### Bug 1: `setMessages` 直接替换消息列表（无合并逻辑）

**位置**: [useSessionStore.ts:339-354](file:///Users/mac/AI/CScode/src/cscode/web/src/stores/useSessionStore.ts#L339-L354)

```typescript
setMessages: (messages, sessionId) => set((s) => {
  const prev = s.sessionMessages[sessionId];
  const filtered = messages.filter(
    (m) => m.role !== 'assistant' || (m.content && m.content.trim())
  );
  // ❌ 直接替换，不做任何合并！
  return {
    sessionMessages: {
      ...s.sessionMessages,
      [sessionId]: filtered,  // 直接覆盖！
    },
  };
}),
```

**问题**: `setMessages` 用服务器返回的消息列表**直接替换**本地消息，没有任何合并或 diff 逻辑。如果服务器返回的消息比本地少（流式消息尚未持久化），本地的流式消息就会丢失。

#### Bug 2: `setMessages` 不更新 `sessionMessageVersion`

**位置**: [useSessionStore.ts:339-354](file:///Users/mac/AI/CScode/src/cscode/web/src/stores/useSessionStore.ts#L339-L354)

`setMessages` 返回的新 state 中**不包含 `sessionMessageVersion` 的更新**。

这意味着：
- 调用 `setMessages` 后，`sessionMessageVersion[sessionId]` **不变**
- Version Guard 无法区分 "setMessages 设置后" 和 "setMessages 设置前"

#### Bug 3: `applyEvent` 不更新 `sessionMessageVersion`

**位置**: [useSessionStore.ts:166-313](file:///Users/mac/AI/CScode/src/cscode/web/src/stores/useSessionStore.ts#L166-L313)

所有事件处理分支（`text.delta`, `step.started`, `text.ended`, `tool.called` 等）**都不更新 `sessionMessageVersion`**。

例如 `text.delta`:
```typescript
case 'text.delta': {
  // ...
  return {
    sessionThinking: { ...s.sessionThinking, [sessionId]: true },
    sessionMessages: { ...s.sessionMessages, [sessionId]: updated },
    // ❌ 不更新 sessionMessageVersion！
  };
}
```

#### Bug 4: Version Guard 形同虚设

**位置**: [Sidebar.tsx:54-58](file:///Users/mac/AI/CScode/src/cscode/web/src/components/layout/Sidebar.tsx#L54-L58)

```typescript
const currentVersion = currentStore.sessionMessageVersion[id] || 0;
if (currentVersion > cachedVersion) {
  console.log('[sidebar] VERSION CHANGED... discarding stale server data');
  return;
}
setMessages(msgs, id);
```

**设计意图**: 如果 fetch 期间有新的本地消息追加（version 增加），就丢弃服务器返回的过时数据。

**实际效果**: 
- `cachedVersion = store.sessionMessageVersion[id]` (fetch 前)
- fetch 期间，后台流推送 `text.delta` -> `applyEvent` 更新消息
- 但 `applyEvent` **不更新 version**！
- `currentVersion = store.sessionMessageVersion[id]` (fetch 后)
- `currentVersion === cachedVersion` (因为都没变)
- `currentVersion > cachedVersion` = **false**
- Version Guard **永远不会触发**！

#### Bug 5: catch 分支直接清空消息

**位置**: [Sidebar.tsx:64-75](file:///Users/mac/AI/CScode/src/cscode/web/src/components/layout/Sidebar.tsx#L64-L75)

```typescript
} catch {
  console.log('[sidebar] fetch failed for session=%s', id);
  const currentStore = useSessionStore.getState();
  if (currentStore.activeSessionId === id) {
    const currentVersion = currentStore.sessionMessageVersion[id] || 0;
    if (currentVersion > cachedVersion) {
      return;
    }
    setMessages([], id);  // ❌ fetch 失败时直接清空消息！
  }
}
```

如果 `api.session.messages()` 请求失败（网络错误、服务器错误等），会**直接清空该 session 的所有消息**！

---

## 四、Bug 触发条件

| 条件 | 说明 |
|------|------|
| 多 Session 并行 | 至少两个 session 同时与 LLM 交互 |
| LLM 流式响应中 | session 正在接收 `text.delta` 流式事件 |
| 用户切换 session | 点击左侧 sidebar 切换到另一个 session |
| 切换回原 session | 再次点击回到正在执行任务的 session |

---

## 五、Bug 触发时序图

```
时间线 ->

Session A: 用户发送消息
  -> sendMessage()
    -> appendMessage(user_msg)                    [version=1]
    -> POST /api/chat/stream
      <- 服务器开始流式响应
        -> applyEvent('text.delta', 'Hello')      [version=1, messages=['user_msg', 'assistant_hello']]
        -> applyEvent('text.delta', ' world')     [version=1, messages=['user_msg', 'assistant_hello world']]
        -> applyEvent('text.delta', '!')          [version=1, messages=['user_msg', 'assistant_hello world!']]

用户: 点击切换到 Session B
  -> handleSelectSession(sessionB)

用户: 点击切换回 Session A
  -> handleSelectSession(sessionA)
    -> cachedVersion = sessionMessageVersion[sessionA] = 1
    -> api.session.messages(sessionA) 开始请求
      
      (请求期间，Session A 的后台流继续...)
      -> applyEvent('text.delta', ' How')         [version=1, 消息继续累积]
      -> applyEvent('text.delta', ' are')         [version=1, 消息继续累积]
      
    <- api.session.messages(sessionA) 返回
       服务器只返回了已持久化的消息: ['user_msg']
       
    -> currentVersion = sessionMessageVersion[sessionA] = 1
    -> currentVersion(1) > cachedVersion(1) ? NO! (Version Guard 失效)
    -> setMessages(['user_msg'], sessionA)
       ❌ 本地累积的 'assistant_hello world! How are' 被覆盖！
```

---

## 六、修复建议

### 方案 1: 修复 Version Guard（推荐）

让 `applyEvent` 和 `setMessages` 正确更新 `sessionMessageVersion`。

```typescript
// applyEvent 中每个更新 sessionMessages 的分支都需要更新 version

case 'text.delta': {
  // ...
  const newVersion = (s.sessionMessageVersion[sessionId] || 0) + 1;
  return {
    sessionThinking: { ...s.sessionThinking, [sessionId]: true },
    sessionMessages: { ...s.sessionMessages, [sessionId]: updated },
    sessionMessageVersion: { ...s.sessionMessageVersion, [sessionId]: newVersion },  // 新增
  };
}

// setMessages 也需要更新 version
setMessages: (messages, sessionId) => set((s) => {
  // ...
  const newVersion = (s.sessionMessageVersion[sessionId] || 0) + 1;
  return {
    sessionMessages: { ...s.sessionMessages, [sessionId]: filtered },
    sessionMessageVersion: { ...s.sessionMessageVersion, [sessionId]: newVersion },  // 新增
  };
}),
```

### 方案 2: setMessages 改为合并逻辑（更安全）

```typescript
setMessages: (messages, sessionId) => set((s) => {
  const current = s.sessionMessages[sessionId] || [];
  // 合并策略：保留本地已有但服务器没有的消息（如流式中的消息）
  const serverIds = new Set(messages.map(m => m.id).filter(Boolean));
  const localOnly = current.filter(m => m.id && !serverIds.has(m.id));
  const merged = [...messages, ...localOnly];
  // ...
}),
```

### 方案 3: 切换 session 时中止后台流

在 `handleSelectSession` 中切换 session 时，中止非活动 session 的流：

```typescript
const handleSelectSession = useCallback(async (id: string) => {
  const store = useSessionStore.getState();
  const prevId = store.activeSessionId;
  
  if (prevId && prevId !== id) {
    abortSession(prevId);  // 中止旧 session 的流
  }
  
  setActiveSession(id);
  // ...
}, [setActiveSession, setMessages]);
```

**注意**: 这与当前 P0-6 的设计（"不 abort 旧 session 的流"）冲突，需要重新评估。

---

## 七、代码位置汇总

| 文件 | 行号 | 问题 |
|------|------|------|
| [useSessionStore.ts](file:///Users/mac/AI/CScode/src/cscode/web/src/stores/useSessionStore.ts#L166-L313) | 166-313 | `applyEvent` 不更新 `sessionMessageVersion` |
| [useSessionStore.ts](file:///Users/mac/AI/CScode/src/cscode/web/src/stores/useSessionStore.ts#L339-L354) | 339-354 | `setMessages` 直接替换消息且不更新 version |
| [Sidebar.tsx](file:///Users/mac/AI/CScode/src/cscode/web/src/components/layout/Sidebar.tsx#L54-L58) | 54-58 | Version Guard 因 version 不更新而失效 |
| [Sidebar.tsx](file:///Users/mac/AI/CScode/src/cscode/web/src/components/layout/Sidebar.tsx#L64-L75) | 64-75 | catch 分支直接清空消息 |

---

## 八、结论

**这是一个架构级设计缺陷，不是简单的代码错误。**

Version Guard 的设计意图是正确的（防止服务器旧数据覆盖本地新数据），但实现不完整：
1. `applyEvent` 更新消息但不更新 version → Version Guard 无法检测变化
2. `setMessages` 不更新 version → 连续调用 setMessages 无法区分
3. `setMessages` 直接替换消息 → 没有合并/保护机制

**修复优先级**: P0 - 立即修复

**修复复杂度**: 中等（需要修改多处代码，确保 version 一致性）
