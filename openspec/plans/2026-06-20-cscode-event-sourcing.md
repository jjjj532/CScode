# CScode Event Sourcing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan. Steps use `- [ ]` syntax.

**Goal:** Replace direct message persistence with event sourcing (EventStore + Coordinator + Projector) for 1:1 replication of opencode's session reliability.

**Architecture:**
```
POST /api/chat/prompt → EventStore.append("prompt.admitted")
                     → Coordinator.run(session_id)
                     → Processor (LLM) emits events
                     → Projector updates messages table
                     → SSE /api/events pushes to frontend
```

**Tech Stack:** Python 3.11+ / asyncio / aiosqlite / FastAPI / SSE / TypeScript + React

---

## Phase 1 — EventStore + Coordinator (基础架构)

### Task 1: Event data model + EventStore

**Files:**
- Create: `src/cscode/storage/event_store.py`
- Test: `tests/test_event_store.py`

```python
# src/cscode/storage/event_store.py
from __future__ import annotations
import asyncio, json, time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from cscode.storage.db import Database

@dataclass
class Event:
    aggregate_id: str
    seq: int
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0

class EventStore:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._listeners: dict[str, list[asyncio.Event]] = {}
        self._listener_lock = asyncio.Lock()

    async def append(self, aggregate_id: str, events: list[dict[str, Any]]) -> list[Event]:
        now = time.time()
        # Atomically advance sequence
        async with self._db.conn.execute(
            "UPDATE event_sequences SET seq = seq + ? WHERE aggregate_id = ?",
            (len(events), aggregate_id),
        ):
            pass
        if self._db.conn.total_changes == 0:
            await self._db.conn.execute(
                "INSERT INTO event_sequences (aggregate_id, seq) VALUES (?, ?)",
                (aggregate_id, len(events)),
            )
        cursor = await self._db.conn.execute(
            "SELECT seq FROM event_sequences WHERE aggregate_id = ?", (aggregate_id,)
        )
        row = await cursor.fetchone()
        base_seq = int(row[0]) - len(events)

        result = []
        for i, evt in enumerate(events):
            seq = base_seq + i + 1
            event = Event(aggregate_id=aggregate_id, seq=seq, type=evt["type"],
                          data=evt.get("data", {}), created_at=now)
            await self._db.conn.execute(
                "INSERT INTO events (aggregate_id, seq, type, data, created_at) VALUES (?, ?, ?, ?, ?)",
                (aggregate_id, seq, event.type, json.dumps(event.data), now),
            )
            result.append(event)
        await self._db.conn.commit()
        await self._notify(aggregate_id)
        return result

    async def read(self, aggregate_id: str, after_seq: int = 0, limit: int = 1000) -> list[Event]:
        cursor = await self._db.conn.execute(
            "SELECT * FROM events WHERE aggregate_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
            (aggregate_id, after_seq, limit),
        )
        return [Event(aggregate_id=r["aggregate_id"], seq=r["seq"], type=r["type"],
                      data=json.loads(r["data"]), created_at=r["created_at"]) for r in await cursor.fetchall()]

    async def subscribe(self, aggregate_id: str, after_seq: int = 0) -> AsyncIterator[Event]:
        while True:
            events = await self.read(aggregate_id, after_seq)
            for e in events:
                yield e
                after_seq = e.seq
            if not events:
                evt = asyncio.Event()
                async with self._listener_lock:
                    self._listeners.setdefault(aggregate_id, []).append(evt)
                try:
                    await asyncio.wait_for(evt.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                finally:
                    async with self._listener_lock:
                        if aggregate_id in self._listeners:
                            self._listeners[aggregate_id] = [e for e in self._listeners[aggregate_id] if e is not evt]

    async def _notify(self, aggregate_id: str) -> None:
        async with self._listener_lock:
            for evt in self._listeners.get(aggregate_id, []):
                evt.set()
```

**Test:**
```python
# tests/test_event_store.py
import pytest
from cscode.storage.event_store import EventStore

@pytest.mark.asyncio
async def test_append_and_read(in_memory_db):
    store = EventStore(in_memory_db)
    sid = "s1"
    events = await store.append(sid, [{"type": "a"}, {"type": "b"}])
    assert [e.seq for e in events] == [1, 2]
    read = await store.read(sid)
    assert len(read) == 2
    read_after = await store.read(sid, after_seq=1)
    assert len(read_after) == 1
    assert read_after[0].type == "b"

@pytest.mark.asyncio
async def test_append_twice_continuity(in_memory_db):
    store = EventStore(in_memory_db)
    await store.append("s1", [{"type": "a"}])
    await store.append("s1", [{"type": "b"}, {"type": "c"}])
    events = await store.read("s1")
    assert [e.seq for e in events] == [1, 2, 3]
```

- [ ] Implement EventStore
- [ ] Run `pytest tests/test_event_store.py -v` — PASS
- [ ] Commit

---

### Task 2: DB migration — events tables

**Files:**
- Modify: `src/cscode/storage/db.py`

Add `_migration_003` and include it in the migrations list:

```python
async def _migration_003(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS event_sequences (
            aggregate_id TEXT PRIMARY KEY,
            seq INTEGER NOT NULL DEFAULT 0
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aggregate_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            type TEXT NOT NULL,
            data TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            UNIQUE(aggregate_id, seq)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events(aggregate_id, seq)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)")

# Update: migrations = [_migration_001, _migration_002, _migration_003]
```

- [ ] Add migration + update migrations list
- [ ] Run all tests to verify no regression
- [ ] Commit

---

### Task 3: SessionCoordinator — per-session concurrency

**Files:**
- Create: `src/cscode/server/coordinator.py`
- Test: `tests/test_coordinator.py`

```python
# src/cscode/server/coordinator.py
from __future__ import annotations
import asyncio
from typing import Any, Callable

Handler = Callable[[], Any]

class _Entry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._pending: Handler | None = None

    @property
    def locked(self) -> bool:
        return self._lock.locked()

class SessionCoordinator:
    """Per-session: 1 active + 1 queued. run() waits, wake() coalesces."""

    _entries: dict[str, _Entry] = {}
    _dict_lock = asyncio.Lock()

    async def _entry(self, sid: str) -> _Entry:
        async with self._dict_lock:
            if sid not in self._entries:
                self._entries[sid] = _Entry()
            return self._entries[sid]

    async def _drain(self, sid: str, entry: _Entry, handler: Handler) -> None:
        await entry._lock.acquire()
        try:
            await handler()
            while entry._pending:
                h = entry._pending
                entry._pending = None
                await h()
        finally:
            entry._lock.release()
            async with self._dict_lock:
                if entry._pending is None and sid in self._entries:
                    del self._entries[sid]

    async def run(self, sid: str, handler: Handler) -> None:
        entry = await self._entry(sid)
        if entry.locked:
            pending_event = asyncio.Event()
            entry._pending = handler
            await pending_event.wait()
        else:
            await self._drain(sid, entry, handler)

    async def wake(self, sid: str, handler: Handler) -> None:
        entry = await self._entry(sid)
        if entry.locked:
            entry._pending = handler
        else:
            await self._drain(sid, entry, handler)
```

**Test:**
```python
@pytest.mark.asyncio
async def test_run_waits_for_previous():
    c = SessionCoordinator()
    order = []
    async def slow():
        order.append("start")
        await asyncio.sleep(0.1)
        order.append("end")
    t1 = asyncio.create_task(c.run("s", slow))
    await asyncio.sleep(0.02)
    t2 = asyncio.create_task(c.run("s", slow))
    await asyncio.gather(t1, t2)
    assert order == ["start", "end", "start", "end"]
```

- [ ] Implement Coordinator
- [ ] Run `pytest tests/test_coordinator.py -v` — PASS
- [ ] Commit

---

## Phase 2 — Projector + Processor 重构

### Task 4: Projector — events → Message context

**Files:**
- Create: `src/cscode/server/projector.py`
- Test: `tests/test_projector.py`

```python
# src/cscode/server/projector.py
from __future__ import annotations
from cscode.core.messages import Message, MessageRole
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore

class Projector:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def build_context(self, session_id: str, event_store: EventStore,
                            system_prompt: str | None = None) -> list[Message]:
        """Rebuild LLM context from events. System prompt prepended."""
        events = await event_store.read(session_id)
        msgs: list[Message] = []
        if system_prompt:
            msgs.append(Message(role=MessageRole.SYSTEM, content=system_prompt))
        tool_results: dict[str, str] = {}
        for evt in events:
            match evt.type:
                case "prompt.admitted":
                    msgs.append(Message(role=MessageRole.USER, content=evt.data.get("content", "")))
                case "text.ended":
                    msgs.append(Message(role=MessageRole.ASSISTANT, content=evt.data.get("content", "")))
                case "tool.called":
                    tool_results[evt.data.get("name", "")] = "..."  # placeholder
                case "tool.success":
                    msgs.append(Message(role=MessageRole.TOOL, content=evt.data.get("result", ""),
                                        name=evt.data.get("name")))
                case "tool.failed":
                    msgs.append(Message(role=MessageRole.TOOL, content=f"Error: {evt.data.get('error', '')}",
                                        name=evt.data.get("name")))
        return msgs
```

- [ ] Implement Projector.build_context
- [ ] Write test verifying event → Message conversion
- [ ] Run tests — PASS
- [ ] Commit

---

### Task 5: Refactor engine.py — emit events instead of modifying messages

**Files:**
- Modify: `src/cscode/core/engine.py`

**Core change:** Add a new method `run_loop_events` that takes an `on_event` callback and emits events instead of directly appending to `messages`. The existing `_run_loop` is kept for backward compat but internally calls the event version.

```python
# In Agent class, add:
async def run_loop_events(
    self,
    messages: list[Message],
    on_event: collections.abc.Callable[[dict[str, Any]], collections.abc.Awaitable[None]],
    attached_filenames: list[str] | None = None,
    timeout: float | None = None,
) -> str:
    """Like _run_loop but emits granular events instead of tool:start/complete."""
    # ... same logic but emit step.started, text.ended, tool.called, tool.success, tool.failed
    # instead of tool:start, tool:complete
```

The key change in the loop:
- Replace `_emit({"type": "tool:start", ...})` with `_emit({"type": "tool.called", ...})`
- Replace `_emit({"type": "tool:complete", ...})` with `_emit({"type": "tool.success", ...})` / `_emit({"type": "tool.failed", ...})`
- Add `_emit({"type": "text.ended", "data": {"content": result.content}})`
- Add `_emit({"type": "step.started", ...})` / `_emit({"type": "step.ended", ...})`
- Remove `thinking` event (opencode doesn't have it — state machine replaces it)

- [ ] Implement `run_loop_events` in engine.py
- [ ] Run existing tests — PASS (backward compat preserved)
- [ ] Commit

---

### Task 6: Refactor app.py chat_stream — EventStore pipeline

**Files:**
- Modify: `src/cscode/server/app.py`

**New flow in `chat_stream`:**

```python
# Instead of calling _agent._run_loop directly:

# 1. Append prompt event
events = await event_store.append(session_id, [
    {"type": "prompt.admitted", "data": {"content": message, "files": attached_filenames}}
])

# 2. Process through coordinator
async def process():
    # Build context from events
    messages = await projector.build_context(session_id, event_store, _agent.options.system_prompt)
    # Handle file context
    if file_context:
        messages.append(Message(role=MessageRole.SYSTEM, content=file_context))

    async def on_event(evt: dict):
        await queue.put(evt)  # for SSE streaming
        # Also persist relevant events
        persist_events = []
        if evt["type"] in ("text.ended", "tool.called", "tool.success", "tool.failed"):
            persist_events.append({"type": evt["type"], "data": evt.get("data", evt)})
        if persist_events:
            await event_store.append(session_id, persist_events)

    response = await _agent.run_loop_events(messages, on_event=on_event, ...)

await coordinator.run(session_id, process)
```

The SSE stream now reads from BOTH the live queue AND historical events:
1. Send events from the live queue as they arrive
2. On disconnect/reconnect, client can read from `event_store.read(session_id, after_seq=N)`

- [ ] Refactor chat_stream to use EventStore + Coordinator + Projector + run_loop_events
- [ ] Refactor non-streaming chat endpoint similarly
- [ ] Manually test: send message, verify SSE output
- [ ] Commit

---

## Phase 3 — SSE 独立订阅 + 前端适配

### Task 7: Independent SSE subscription endpoint

**Files:**
- Modify: `src/cscode/server/app.py`

Add new endpoint:

```python
@api_router.get("/events")
async def event_stream(session_id: str, after_seq: int = 0) -> StreamingResponse:
    async def stream():
        async for event in event_store.subscribe(session_id, after_seq):
            yield f"event: {event.type}\ndata: {json.dumps(event.data)}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream")
```

Also keep the existing `/api/chat/stream` working for backward compat but have it internally use the event pipeline.

- [ ] Add `/api/events` SSE endpoint
- [ ] Test with curl: verify events stream after POST
- [ ] Commit

---

### Task 8: Frontend — split submit + subscribe

**Files:**
- Modify: `src/cscode/web/src/hooks/useChat.ts`
- Modify: `src/cscode/web/src/stores/useSessionStore.ts`

**useChat.ts changes:**
```typescript
const sendMessage = async (message: string, sessionId?: string, files?: File[]) => {
    // 1. Submit prompt (non-streaming)
    const admitted = await fetch('/api/chat/prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId, files }),
    }).then(r => r.json());

    // 2. Subscribe to events (SSE, auto-reconnect)
    subscribeToEvents(admitted.session_id, admitted.admitted_seq);
};

const subscribeToEvents = (sessionId: string, afterSeq: number) => {
    const es = new EventSource(`/api/events?session_id=${sessionId}&after_seq=${afterSeq}`);
    es.addEventListener('text.ended', (e) => {
        const data = JSON.parse(e.data);
        appendMessage({ role: 'assistant', content: data.content }, sessionId);
    });
    es.addEventListener('tool.called', (e) => {
        const data = JSON.parse(e.data);
        addToolCall(sessionId, { name: data.name, args: data.args, status: 'running' });
    });
    es.addEventListener('tool.success', (e) => {
        const data = JSON.parse(e.data);
        updateToolCall(sessionId, data.name, { status: 'success', output: data.result });
    });
    es.onerror = () => {
        es.close();
        // Reconnect with last known seq
        setTimeout(() => subscribeToEvents(sessionId, lastSeq), 1000);
    };
};
```

**useSessionStore.ts additions — event reducer pattern:**
```typescript
// Add reducer-like methods
const applyEvent = (sessionId: string, event: { type: string; data: any }) => {
    switch (event.type) {
        case 'text.ended':
            // Append assistant message or update current
            break;
        case 'tool.called':
            // Add tool call
            break;
        case 'tool.success':
        case 'tool.failed':
            // Update tool call status
            break;
    }
};
```

- [ ] Refactor useChat.ts: POST submit + EventSource subscribe
- [ ] Add event reducer to useSessionStore.ts
- [ ] Test manually: send message, verify streaming works with new flow
- [ ] Test disconnect/reconnect
- [ ] Commit

---

## Phase 4 — Compaction + 后续

### Task 9: Context epoch + compaction (future)

When context gets large, processor emits `compaction` event and creates an epoch:

```python
async def compact_context(session_id: str, event_store: EventStore, db: Database) -> None:
    events = await event_store.read(session_id)
    # Build snapshot of system + recent messages
    snapshot = compress_messages(events[-50:])  # keep last 50
    latest_seq = events[-1].seq
    await db.conn.execute(
        "INSERT INTO context_epochs (session_id, epoch, baseline_seq, snapshot, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, next_epoch, latest_seq, snapshot, time.time()),
    )
    await db.conn.commit()
```

- [ ] Implement compaction logic (can be deferred)
- [ ] Update Projector.build_context to filter by baseline_seq

---

## Key Risks

| Risk | Mitigation |
|------|-----------|
| Event seq collision under high concurrency | SQLite UNIQUE constraint + retry on IntegrityError |
| SSE connection leak | Client disconnect detection in subscribe loop |
| Old `/api/chat/stream` client breakage | Keep backward compat wrapper using EventStore internally |
| Frontend EventSource reconnection storm | Exponential backoff (100ms, 200ms, 400ms, ... 5s max) |

## Test Strategy

- Unit tests for EventStore (append/read/seq continuity)
- Unit tests for Coordinator (run/wake/queue)
- Integration test: POST prompt → EventStore contains events → SSE delivers them
- Frontend: manual testing with browser DevTools

## Rollback Plan

Revert last 2 commits:

```bash
git revert HEAD~2..HEAD
git commit -m "revert: back to direct message persistence"
```

The old `/api/chat/stream` endpoint is preserved as a backward-compat wrapper.
