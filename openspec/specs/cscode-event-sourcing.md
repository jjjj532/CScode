# CScode Event Sourcing 架构

基于 opencode 源码（/tmp/opencode）的 Event Sourcing + CQRS 模式，在 Python/FastAPI 栈上落地。

## 1. 指导思想

**所有状态变更都是不可变事件。** 你不是在 "保存消息"，而是在 "记录发生了什么"。

```
用户输入 → 事件 → EventStore（追加写，永不删改）
                     ↓
               Coordinator（per-session 队列 + 状态机）
                     ↓
               Processor（读取事件 → 构建 LLM 上下文 → 产生新事件）
                     ↓
               EventStore（追加写新事件）
                     ↓
               Projector（监听事件 → 更新投影表）
                     ↓
               Subscription（独立 SSE 推送给前端）
```

## 2. 事件定义

每个事件有且仅有这些字段：

```python
@dataclass
class Event:
    aggregate_id: str          # session_id
    seq: int                   # per-aggregate 自增序号
    type: str                  # 事件类型
    data: dict                 # 事件载荷
    created_at: float          # time.time()
```

### 事件类型表

| 类型 | 数据载荷 | 用途 |
|------|---------|------|
| `session.created` | `{id, title, agent, model, ...}` | 新 session |
| `session.updated` | `{title?, agent?, model?}` | 更新元数据 |
| `prompt.admitted` | `{message_id, prompt, delivery}` | 用户输入已接收 |
| `prompt.promoted` | `{seq}` | 输入已开始处理 |
| `step.started` | `{round}` | LLM 调用开始 |
| `text.delta` | `{content}` | LLM 文本增量（不持久化） |
| `text.ended` | `{content}` | LLM 文本完成 |
| `tool.called` | `{name, args, round}` | 工具开始执行 |
| `tool.success` | `{name, result}` | 工具执行成功 |
| `tool.failed` | `{name, error}` | 工具执行失败 |
| `step.ended` | `{round, finish_reason}` | LLM 一次调用完成 |
| `error` | `{message, recoverable}` | 错误发生 |
| `compaction` | `{snapshot, baseline_seq}` | 上下文压缩 |
| `session.deleted` | `{}` | Session 已删除 |

**Delta 事件不持久化**（opencode 的做法）。`text.delta` 只通过 SSE 实时推送给前端，不入库。

## 3. 存储层

### 3.1 Event Store（核心）

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aggregate_id TEXT NOT NULL,        -- session_id
    seq INTEGER NOT NULL,              -- per-aggregate 递增
    type TEXT NOT NULL,
    data TEXT NOT NULL,                 -- JSON
    created_at REAL NOT NULL,           -- time.time()
    UNIQUE(aggregate_id, seq)
);
CREATE INDEX idx_events_aggregate ON events(aggregate_id, seq);
```

```python
class EventStore:
    async def append(self, aggregate_id: str, events: list[Event]) -> list[Event]:
        """追加写。自动分配 seq。线程安全。"""

    async def read(self, aggregate_id: str, after_seq: int = 0, limit: int = 1000) -> list[Event]:
        """读取事件。用于重放/构建状态。"""

    async def subscribe(self, aggregate_id: str, after_seq: int = 0) -> AsyncIterator[Event]:
        """实时订阅。轮询 + asyncio.Event 唤醒。"""
```

### 3.2 投影表（Projection）

```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,                -- UUID
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tool_calls TEXT,
    tool_call_id TEXT,
    name TEXT,
    event_seq INTEGER NOT NULL,         -- 创建此消息的事件 seq
    created_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX idx_messages_session ON messages(session_id, event_seq);

CREATE TABLE context_epochs (
    session_id TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    baseline_seq INTEGER NOT NULL,      -- 此 seq 之前的消息被过滤
    agent TEXT,
    model TEXT,
    snapshot TEXT,                       -- 压缩后的系统提示
    created_at REAL NOT NULL,
    PRIMARY KEY (session_id, epoch)
);
```

`messages` 表是**只追加不删除**的投影。从事件重放可以完全重建。

### 3.3 Session 表（不变量）

保留现有的 `sessions` 表，去掉直接操作 messages 的方法。

## 4. 并发控制（Coordinator）

基于 opencode 的 `RunCoordinator` + `Runner` 状态机，适配 Python：

```python
class SessionCoordinator:
    """
    每个 Session 一个状态机。
    状态: idle → draining → draining+queued → idle
    最多 1 active + 1 queued。
    """

    class State(Enum):
        IDLE = "idle"
        DRAINING = "draining"      # 正在处理
        QUEUED = "queued"          # 有排队等待的请求

    _entries: dict[str, _Entry] = {}
    _lock = asyncio.Lock()

    async def run(self, session_id: str) -> None:
        """显式运行。如果 draining 则加入等待队列。"""

    async def wake(self, session_id: str) -> None:
        """告示。与现有 demand 合并。"""

    async def interrupt(self, session_id: str) -> None:
        """中断当前处理。"""
```

### 状态转换

```
IDLE --run/wake--> DRAINING
DRAINING --run--> DRAINING + QUEUED  (caller 等待当前链完成)
DRAINING --wake--> DRAINING + COALESCED  (与现有告示合并)
DRAINING (完成) + QUEUED --> DRAINING (开始排队任务)
DRAINING (完成) + 无排队 --> IDLE
```

## 5. Processor（LLM 流水线）

从 engine.py 的 `_run_loop` 重构。不再直接操作 `messages` 列表，而是：

```python
class SessionProcessor:
    async def process(self, session_id: str, event_store: EventStore, projector: Projector) -> None:
        # 1. 从 EventStore 读取事件
        events = await event_store.read(session_id)

        # 2. 用 Projector 构建 LLM 上下文消息
        #    (过滤掉 baseline_seq 之前的 system 消息)
        context = await projector.build_context(session_id, events)

        # 3. 循环调用 LLM
        while tool_rounds < max_rounds:
            await self._emit("step.started", {"round": tool_rounds})

            result = await provider.complete(context, tools=...)

            # 记录文本事件
            await self._emit("text.ended", {"content": result.content})
            context.append(assistant_msg)

            if not result.tool_calls:
                await self._emit("step.ended", {"round": tool_rounds})
                break

            for tc in result.tool_calls:
                await self._emit("tool.called", {"name": tc.name, "args": tc.args, "round": tool_rounds})
                tool_result = await registry.execute(tc)
                await self._emit("tool.success" if tool_result.success else "tool.failed", {...})
                context.append(tool_msg)

            tool_rounds += 1

    async def _emit(self, type: str, data: dict) -> None:
        """processor 不直接写 EventStore，通过回调发射事件。
        由调用方决定如何持久化 + 通知 projector + 推送给前端。"""
        await self._on_event(Event(type=type, data=data))
```

核心变化：`_run_loop` 变成**发射事件**而不是**追加消息**。消息列表是本地临时变量，由 Projector 从事件重建。

## 6. Projector（事件 → 投影）

```python
class Projector:
    """监听事件，更新投影表。"""

    async def on_event(self, event: Event) -> None:
        match event.type:
            case "session.created":
                await self._insert_session(event)
            case "text.ended":
                await self._insert_message(event, role="assistant")
            case "tool.called":
                await self._insert_tool_call(event)
            case "tool.success" | "tool.failed":
                await self._update_tool_result(event)
            case "compaction":
                await self._insert_epoch(event)

    async def build_context(self, session_id: str, events: list[Event]) -> list[Message]:
        """从事件重建 LLM 上下文。
        - 过滤掉 baseline_seq 之前的 system 消息
        - 按 seq 排序
        - 返回 Message[]"""
```

## 7. API 端点

### 7.1 提交 prompt

```http
POST /api/chat/prompt
{
    "session_id": "xxx",
    "message": "...",
    "files": [...]
}
→ 202 Accepted
{
    "session_id": "xxx",
    "admitted_seq": 42,
    "status": "queued"
}
```

不在此处流式返回。只确认接收。

### 7.2 SSE 事件订阅

```http
GET /api/events?session_id=xxx&after_seq=42
Content-Type: text/event-stream

event: text.delta
data: {"content": "Hello"}

event: tool.called
data: {"name": "Bash", "args": "ls -la", "round": 1}

event: tool.success
data: {"name": "Bash", "result": "..."}

event: complete
data: {"content": "Final response"}
```

前端在 onerror 时用当前 seq 重连。

### 7.3 消息查询（已有，但改从投影表读取）

```http
GET /api/sessions/:id/messages
→ messages 投影表内容（不包含 delta 事件）
```

## 8. 前端改动

### 8.1 useChat.ts 重构

```typescript
// 旧：一个 POST 跑完整个流
// 新：分两步

// Step 1: 提交 prompt
const admitted = await fetch('/api/chat/prompt', {
    method: 'POST',
    body: JSON.stringify({ session_id, message, files })
}).then(r => r.json());
// admitted = { admitted_seq: 42, session_id: "xxx" }

// Step 2: 订阅事件流（可断线重连）
const subscribe = (sessionId: string, afterSeq: number) => {
    const es = new EventSource(`/api/events?session_id=${sessionId}&after_seq=${afterSeq}`);
    es.addEventListener('text.delta', (e) => handleTextDelta(JSON.parse(e.data)));
    es.addEventListener('tool.called', (e) => handleToolCalled(JSON.parse(e.data)));
    es.addEventListener('tool.success', (e) => handleToolSuccess(JSON.parse(e.data)));
    es.addEventListener('complete', (e) => handleComplete(JSON.parse(e.data)));
    es.onerror = () => {
        es.close();
        setTimeout(() => subscribe(sessionId, lastSeq), 1000); // 重连
    };
};
```

### 8.2 Store 改为 Event Reducer

借用 opencode 的 event-reducer.ts 模式：

```typescript
// 每个事件类型对应一个 reducer
const reducers = {
    'text.delta': (state, event) => {
        // 追加/更新当前 assistant 消息内容
    },
    'tool.called': (state, event) => {
        // 添加 tool call 到当前列表
    },
    'tool.success': (state, event) => {
        // 更新 tool call 状态
    },
    'complete': (state, event) => {
        // 最终消息入库，清空 tool calls
    },
};
```

## 9. 实施阶段

### Phase 1: EventStore + Coordinator（基础架构）

| 文件 | 操作 |
|------|------|
| `src/cscode/storage/event_store.py` | **新建** EventStore（append/read/subscribe） |
| `src/cscode/server/coordinator.py` | **新建** SessionCoordinator（run/wake/interrupt） |
| `src/cscode/storage/db.py` | **改** 添加 events/context_epochs 表迁移 |

### Phase 2: Projector + Processor 重构

| 文件 | 操作 |
|------|------|
| `src/cscode/server/projector.py` | **新建** Projector（event → messages/epochs） |
| `src/cscode/core/engine.py` | **重构** _run_loop 改为发射事件 |
| `src/cscode/server/app.py` | **改** chat_stream 使用 EventStore + Coordinator + Projector |
| `src/cscode/storage/session.py` | **改** 去掉 save_messages/get_messages，改为投影读取 |

### Phase 3: SSE 订阅

| 文件 | 操作 |
|------|------|
| `src/cscode/server/subscription.py` | **新建** SSE 订阅管理器 |
| `src/cscode/server/app.py` | **改** 添加 `/api/events` SSE 端点 |

### Phase 4: 前端适配

| 文件 | 操作 |
|------|------|
| `src/cscode/web/src/hooks/useChat.ts` | **重构** POST submit + EventSource subscribe |
| `src/cscode/web/src/stores/useSessionStore.ts` | **改** 事件 reducer |
| `src/cscode/web/src/components/chat/*.tsx` | **微调** 适配新事件流 |

## 10. 验收标准

1. 同 Session 连点两次发送 → 第二次排队，不丢失
2. 前端断线重连 → 从 last_seq 继续接收，消息不重复不丢失
3. 加载历史 Session → System 消息只出现一次
4. 消息查询不依赖内存，从投影表读取
5. 从事件重放可完全重建 session 状态
6. Compaction 后上下文大小受控，旧 system 消息被过滤
7. 并发测试：10 个 session 同时发消息 → 无死锁、无数据损坏

## 11. 与当前代码的兼容策略

Phase 1-2 完成后，旧的 `/api/chat/stream` 端点仍然可用，内部适配为：
1. 接收 POST → EventStore.append("prompt.admitted")
2. Coordinator.run() → 处理完
3. 从 EventStore 读取最终事件 → 构造 SSE 流返回

这样前端可以逐步迁移，不一次性全改。
