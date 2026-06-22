# Session 架构：1:1 复刻 opencode

## 问题

CScode 的 Session 管理与 opencode 存在 5 项关键差异，导致数据丢失、竞态条件和状态混乱：

1. **全局 `_agent` 单例** — 所有 Session 共用一个 `Agent` 实例。每次 HTTP 请求都会重新赋值 `_agent.provider` 和 `_agent.config`，当两个 Session 使用不同 Provider 时会产生竞态条件。
2. **缺少 Session 级并发锁** — 对同一 Session 重复发送消息会产生两个并发的 SSE 流，争夺修改同一消息列表。
3. **`save_messages` 先删后插**（`session.py:74-93`）— 先删除 Session 的所有消息再重新插入。如果两个请求交错执行，消息会永久丢失。
4. **System 消息被持久化到 DB** — `app.py:426` 在 `save_messages` 持久化之前将 SYSTEM prompt 插入消息列表。下次加载时，System 消息会随着每次对话轮次重复。
5. **`messages.session_id` 缺少索引** — 随着消息数量增加，性能会下降。

## 解决方案

### 1. Session 并发锁（后端）

添加 `SessionLockManager`，使用非阻塞的 per-session 锁。由于 CScode 可能在 Python <3.13 上运行（macOS 默认），使用自定义的 `EventLock` 类：

```python
class EventLock:
    """为 Python <3.13 提供 try_acquire() 的锁。"""
    def __init__(self):
        self._locked = False
        self._waiters: list[asyncio.Event] = []

    async def acquire(self):
        while self._locked:
            evt = asyncio.Event()
            self._waiters.append(evt)
            await evt.wait()
        self._locked = True

    def try_acquire(self) -> bool:
        if self._locked:
            return False
        self._locked = True
        return True

    def release(self):
        self._locked = False
        if self._waiters:
            self._waiters.pop(0).set()


class SessionLockManager:
    _locks: dict[str, EventLock] = {}
    _dict_lock = asyncio.Lock()

    @classmethod
    async def try_lock(cls, session_id: str) -> bool:
        async with cls._dict_lock:
            if session_id not in cls._locks:
                cls._locks[session_id] = EventLock()
        return cls._locks[session_id].try_acquire()

    @classmethod
    def unlock(cls, session_id: str) -> None:
        if session_id in cls._locks:
            cls._locks[session_id].release()
```

**行为**：当 `chat_stream` 收到一个已正在处理中的 Session 请求时，返回错误 SSE 事件，而不是启动第二个流。`unlock` 必须在 `finally` 块中调用。

### 2. 修复 `save_messages` — 仅追加 + 过滤 System 消息

**当前**：删除所有消息，重新插入整个列表（易竞态 + 持久化 System prompt）。
**新方案**：在 Session 开始时跟踪消息数量，只持久化新的非 System 消息：

```python
# 在 SessionStore 中：
async def get_message_count(self, session_id: str) -> int:
    cursor = await self._db.conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
    )
    row = await cursor.fetchone()
    return row[0] if row else 0

async def append_messages(self, session_id: str, messages: List[Message]) -> None:
    """仅追加插入。过滤 SYSTEM 消息。不删除。"""
    now = datetime.now(timezone.utc).isoformat()
    for msg in messages:
        if msg.role == MessageRole.SYSTEM:
            continue
        await self._db.conn.execute(
            """INSERT INTO messages
               (session_id, role, content, tool_calls, tool_call_id, name, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, msg.role.value, msg.content,
             json.dumps(msg.tool_calls) if msg.tool_calls else None,
             msg.tool_call_id, msg.name, now),
        )
    await self._db.conn.commit()
```

调用方用法：

```python
# 在 chat_stream 中，Session 入口处：
existing_count = await _session_store.get_message_count(session_id)

# 处理完成后（在 finally 或 complete 块中）：
new_messages = messages[existing_count:]
await _session_store.append_messages(session_id, new_messages)
```

**为什么仅追加**：完全消除了先删后插的竞态条件。即使两个并发的 `append_messages` 调用交错执行，数据也不会丢失——两组插入操作是独立的。

### 3. 修复 Provider 竞态条件

**当前**：每次请求都执行 `_agent.provider = create_provider(config)`。
**修复**：仅在配置实际发生变化时才更新 Provider：

```python
saved_config = await store.get()
if saved_config:
    from cscode.core.config import Config
    config = Config.from_dict(saved_config)
    if (_agent.config is None or 
        _agent.config.model != config.model or 
        _agent.config.provider != config.provider):
        provider = create_provider(config)
        _agent.provider = provider
        _agent.config = config
```

### 4. Session 状态机

为 Session 添加 `state` 字段：

**后端**：在 app.py 中添加内存 `session_states: dict[str, str]`。

状态：
- `idle` — 可处理
- `processing` — 正在流式处理
- `error` — 上次流处理以错误结束（下次开始时自动清除）

```python
session_states: dict[str, str] = {}

# 在 chat_stream 中，处理前：
state = session_states.get(session_id, "idle")
if state == "processing":
    yield f"data: {json.dumps({'type': 'error', 'content': 'Session 正在处理中'})}\n\n"
    return

session_states[session_id] = "processing"
try:
    # ... 处理 ...
    session_states[session_id] = "idle"
except Exception:
    session_states[session_id] = "error"
    raise
```

**前端**：在 Store 中添加：

```typescript
interface SessionState {
  sessions: Session[];
  sessionStates: Record<string, 'idle' | 'processing' | 'error'>;
  // ...
}
```

### 5. 数据库迁移 v003

```sql
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
ALTER TABLE sessions ADD COLUMN state TEXT NOT NULL DEFAULT 'idle';
```

### 6. 前端：禁止向处理中的 Session 重复发送

```typescript
// 在 Composer.tsx 中
const isProcessing = useSessionStore((s) => s.sessionStates[activeSessionId]) === 'processing';

// handleSend:
if (isProcessing) return; // 静默阻止
```

## 影响分析

| 变更 | 风险 | 收益 | 工作量 |
|------|------|------|--------|
| Session 锁 | 低 — 独立新类 | 防止重复发送导致的数据损坏 | 小 |
| 修复 save_messages | 中 — 消息持久化路径 | 防止数据丢失 + 系统消息重复 | 小 |
| Provider 竞态修复 | 低 — 仅增加守卫条件 | 防止 Provider 不匹配 | 极小 |
| Session 状态 | 低 — 增量、非破坏性 | 更好的 UX、阻塞层 | 小 |
| 数据库迁移 | 低 — 追加列/索引 | 性能、前瞻性 | 极小 |

## 发布顺序

1. Session 锁 + Provider 竞态修复（仅后端，立即可靠）
2. 修复 save_messages（后端，改变数据持久化方式）
3. 数据库迁移 v003（后端，轻微 Schema 变更）
4. Session 状态 + 前端阻止（前端 + 后端，UX）

## 验收标准

1. 同时向同一 Session 发送两条消息 → 第二条被拒绝并返回错误
2. 完成后加载 Session → System prompt 精确出现一次，无重复
3. 处理过程中切换 Session → 第一个 Session 继续处理不受干扰
4. `save_messages` 并发调用 → 无数据丢失（仅追加安全）
5. 不同 Session 使用不同 Provider → 无 Provider 冲突
6. Session 状态在流处理期间显示"processing"，其他时候显示"idle"
7. Session 处理中时 Composer 按钮禁用
