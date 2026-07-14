# CScode 全面测试报告

> 测试日期: 2026-07-09  
> 后端版本: 0.3.4  
> 数据库: SQLite (2.1MB data + 4.0MB WAL)  
> 测试方法: API 级全面功能测试 + 前端源码审查 + OpenCode 架构对比

---

## 目录

1. [测试概览](#1-测试概览)
2. [已测端点清单](#2-已测端点清单)
3. [发现的问题](#3-发现的问题)
4. [OpenCode 架构差距对照](#4-opencode-架构差距对照)
5. [前端 UI 审查结果](#5-前端-ui-审查结果)
6. [修复建议优先级](#6-修复建议优先级)

---

## 1. 测试概览

### 测试环境
- Server: `http://localhost:8000` (Python 3.14, FastAPI)
- DB: `/Users/mac/.config/cscode/cscode.db` (2.1MB, 12 tables)
- 50 个 session，6303 条 events，110 条 messages
- LLM Provider: `MiniMax-M2.5` via `https://api.scnet.cn/api/llm/v1`

### 测试结果速览

| 类别 | 通过 | 失败 | 异常 |
|------|------|------|------|
| Session CRUD | 10/10 | 0 | 0 |
| Chat 端点 | 3/4 | 0 | 1 |
| 流式 Chat | 4/4 | 0 | 0 |
| 配置管理 | 3/3 | 0 | 1 |
| 权限规则 | 3/3 | 0 | 0 |
| 凭证管理 | 2/2 | 0 | 0 |
| 并发 Session | 3/3 | 0 | 0 |
| 边缘情况 | 2/4 | 0 | 2 |
| **总计** | **30/33** | **0** | **4** |

---

## 2. 已测端点清单

### Session 管理

| # | 端点 | 方法 | 结果 | 备注 |
|---|------|------|------|------|
| 1 | `/api/sessions` | GET | ✅ | 正确返回 50 个 session |
| 2 | `/api/sessions` | POST | ✅ | 创建成功，返回 ID+title |
| 3 | `/api/sessions/:id` | PATCH | ✅ | 更新 title 成功 |
| 4 | `/api/sessions/:id` | DELETE | ✅ | 软删除（status 改为 deleted） |
| 5 | `/api/sessions/:id/messages` | GET | ✅ | 从 EventStore 重建消息 |
| 6 | `/api/sessions/:id/export` | POST | ✅ | 导出含 session metadata + messages |
| 7 | `/api/sessions/import` | POST | ✅ | 导入创建新 session |
| 8 | `/api/sessions/:id/context` | GET | ✅ | 返回 LLM context messages |
| 9 | `/api/sessions/:id/summary` | GET | ✅ | 返回完整统计信息 |
| 10 | `/api/session` (singular alias) | GET | ✅ | 功能等价于 plural |

### Chat 端点

| # | 端点 | 方法 | 结果 | 备注 |
|---|------|------|------|------|
| 11 | `/api/chat` | POST | ✅ | 非流式响应，但 `#1` |
| 12 | `/api/chat/stream` | POST | ✅ | SSE 流式正常，事件链完整 |
| 13 | `/api/chat/stream` (新 session) | POST | ✅ | 自动创建 session |
| 14 | `/api/chat` (无 session_id) | POST | ✅ | 自动创建 UUID session |

### 配置管理

| # | 端点 | 方法 | 结果 | 备注 |
|---|------|------|------|------|
| 15 | `/api/config` | GET | ✅ | 但 `#2` API key 明文暴露 |
| 16 | `/api/config` | POST | ✅ | 保存成功，实时生效 |
| 17 | `/api/config/reference` | GET | ✅ | 16 个配置键描述 |

### 权限 & 凭证

| # | 端点 | 方法 | 结果 | 备注 |
|---|------|------|------|------|
| 18 | `/api/permission-rules` | GET | ✅ | 正确列出所有规则 |
| 19 | `/api/permission-rules` | POST | ✅ | 创建成功 |
| 20 | `/api/credentials` | GET | ✅ | 列表显示已 mask 的值 |
| 21 | `/api/credentials` | POST | ✅ | 创建成功 |

### 辅助端点

| # | 端点 | 方法 | 结果 | 备注 |
|---|------|------|------|------|
| 22 | `/api/health` | GET | ✅ | 返回 status + version |
| 23 | `/api/tools/application` | GET | ✅ | 12 个 application tools |
| 24 | `/api/sessions/:id/events` | GET | ✅ | SSE event replay |
| 25 | `/api/workspaces` | GET | ✅ | 空列表 |

### 流式事件链验证

```
session.created → prompt.admitted → step.started →
text.delta → text.ended → complete → step.ended
```

✔ 事件类型完整，session_id 正确  
✔ `PERSIST_EVENT_TYPES` 正确过滤（排除 `text.delta`）  
✔ `complete` 事件携带完整响应内容

### 并发 Session 隔离

| 测试 | 结果 |
|------|------|
| 两个会话同时流式 | ✅ A 返回 "Session-A-Response"，B 返回 "Session-B-Response" |
| session_id 无污染 | ✅ 各事件携带正确的 session_id |
| SSE 前端过滤 | ✅ 前端 `useChat.ts` 按 session_id 过滤事件 |

---

## 3. 发现的问题

### #1 [CRITICAL] 非流式 Chat 未持久化 Assistant 回复

**路径**: `src/cscode/server/app.py` → `_handle_chat()`  
**行**: 1157  
**代码**:
```python
response = await agent.run_with_messages(messages, on_event=None)
```
**根因**: `on_event=None` 不触发任何事件回调，assistant 响应没有被写入 EventStore。  
仅 `prompt.admitted` 在行 1136 手动写入。  
**影响**: GET messages/export/context 无法获取非流式 chat 的 assistant 回复。  
**验证**: 事件表仅包含:
```sql
1|session.created
2|prompt.admitted
3|prompt.admitted  ← 后续消息也只存了 prompt.admitted
```
**修复方向**: 将 `on_event=None` 改为传入回调函数，将 LLM event 写入 EventStore。

### #2 [HIGH] GET /api/config 返回明文 API Key

**路径**: `src/cscode/server/app.py`  
**影响**: 任意能访问 `/api/config` 的人可读取全部配置，包括 `api_key`。  
**证据**:
```json
{
    "api_key": "sk-sp-Mzg1LTExNjk5ODA1Mjg4LTE3NzYyMTUxNTU1MTA=",
    ...
}
```
**修复方向**: GET 响应中移除 `api_key` 字段，或返回 mask 后的值（如凭证端点做的 `sk-t****23`）。

### #3 [HIGH] Projector 未接入事件管道

**路径**: `src/cscode/server/projector.py`  
**问题**: `Projector.on_event()` 仅在 `BatchProjector.rebuild()` 中被调用，  
从未在正常的流式/非流式事件写入路径中被触发。  
**影响**: SQLite `messages` 表在生产运行中永远为空。  
所有消息读取依赖 `SessionProjector.build_context()` 从 EventStore 重建。  
这是一个正确性没问题但性能有隐患的问题。  
**修复方向**: 在 app.py 的事件持久化回调中同步调用 `_projector.on_event()`。

### #4 [MEDIUM] Deleted Sessions 仍在列表中

**问题**: 50 个 session 中 48 个 status="deleted" 仍出现在 `/api/sessions` 列表。  
**证据**:
```
Total: 50
  status=active: 2
  status=deleted: 48
```
**修复方向**: GET /api/sessions 过滤 `status != 'deleted'` 或增加查询参数。

### #5 [MEDIUM] Malformed JSON 返回 200 而非 400

**证据**:
```bash
curl -s "http://localhost:8000/api/chat" -d "not json"
# HTTP 200, 返回包含错误信息的 JSON
```
**修复方向**: 在 JSON parse 失败时返回 400 Bad Request。

### #6 [MEDIUM] 非法 session_id 返回空数组而非 404

**证据**:
```bash
curl -s "http://localhost:8000/api/sessions/nonexistent/messages"
# 返回 [] (HTTP 200) 而非 404
```
**修复方向**: 检查 session 是否存在，不存在则返回 404。

### #7 [LOW] WebSocket / API 端点 404

| 端点 | 结果 |
|------|------|
| `/api/ws` | 404 |
| `/api/pty` | 404 |
| `/api/sessions/:id/stop` | 需验证 |
| `/api/tokens/usage` | 404 |
| `/api/shares` | 405 |

这些端点可能尚未实现，属于文档/路线图问题。

### #8 [LOW] 数据库 WAL 文件过大

**DB**: `cscode.db` = 2.1MB 但 `cscode.db-wal` = 4.0MB  
WAL 文件是 data 文件的约 2 倍，说明 checkpoint 不及时。  
**建议**: 增加定期 WAL checkpoint。

---

## 4. OpenCode 架构差距对照

基于 `docs/opencode-analysis/source-analysis.md` 和 `docs/technical-specification.md`：

### 已实现（差异≈0）

| 组件 | CScode | OpenCode | 差距 |
|------|--------|----------|------|
| HTTP Server | FastAPI | FastAPI | 0 |
| File tools | 齐全 | 齐全 | 0 |
| Browser tool | Playwright | Playwright | 0 |
| Web fetch/search | 齐备 | 齐备 | 0 |
| SSE Streaming | 事件链完整 | 事件链完整 | 0 |
| MCP Server | 实现 | 实现 | 0 |
| Plugin system | SDK 完整 | SDK 完整 | 0 |
| Theme system | 多主题 | 多主题 | 0 |
| Multi-provider | 7个provider | 多provider | 0 |

### 部分实现（有基础但功能不全）

| 组件 | CScode | OpenCode | 差距 |
|------|--------|----------|------|
| Session V2 | 基本完整 | 完整 | Event projection 接入 |
| Coordinator | 实现 | 完整 | 无速率限制/优先级 |
| Compactor | 实现 | 完整 | 未验证大 session 效果 |
| Event Sourcing | 基础实现 | 完整 | 无 snapshot 版本管理 |
| Permission system | 简单规则 | 完整 | 无通配符匹配优化 |
| Config system | 基础 | 完整 | 无分层 merge |
| Workspace | 基础 CRUD | 完整 | 无 session 关联 |

### 未实现（完全缺失）

| 组件 | CScode | OpenCode | 重要性 |
|------|--------|----------|--------|
| Session Route 系统 | ❌ | 有 | High |
| SessionRunner 架构 | ❌ | 有 | High |
| 自定义 Skill 系统 | ❌ | 有 | High |
| Agent 超时/重试 | ❌ | 有 | Medium |
| Rate Limiting | ❌ | 有 | Medium |
| WebSocket 事件桥 | ❌ | 有 | Medium |
| PTY Terminal | 骨架 | 完整 | Low |

---

## 5. 前端 UI 审查结果

### 架构

| 方面 | 评价 |
|------|------|
| State管理 | ✅ Zustand，清晰分离 4 个 store |
| API 封装 | ✅ `lib/api.ts` 统一 request 函数，类型安全 |
| SSE 处理 | ✅ `useChat.ts` 完全实现流式解析 + session_id 过滤 |
| 组件结构 | ✅ 分层清晰（layout/chat/ui/sidebar） |
| 错误处理 | ✅ ErrorBoundary 全局兜底 |
| 主题系统 | ✅ 支持主题切换，`opencode-dark` 为默认 |

### 关键代码质量

- `useChat.ts` (256行): 流式聊天实现完整，包含 AbortController、session_id 隔离、断线恢复
- `MessageList.tsx` (66行): 消息列表 scroll 到最新、过滤空 assistant 消息
- `Composer.tsx` (237行): 输入框含 @mention、文件附件、自动创建 session
- `SettingsPanel.tsx` (538行): MCP 服务器配置、插件开关、键绑定、权限规则

### 发现的前端问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| `MessageList.tsx:57` key=`Math.random()` | Low | 随机 key 导致不必要的重新渲染 |
| `Composer.tsx:227` hardcoded model label | Low | config?.model 回退显示"gpt-4o" |
| `SettingsPanel.tsx:67` JSON.stringify 比较 | Low | 性能优化点 |
| `Message.tsx` 未审查 | Info | 需要确认 markdown 渲染正确性 |

---

## 6. 修复建议优先级

### P0 - 立即修复

| # | 问题 | 预计工作量 | 影响面 |
|---|------|------------|--------|
| #1 | `_handle_chat` 未持久化 assistant 回复 | 1-2h | 非流式 chat 消息丢失 |
| #2 | API key 明文暴露 | 0.5h | 安全风险 |
| #3 | Projector 接入事件管道 | 1h | messages 表为空 |

### P1 - 本周修复

| # | 问题 | 预计工作量 | 影响面 |
|---|------|------------|--------|
| #4 | Deleted sessions 过滤 | 0.5h | UI 体验 |
| #5 | Malformed JSON 返回 400 | 0.5h | API 健壮性 |
| #6 | 非法 session_id 404 | 0.5h | API 规范 |

### P2 - 下个迭代

| # | 问题 | 预计工作量 | 影响面 |
|---|------|------------|--------|
| #7 | 缺失端点的路线图 | 0.5h | 文档 |
| #8 | WAL checkpoint 策略 | 0.5h | 存储 |
| - | OpenCode 架构差距填补 | 多迭代 | 长期演进 |

---

## 附录: 关键测试命令

```bash
# 健康检查
curl -s http://localhost:8000/api/health

# 创建 session + 发送 chat
SID=$(curl -s -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" -d '{}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
curl -s --max-time 30 -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"hello\",\"session_id\":\"$SID\"}"

# 流式 chat
curl -s --max-time 20 -X POST "http://localhost:8000/api/chat/stream" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Count to 3\"}"

# 检查事件持久化
sqlite3 ~/.config/cscode/cscode.db "SELECT seq, type FROM events WHERE aggregate_id='$SID' ORDER BY seq;"

# Session 列表统计
curl -s http://localhost:8000/api/sessions | python3 -c "
import sys,json
sessions=json.load(sys.stdin)
statuses={}
for s in sessions: st=s.get('status','?');statuses[st]=statuses.get(st,0)+1
print(statuses)
"
```
