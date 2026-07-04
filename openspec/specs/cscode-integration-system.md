# P2-2: Integration 系统 — WebSocket 实时双向通信

## 1. 问题

当前 CScode 仅通过 SSE（单向）流式传输 LLM 事件到前端。外部 IDE（VS Code、JetBrains）和自定义客户端无法：
- 通过 WebSocket 双向实时通信
- 接收推送事件（会话更新、工具结果、错误）
- 发送命令（创建会话、发送消息）而不通过 HTTP REST

## 2. 目标

提供一个 WebSocket 集成层，支持：
1. WebSocket 端点用于双向实时通信
2. 连接管理（认证、心跳、断线重连）
3. 事件桥接 — 将 EventStore 事件推送到 WebSocket 客户端
4. 基于 JSON 的协议 — 客户端通过消息发送命令

## 3. 接口定义

### 3.1 数据模型

```python
@dataclass
class WSClient:
    """A connected WebSocket client."""
    client_id: str
    websocket: WebSocket
    session_ids: set[str]     # 订阅的 session
    authenticated: bool
    connected_at: float
    last_activity: float

class WSMessage(BaseModel):
    """Client → Server message."""
    type: str                  # "chat", "subscribe", "unsubscribe", "ping"
    session_id: str | None = None
    message: str | None = None
    payload: dict[str, object] | None = None

class WSEvent(BaseModel):
    """Server → Client event."""
    type: str                  # "event", "error", "pong"
    event_type: str | None = None
    data: dict[str, object] = {}
    session_id: str | None = None
```

### 3.2 文件结构

```
src/cscode/server/
  integration.py   ← WebSocketManager + WSClient (新文件)
  app.py           ← WebSocket endpoint (修改)
tests/
  test_integration.py  ← WebSocket 测试 (新文件)
```

### 3.3 WebSocketManager

```python
class WebSocketManager:
    """Manages all connected WebSocket clients."""
    
    def __init__(self, event_store: EventStore | None = None):
        self._clients: dict[str, WSClient] = {}
        self._event_store = event_store
        self._event_task: asyncio.Task | None = None
    
    async def connect(self, websocket: WebSocket) -> WSClient: ...
    async def disconnect(self, client_id: str) -> None: ...
    async def send_to_client(self, client_id: str, event: dict) -> bool: ...
    async def broadcast(self, event: dict, session_id: str | None = None) -> int: ...
    async def subscribe(self, client_id: str, session_id: str) -> None: ...
    async def unsubscribe(self, client_id: str, session_id: str) -> None: ...
    async def _event_bridge(self): ...  # subscribe to EventStore and forward
    async def cleanup_stale(self): ...  # remove disconnected clients
    def get_stats(self) -> dict: ...
```

### 3.4 WebSocket 协议

**Client → Server:**
```json
{"type": "chat",      "session_id": "abc", "message": "Hello"}
{"type": "subscribe", "session_id": "abc"}
{"type": "unsubscribe", "session_id": "abc"}
{"type": "ping"}
```

**Server → Client:**
```json
{"type": "event", "event_type": "text.delta", "session_id": "abc", "data": {"content": "Hello"}}
{"type": "pong"}
{"type": "error", "data": {"message": "..."}}
```

### 3.5 API 端点

```
WS /api/ws              → WebSocket 连接入口
```

## 4. 验收标准

1. [ ] WebSocket 客户端可以连接 `/api/ws`
2. [ ] 客户端发送 `ping`，收到 `pong`
3. [ ] 客户端发送 `subscribe` 到 session，开始接收该 session 的事件
4. [ ] 客户端发送 `unsubscribe`，停止接收事件
5. [ ] 客户端发送 `chat` 消息，触发 LLM 响应（桥接到现有 SSE 流程）
6. [ ] 多个客户端连接互不干扰
7. [ ] 客户端断线后，连接管理清理资源
8. [ ] 认证 token 可选（如果配置了 auth）
9. [ ] 与现有 SSE 端点共存不冲突

## 5. 依赖

- FastAPI 内置 `WebSocket` — 无需额外依赖
- Python 标准库: `asyncio`, `json`, `time`, `uuid`

## 6. 不做的

- 不实现 VS Code 扩展/插件（由外部项目实现）
- 不实现完整的 IDE 协议（只提供基础 WebSocket 桥）
- 不实现文件同步
- 不实现 RPC 框架
