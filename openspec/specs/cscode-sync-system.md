# P2-5: Sync 系统 — 多实例事件同步

## 问题

CScode 的 EventStore 是本地 SQLite 事件存储。多设备/多实例之间无法共享会话事件变更。

## 目标

建立简单的多实例事件同步机制，使一台设备可以拉取另一台设备的会话事件日志并在本地回放。

## 设计决策

- **Single writer 模型**：每个会话在同一时间只有一个写入者，不需要分布式时钟
- **基于 EventStore 构建**：利用已有的 EventStore（events 表），不做额外存储
- **HTTP 同步**：通过 REST API 拉取/推送事件日志
- **增量同步**：按 seq 拉取增量事件（after_seq）

## 核心组件

### `SyncEngine`
协调事件同步的核心服务。
- `pull(remote_url, after_seq)` → 从远程拉取事件并应用到本地
- `push(remote_url)` → 推送本地新事件到远程
- `get_sync_status()` → 获取同步状态

### API Endpoints
- `GET /api/sync/events?after_seq=N` → 返回本地比 N 新的事件列表
- `POST /api/sync/push` → 接受远程推送的事件列表

### `SyncClient`
可选的 HTTP 客户端封装，用于从命令行/UI 触发同步。

## 数据结构

### SyncEvent
```python
@dataclass
class SyncEvent:
    event_id: str        # 全局唯一事件 ID
    seq: int             # 全局单调递增序列号
    type: str            # 事件类型
    data: dict           # 事件数据
    source: str          # 源实例标识
    created_at: float    # 创建时间
```

### SyncState
```python
@dataclass
class SyncState:
    remote_url: str
    last_seq: int        # 最后同步的全局 seq
    last_sync_at: float
```

## 实现策略

1. 扩展 EventStore，增加按全局 seq 扫描事件的方法
2. 新增 `core/sync.py` — SyncEngine
3. 新增 API endpoints
4. 新增 `tests/test_sync.py`

## 验收标准

- [ ] SyncEngine.pull() 能从远程拉取事件并应用到本地 EventStore
- [ ] SyncEngine.push() 能推送本地新事件到远程
- [ ] API 端点正确返回增量事件
- [ ] 重复事件幂等处理（seq 去重）
- [ ] pytest 通过
- [ ] ruff / mypy 清洁
