# CScode 并发 Session 隔离测试报告

**测试日期**: 2026-07-08
**测试场景**: 两个 session 并发处理 LLM 任务，手动切换观察进展
**测试方法**: curl 并发请求 + 代码审查 + 事件存储验证 + 后端日志分析

---

## 1. 测试设计

### 场景描述
1. 创建 Session A 和 Session B
2. 同时向两个 session 发送不同任务（A: 中文春日诗，B: 英文秋天诗）
3. 在任务执行过程中切换 session 观察进展
4. 验证 session 隔离：消息不乱窜、任务正常执行

### 测试矩阵

| 测试组 | Session A 任务 | Session B 任务 | 预期结果 |
|--------|---------------|---------------|---------|
| curl 并发 | 中文春日诗 | 英文秋天诗 | 各自独立完成，内容不串扰 |
| curl 并发 | 1+1=? (中文) | 2+2=? (英文) | A=2, B=4 |

---

## 2. 后端隔离验证结果

### 2.1 后端隔离机制

| 机制 | 位置 | 说明 |
|------|------|------|
| Per-session 锁 | [session.py:63-90](file:///Users/mac/AI/CScode/src/cscode/core/session.py#L63-L90) | `SessionLockManager` 为每个 session 提供独立锁，不同 session 可并发执行 |
| 事件 session_id 标记 | [app.py:500-501](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L500-L501) | 每个 SSE 事件都带 `session_id` 字段 |
| 事件存储隔离 | EventStore | 事件按 `aggregate_id` 隔离存储 |
| 并发锁检查 | [app.py:455](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L455) | 同一 session 重复请求会被拒绝 |

### 2.2 后端测试结果

**测试组 1: 中文诗 + 英文诗**

| 验证项 | 结果 |
|--------|------|
| Session A 内容 | `# 春日\n\n碧柳轻摇映池塘，\n桃花绽放满山岗。\n燕归细语呢喃过，\n风送清香入画廊。` ✅ |
| Session B 内容 | `# Autumn\n\nGolden leaves dance on the cooling breeze,\nCrimson maples whisper through the trees,\nHarvest moon rises, crisp air sighs,\nNature prepares for slumber as autumn dies.` ✅ |
| session_id 标记 | 每个事件都正确标记对应 session_id ✅ |
| 事件串扰 | 无串扰 ✅ |

**测试组 2: 数学题**

| 验证项 | 结果 |
|--------|------|
| Session A (1+1, 中文) | 回答 "2" ✅ |
| Session B (2+2, 英文) | 回答 "4" ✅ |
| 内容串扰 | 无 ✅ |

### 2.3 后端事件存储验证

```
Session A (1783470467243733000) - 6 events:
  seq=1 session.created    title="Concurrent Test A"
  seq=2 prompt.admitted    prompt="请用中文写一首关于春天的诗"
  seq=3 step.started
  seq=4 text.ended         content="# 春日\n\n碧柳轻摇映池塘..."
  seq=5 step.ended
  seq=6 compaction         baseline_seq=5

Session B (1783470471779992000) - 6 events:
  seq=1 session.created    title="Concurrent Test B"
  seq=2 prompt.admitted    prompt="Please write a poem about autumn in English"
  seq=3 step.started
  seq=4 text.ended         content="# Autumn\n\nGolden leaves dance..."
  seq=5 step.ended
  seq=6 compaction         baseline_seq=5
```

**结论**: 后端 session 隔离完美，事件按 aggregate_id 正确分离，无串扰。

---

## 3. 前端隔离验证结果

### 3.1 前端隔离机制分析

| 机制 | 位置 | 说明 |
|------|------|------|
| session_id 过滤 | [useChat.ts:133-136](file:///Users/mac/AI/CScode/src/cscode/web/src/hooks/useChat.ts#L133-L136) | 丢弃 `event.session_id !== capturedSid` 的事件 |
| isCurrentStream() | [useChat.ts:138-141](file:///Users/mac/AI/CScode/src/cscode/web/src/hooks/useChat.ts#L138-L141) | 检查 `activeId === capturedSid`，非当前 session 的事件被丢弃 |
| abortSession | [Sidebar.tsx:42-44](file:///Users/mac/AI/CScode/src/cscode/web/src/components/layout/Sidebar.tsx#L42-L44) | 切换 session 时中止前一个 session 的流 |
| 缓存命中跳过拉取 | [Sidebar.tsx:49-52](file:///Users/mac/AI/CScode/src/cscode/web/src/components/layout/Sidebar.tsx#L49-L52) | 有缓存消息时跳过服务器拉取 |
| Store 分区 | useSessionStore.ts | `sessionMessages`/`sessionToolCalls` 按 session ID 分区 |

### 3.2 发现的问题

---

## 4. 发现的问题

### P0-5: 自动 compaction 每次响应后清空所有消息

**严重程度**: P0（极严重 — 影响所有用户、所有 session）

- **位置**: 
  - 触发: [app.py:670](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L670) — 每次聊天响应后自动调用
  - 执行: [compactor.py:19-58](file:///Users/mac/AI/CScode/src/cscode/server/compactor.py#L19-L58) — `baseline_seq = events[-1].seq`
  - 影响: [session.py:198-205](file:///Users/mac/AI/CScode/src/cscode/core/session.py#L198-L205) — 过滤 `seq >= baseline_seq` 的消息

- **问题链条**:
  1. 每次聊天完成后，`_auto_compact()` 被调用
  2. `Compactor.compact()` 设置 `baseline_seq = events[-1].seq`（即 `step.ended` 的 seq=5）
  3. 投影器执行 `messages = [m for m, s in zip(messages, msg_seqs) if s >= baseline_seq]`
  4. 用户消息 seq=2 和 AI 消息 seq=4 都 < 5，被过滤掉
  5. 结果：`/api/sessions/{id}/messages` 返回空数组

- **证据**:
  ```
  Session A events:
    seq=2 prompt.admitted  ← 用户消息
    seq=4 text.ended       ← AI回复
    seq=5 step.ended       ← 最后事件
    seq=6 compaction       ← baseline_seq=5

  Projector: filter seq >= 5 → 0 messages
  API response: []
  ```

- **影响**: 
  - 所有 session 的消息历史丢失
  - 前端切换 session 后无法加载历史消息
  - LLM 上下文丢失，多轮对话无法正常工作

- **根因**: 
  1. Compaction 在每次响应后无条件触发（应该有阈值）
  2. `baseline_seq` 设为最后事件的 seq，但消息事件的 seq 都小于它
  3. Compaction 没有从 snapshot 创建替换消息

- **修复建议**:
  1. 添加 compaction 阈值（如消息数 > 50 才触发）
  2. 修复 `baseline_seq` 逻辑：应该保留最新消息，只压缩旧消息
  3. 在投影器中用 compaction snapshot 创建系统消息替代被压缩的消息

---

### P0-6: 前端切换 session 时中止正在进行的流

**严重程度**: P0（严重 — 影响并发 session 场景）

- **位置**: [Sidebar.tsx:42-44](file:///Users/mac/AI/CScode/src/cscode/web/src/components/layout/Sidebar.tsx#L42-L44)
- **问题**:
  ```typescript
  if (prevId && prevId !== id) {
      abortSession(prevId);  // ← 中止前一个 session 的流
  }
  ```
  切换 session 时，前一个 session 的 SSE 流被中止。虽然后端继续处理，但前端不再接收事件。

- **影响**:
  - 用户在 Session A 处理中切换到 Session B
  - Session A 的流被中止，AI 回复丢失
  - 切换回 Session A 时，看不到完整回复

- **修复建议**: 不中止流，让后端事件继续在后台应用 to store。移除 `abortSession(prevId)` 调用，或改为只中止用户主动取消的流。

---

### P0-7: 前端丢弃非活跃 session 的事件

**严重程度**: P0（严重 — 影响并发 session 场景）

- **位置**: [useChat.ts:138-141](file:///Users/mac/AI/CScode/src/cscode/web/src/hooks/useChat.ts#L138-L141)
- **问题**:
  ```typescript
  const isCurrentStream = () => {
      const activeId = useSessionStore.getState().activeSessionId;
      return streamControllers[capturedSid] === controller && activeId === capturedSid;
      //                                                        ^^^^^^^^^^^^^^^^^^^^^^^^
      //     这一行导致非活跃 session 的事件被丢弃
  };
  ```
  `isCurrentStream()` 要求当前活跃 session 等于事件来源 session。如果用户切换到另一个 session，所有事件（包括 `complete`）都被丢弃。

- **影响**:
  - 即使不中止流（P0-6 修复后），事件仍然会被丢弃
  - `complete` 事件被丢弃 → AI 回复不会添加到 store
  - `text.ended` 事件被丢弃 → 消息不会更新
  - `tool.called`/`tool.success` 事件被丢弃 → 工具调用不显示

- **修复建议**: 移除 `activeId === capturedSid` 条件。`applyEvent` 已经用 session ID 作为 key，不会有串扰风险：
  ```typescript
  const isCurrentStream = () => {
      return streamControllers[capturedSid] === controller;
  };
  ```

---

### P1-5: 前端缓存命中时跳过服务器拉取

**严重程度**: P1（中等 — 导致显示不完整）

- **位置**: [Sidebar.tsx:49-52](file:///Users/mac/AI/CScode/src/cscode/web/src/components/layout/Sidebar.tsx#L49-L52)
- **问题**:
  ```typescript
  if (cached !== undefined && cached.length > 0) {
      console.log('[sidebar] <<< cached hit, skip fetch');
      setActiveSession(id);
      return;  // ← 跳过服务器拉取
  }
  ```
  如果 session 有缓存消息（即使不完整），切换回来时不从服务器拉取最新数据。

- **影响**: 
  - 用户切换走再切回来时，看到的是缓存中的部分消息
  - 即使后端已完成处理，前端也不更新

- **修复建议**: 切换 session 时总是从服务器拉取最新消息，或添加一个标志标记缓存是否需要刷新。

---

## 5. 测试结论

### 5.1 后端隔离评估

| 评估项 | 结果 |
|--------|------|
| Session 并发执行 | ✅ 两个 session 同时处理，互不阻塞 |
| 事件 session_id 标记 | ✅ 每个事件正确标记 |
| 事件存储隔离 | ✅ 按 aggregate_id 隔离 |
| 消息内容隔离 | ✅ 无串扰 |
| Session 锁机制 | ✅ 同 session 重复请求被拒绝 |

### 5.2 前端隔离评估

| 评估项 | 结果 |
|--------|------|
| Store 分区隔离 | ✅ 按 session ID 分区 |
| session_id 事件过滤 | ✅ 丢弃错误 session 的事件 |
| 流切换处理 | ❌ 中止正在进行的流 (P0-6) |
| 非活跃 session 事件 | ❌ 丢弃所有事件 (P0-7) |
| 缓存刷新 | ❌ 缓存命中跳过拉取 (P1-5) |

### 5.3 消息持久化评估

| 评估项 | 结果 |
|--------|------|
| 事件存储 | ✅ 事件正确保存到 EventStore |
| 消息重建 | ❌ compaction 清空所有消息 (P0-5) |
| API 返回 | ❌ /messages 返回空数组 |

### 5.4 总结

| 层级 | 隔离状态 | 问题数 |
|------|---------|--------|
| 后端 | ✅ 完美隔离 | 0 |
| 前端 | ❌ 存在隔离缺陷 | 3 (2 P0 + 1 P1) |
| 持久化 | ❌ 消息丢失 | 1 (P0) |

**后端并发隔离机制完善**，两个 session 可以同时处理不同任务，事件和内容无串扰。

**前端存在严重的隔离缺陷**：切换 session 时中止流、丢弃非活跃 session 的事件、缓存命中跳过拉取，这三个问题联合导致并发 session 场景下用户体验严重受损。

**消息持久化存在致命 bug**：自动 compaction 在每次响应后清空所有消息，导致历史记录完全丢失。

---

## 6. 修复优先级

| 优先级 | 问题 | 影响 |
|--------|------|------|
| P0-5 | 自动 compaction 清空消息 | 所有 session 消息丢失 |
| P0-7 | 前端丢弃非活跃 session 事件 | 并发场景 AI 回复丢失 |
| P0-6 | 前端切换 session 中止流 | 并发场景流被中断 |
| P1-5 | 缓存命中跳过拉取 | 切换后显示不完整 |

---

*报告生成时间: 2026-07-08*
