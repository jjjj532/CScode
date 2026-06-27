# Phase 2: Core 层实现计划

## 目标

基于 Event Sourcing 架构重构 Core 层，实现：
1. **SessionV2** — Event Sourcing 驱动的 Session
2. **Projector** — 事件 → 投影表
3. **SessionRunner** — 从 engine.py 提取标准化 Agent Loop
4. **SessionCoordinator** — 状态机（run/wake/interrupt）
5. 全部附带契约测试

## 依赖

- ✅ Phase 0 (Schema 层) — 完毕
- ✅ Phase 1 (LLM 层) — 完毕
- ✅ EventStore (storage/event_store.py) — 已存在
- ✅ DB 迁移 (events/event_sequences/context_epochs) — 已存在

## 实现顺序

### Step 1: 核心类型定义
- `core/session.py` — SessionV2 + SessionState + SessionProjector
- 无数据库依赖，纯事件重放

### Step 2: Projector
- `core/projector.py` — 监听事件 → 更新 messages/epochs 投影表
- 从 EventStore 读取事件流，构建 LLM 上下文消息

### Step 3: SessionCoordinator
- `core/coordinator.py` — Per-session 状态机
- 状态: idle → draining → queued → idle

### Step 4: SessionRunner
- `core/runner.py` — 标准化 Agent Loop
- 使用 LLM 层的 LLMClient + ToolRuntime
- 从 engine.py _run_loop 提取核心循环

### Step 5: 契约测试
- `tests/test_core_session.py` — SessionV2 + Projector
- `tests/test_core_coordinator.py` — Coordinator 状态机
- `tests/test_core_runner.py` — SessionRunner

## 验收标准

1. 从事件可完整重建 Session 状态
2. Projector 从事件生成 Message[] → LLM 上下文
3. Coordinator 正确管理 idle/draining/queued 状态
4. SessionRunner 能用 LLM 层 produce/stream 响应
5. ruff check + mypy + pytest 全部通过
