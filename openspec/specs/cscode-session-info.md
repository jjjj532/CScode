# P2-7: Session Info — 会话信息端点

## 问题

当前没有独立端点返回单会话的完整元数据，需要遍历多个 API 获取。

## 需求

`GET /api/sessions/{session_id}/info` 返回：

```json
{
  "session_id": "...",
  "title": "Chat",
  "model": "gpt-4o",
  "provider": "openai",
  "agent": "auto",
  "status": "active",
  "workspace_id": "",
  "message_count": 4,
  "event_count": 6,
  "tool_rounds": 0,
  "created_at": 1234567890.0,
  "updated_at": 1234567890.0,
  "seq": 6
}
```

## 验收标准

1. 返回完整会话元数据
2. message_count 等于 state.messages 长度
3. 404 不存在的 session_id
4. pytest + ruff + mypy 无回归
