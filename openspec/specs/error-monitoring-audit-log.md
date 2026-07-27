# Error Monitoring + Audit Log

## Objective
Add enterprise monitoring for internal deployment: frontend error capture + backend audit logging for key operations.

## 后端（Python/FastAPI）

### A. `audit_logs` 表（Migration 011）
```sql
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    action_type TEXT NOT NULL,       -- e.g. session.create, session.delete, config.update, tool.execute
    resource_type TEXT NOT NULL,     -- e.g. session, config, tool
    resource_id TEXT,                -- session_id / tool name / etc.
    detail TEXT DEFAULT '{}',        -- JSON blob with extra context
    ip_address TEXT DEFAULT '',
    user_agent TEXT DEFAULT ''
);
```

### B. `AuditLogStore` 类 (`src/cscode/server/audit_log.py`)
- `record(action_type, resource_type, resource_id=None, detail=None, request=None)` — 记录操作
- `list(limit=50, offset=0)` — 分页查询
- 接收可选的 `Request` 对象自动提取 IP + User-Agent

### C. 关键操作埋点
在现有 route handler 中插入 `audit_log.record()` 调用：
- `POST /sessions` → `session.create`
- `DELETE /sessions/{id}` → `session.delete`
- `POST /config` / `PUT /config` → `config.update`
- `POST /chat` / `POST /chat/stream` → `chat.send`（粗略记录）

### D. `error_logs` 表（Migration 012）
```sql
CREATE TABLE error_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    message TEXT NOT NULL,
    stack TEXT DEFAULT '',
    url TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    detail TEXT DEFAULT '{}'
);
```

### E. `POST /api/logs/error` endpoint
- 前端上报错误到此端点
- 存入 `error_logs` 表
- 返回 `{"status": "ok"}`

### F. `GET /api/audit-logs` endpoint
- 返回分页的审计日志
- 参数：`limit` (default 50), `offset` (default 0)
- 按 created_at DESC 排序

## 前端（TypeScript/React）

### G. `src/lib/errorMonitor.ts`
- `initErrorMonitor()` — 注册 `window.onerror` + `window.onunhandledrejection`
- 捕获后 POST 到 `/api/logs/error`
- 防抖：同一条错误 30s 内不上报两次
- 在 `App.tsx` 的 useEffect 中初始化

## Acceptance Criteria
1. `pytest tests/` — 全部通过，新增测试覆盖 audit_log store 和 error endpoint
2. `npm test` — 全部通过，新增测试覆盖 errorMonitor
3. `npx tsc --noEmit` — 无类型错误
4. `ruff check src/` — 无 lint 错误
5. 手动验证：curl POST /api/logs/error 返回 200，日志入库
