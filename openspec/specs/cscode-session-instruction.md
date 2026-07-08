# P2-6: Session Instruction — 会话级自定义指令

## 问题

当前 CScode 支持全局 system_prompt（通过配置），但缺少**按会话**设置自定义指令的能力。
OpenCode 有 `core/session/instruction.ts`，支持 per-session instruction 的事件溯源存储和自动注入。

## 需求

1. 用户可以为每个会话设置自定义指令（instruction）
2. 指令通过事件溯源持久化（`instruction.set` / `instruction.deleted` 事件）
3. 指令自动注入到 LLM context 的 system message 中
4. 支持 API 端点: GET/PUT/DELETE /api/sessions/{id}/instruction

## 数据模型

### Event Types
- `instruction.set` — 设置/更新指令
  - data: `{ "instruction": "string" }`
- `instruction.deleted` — 删除指令
  - data: `{}`

### SessionState 扩展
- `instruction: str = ""` — 当前会话的指令文本

### projector 处理
- `instruction.set` → 更新 `state.instruction`
- `instruction.deleted` → 清空 `state.instruction`
- `build_context()` → 如果有 instruction，作为第一个 system message 注入

## API 端点

```
GET    /api/sessions/{session_id}/instruction
  → 200 { "instruction": "..." } | 404

PUT    /api/sessions/{session_id}/instruction
  Body: { "instruction": "string" }
  → 200 { "instruction": "..." }

DELETE /api/sessions/{session_id}/instruction
  → 200 { "deleted": true }
```

## 验收标准

1. SessionV2.set_instruction(text) 追加 instruction.set 事件并更新 state
2. SessionV2.delete_instruction() 追加 instruction.deleted 事件并清空 state
3. SessionProjector 正确处理 instruction.set / instruction.deleted
4. build_context() 在有 instruction 时注入 system message
5. API 端点可以 GET/PUT/DELETE instruction
6. Instruction 跨 session load 持久化
7. 无回归: pytest 全量 + ruff + mypy
