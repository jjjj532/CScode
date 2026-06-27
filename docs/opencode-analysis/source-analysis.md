# OpenCode 源码深度分析 — 基于源码阅读的五维分析

> 基于直接阅读 OpenCode 核心包源码 (packages/core, packages/llm, packages/opencode, packages/protocol, packages/function)
> 分析日期: 2026-06-26

---

## 整体架构：三层蛋糕模型

```
┌──────────────────────────────────────────────────────────────────┐
│                    packages/opencode (应用层)                      │
│  Session CRUD | LLM Runtime (AI SDK/Native) | Tool Resolution    │
│  SessionProcessor (LLM Events → Session Events)                   │
├──────────────────────────────────────────────────────────────────┤
│                    packages/core (核心引擎层)                       │
│  Agent V2 | Session V2 (Event Sourcing) | ToolRegistry V2         │
│  SessionRunner (LLM Stream + Tool Loop) | Permission V2          │
│  Event V2 (事件溯源 + 投影) | Config | Location                   │
├──────────────────────────────────────────────────────────────────┤
│                    packages/llm (LLM 抽象层)                       │
│  LLMClient (generate/stream) | Route (Protocol + Endpoint + Auth) │
│  Schema (Message, ToolDefinition, LLMError, LLMEvent)            │
│  ToolRuntime (dispatch) | Protocols (OpenAI/Anthropic/Gemini...)  │
├──────────────────────────────────────────────────────────────────┤
│                    packages/schema (共享 Schema 层)                │
│  Session, Agent, Permission, Event 的 Effect Schema 定义           │
├──────────────────────────────────────────────────────────────────┤
│                    packages/protocol (HTTP API 层)                 │
│  Effect HttpApi 定义 | Middleware (Auth, SchemaError)              │
└──────────────────────────────────────────────────────────────────┘
```

**关键设计原则：core 和 llm 是纯 Effect 层，不依赖任何 UI/CLI 代码。opencode 是应用粘合层。**

---

## 1. 结构分析 (Structure)

### 1.1 包依赖关系 (关键!)

```
@opencode-ai/schema          ← 所有包依赖 (纯 Schema 定义, 无 runtime)
@opencode-ai/llm             ← 依赖 schema + effect
@opencode-ai/core            ← 依赖 schema + llm + effect
@opencode-ai/opencode        ← 依赖 core + llm + schema + effect (应用粘合层)
@opencode-ai/protocol        ← 依赖 schema + effect (独立于 core)
```

**CScode 缺失的架构层：**
- CScode 没有 `schema` 层 — 类型定义散落在各个模块
- CScode 没有纯 Effect 的核心层 — 业务逻辑直接耦合在 CLI/TUI/Server 中
- CScode 没有 `llm` 抽象层 — provider 调用直接嵌入在 session 代码中

### 1.2 Core 包内部模块

```
packages/core/src/
├── agent.ts              # Agent 管理 (注册/选择/默认)
├── config.ts             # 配置加载 (global + .opencode + project 层级合并)
├── config/               # 子配置: agent, compaction, mcp, plugin, provider...
├── location.ts           # Location (工作目录 + project 信息)
├── state.ts              # 通用状态管理 (可重放的 transform 系统)
├── permission.ts         # 权限核心 (ask/assert/reply/evaluate)
├── permission/           # 权限持久化 (saved.sql.ts)
├── event/                # 事件溯源核心 (EventV2)
│   └── sql.ts            # 事件表: event_sequence + event
├── session/              # Session 系统
│   ├── schema.ts         # ID, Info 类型
│   ├── event.ts          # SessionEvent 类型 (35+ 事件)
│   ├── store.ts          # Session 存储接口 (get/context/message)
│   ├── input.ts          # 输入系统 (admit/promote/steer/queue)
│   ├── projector.ts      # 事件投影器 (event → DB 行)
│   ├── runner/           # Session 运行器
│   │   ├── index.ts      # Service 定义
│   │   ├── llm.ts        # 主循环 (LLM stream + tool loop)
│   │   ├── model.ts      # 模型解析
│   │   ├── to-llm-message.ts  # SessionMessage → LLM Message
│   │   └── publish-llm-event.ts  # LLM 事件发布
│   ├── message.ts        # 消息类型
│   ├── history.ts        # 历史加载
│   ├── compaction.ts     # 上下文压缩
│   └── sql.ts            # Session 表定义
├── tool/                 # 工具系统
│   ├── tool.ts           # Tool.make / definition / settle
│   ├── registry.ts       # 注册 + materialize + settle
│   ├── tools.ts          # Tools.Service (注册接口)
│   ├── application-tools.ts  # 应用级工具注册
│   └── bash.ts, read.ts, write.ts, edit.ts, grep.ts, glob.ts...
```

### 1.3 LLM 包内部模块

```
packages/llm/src/
├── llm.ts                # LLM.request / generateObject (便利函数)
├── tool.ts               # tool() 帮助函数 (typed tool 构造)
├── tool-runtime.ts       # ToolRuntime.dispatch (单次调用 dispatcher)
├── schema/               # 核心数据模型
│   ├── ids.ts            # Branded ID: ModelID, ProviderID, ToolCallID...
│   ├── messages.ts       # Message, ToolDefinition, ToolChoice, LLMRequest
│   ├── events.ts         # LLMEvent (16 种类型), Usage, LLMResponse
│   ├── errors.ts         # LLMError (10 种 reason), ToolFailure
│   └── options.ts        # GenerationOptions, ProviderOptions, CachePolicy
├── route/                # Route 系统
│   ├── client.ts         # LLMClient.generate/stream/prepare
│   ├── protocol.ts       # Protocol 定义
│   ├── endpoint.ts       # Endpoint (URL 构造)
│   ├── auth.ts           # Auth (认证)
│   ├── framing.ts        # Framing (SSE 等)
│   └── transport/        # HTTP/WebSocket 传输
├── protocols/            # 具体协议实现
│   ├── openai-chat.ts    # OpenAI Chat 协议
│   ├── openai-responses.ts
│   ├── anthropic-messages.ts
│   ├── gemini.ts
│   ├── bedrock-converse.ts
│   └── ...
└── providers/            # Provider 配置门面
    ├── openai.ts, anthropic.ts, google.ts, azure.ts...
    └── openai-compatible.ts
```

---

## 2. 行为分析 (Behavior)

### 2.1 Agent 生命周期

```typescript
// Agent 注册 (core/src/agent.ts)
State.create<Data, Draft>({
  initial: () => ({ agents: new Map() }),
  draft: (draft) => ({
    list, get, default, update, remove
  })
})

// Agent 选择
AgentV2.select(id?) → Selection(id, info)
// 回退链: configured default → "build" → first non-subagent non-hidden
```

**关键行为：** Agent 可以带 `permissions`、`system` prompt、`steps` (最大步数)。subagent 和 hidden agent 不可选为默认。

### 2.2 Config 加载优先级

```
global (~/.config/opencode/opencode.json)     ← 最低优先级
  └── project 目录向上搜索发现的 config 文件     ← 中间优先级
      └── .opencode/ 目录                      ← 最高优先级
(config 越具体优先级越高)
policy (规则) 应用顺序相反: global 规则 override 项目规则
```

### 2.3 权限评估

```typescript
// 核心函数 (core/src/permission.ts)
evaluate(action, resource, ...rulesets) → Rule { action, resource, effect }

// 效果: "allow" | "deny" | "ask"
// 规则匹配: 通配符匹配 (Wildcard.match), last-match-wins
// 处理流程:
1. 检查 agent 配置的权限规则 → 如果 denied 立即返回 deny
2. 合并 saved rules (用户"总是允许"的记忆规则)
3. 对每个 resource 执行 evaluate
4. 如果任意 resource 被 deny → deny
5. 如果任意 resource 需要 ask → ask
6. 否则 allow

// ask → 发布 Event.Asked → 等待用户回复 Deferred
// assert → 阻塞直到用户回复或规则允许/拒绝
```

**CScode 差距：CScode 没有 wildcard 匹配，没有 ask 用户确认机制，没有 saved rules 记忆。**

### 2.4 Tool 构造和执行

```typescript
// Tool.make (core/src/tool/tool.ts)
Tool.make({
  description: string,
  input: Schema,          // Effect Schema
  output: Schema,         // Effect Schema
  execute: (input, context) => Effect<output, ToolFailure>,
  toModelOutput?: (input) => Content[]  // 自定义模型输出投影
})

// Tool.withPermission(tool, "edit")  // 声明权限

// ToolRegistry.materialize(permissions?) → {
//   definitions: ToolDefinition[],  // 给 LLM 的定义
//   settle: (input) => Effect<Settlement>
// }

// ToolRegistry.settle() → decode input → execute → encode output
// 输出经 ToolOutputStore.bound() 管理 → 大输出写入文件
```

**关键：Tool.make 返回的是 opqaue object (WeakMap 存储 runtime 数据)。Tool.definition(name) 缓存 ToolDefinition。两种注册作用域：application-tools (进程级) 和 registry (Location 级)。**

### 2.5 Session 事件系统

Session 有 35+ 事件类型，通过 EventV2.publish → Event Sourcing (Drizzle SQLite) → Projector (更新物化视图)：

```
SessionEvent:
├── Prompted          # 用户输入 (已提升为执行)
├── PromptAdmitted    # 用户输入 (已接纳等待执行)
├── ContextUpdated    # 上下文更新
├── Synthetic         # 系统合成消息
├── AgentSwitched     # Agent 切换
├── ModelSwitched     # 模型切换
├── Step.Started      # 一步开始
├── Step.Ended        # 一步结束 (含 tokens/cost/snapshot)
├── Step.Failed       # 一步失败
├── Text.Started      # 文本开始
├── Text.Ended        # 文本结束
├── Tool.Called       # 工具调用
├── Tool.Success      # 工具成功
├── Tool.Failed       # 工具失败
├── Tool.Progress     # 工具进度
├── Shell.Started     # Shell 开始
├── Shell.Ended       # Shell 结束
├── Reasoning.Started # 推理开始
├── Reasoning.Ended   # 推理结束
├── Compaction.Ended  # 压缩完成
├── RevertEvent.*     # 回滚事件
└── Moved             # Session 移动
```

---

## 3. 路径分析 (Flow) — 完整请求处理链

### 3.1 V1 路径 (opencode package)

```
用户输入
  → SessionProcessor.create() 创建 assistant message
  → SessionTools.resolve() 解析可用 tools
  → LLM.stream() (AI SDK 或 Native)
    → AI SDK: streamText() → LLMAISDK.toLLMEvents() 标准化
    → Native: LLMClient.stream() 直接输出 LLMEvent
  → Stream tap handleEvent(event)
    → reasoning-start/delta/end → 发布 ReasoningPart
    → text-start/delta/end → 发布 TextPart
    → tool-input-start/delta/end → 创建 ToolPart (pending)
    → tool-call → 更新为 running → 执行 tool
    → tool-result → 更新为 completed + output
    → tool-error → 更新为 error
    → step-start → 快照
    → step-finish → cost/token 计算 + 快照 patch
    → provider-error → 重试/报错
  → 检查 compaction 需要
  → 返回 compact/stop/continue
  → 如果是 continue → 再次循环
```

### 3.2 V2 路径 (core package, 实验性)

```
SessionExecution.resume(sessionID)
  → SessionRunner.run(sessionID, force)
    → 检查 pending inputs (steer/queue)
    → Loop:
      → RunTurn:
        → 获取 session + agent + model
        → 加载 system context (系统上下文 + skill guidance + reference)
        → 加载 session history (toLLMMessages 转换)
        → materialize tools (按权限过滤)
        → 构建 LLM.request(model, system, messages, tools)
        → 检查 compaction 需要
        → llm.stream(request) — 一轮 provider
        → 处理流事件 + 发布 SessionEvent
        → 非 provider-executed tool-call:
          → toolMaterialization.settle()
          → 发布 tool-result
        → 等待所有 tool fibers 完成
        → 发布 Step.Ended
        → 检查是否需要 continuation (更多 tool calls)
      → 检查 steer/queue 输入
```

### 3.3 V1 vs V2 关键区别

| V1 (opencode 包) | V2 (core 包, 实验性) |
|---|---|
| AI SDK 为主 + Native 回退 | 纯 @opencode-ai/llm |
| SessionProcessor 管理事件 | SessionRunner 管理事件 |
| 每个 Session 独立处理 | SessionExecution coordinator |
| Event V1 投影 | Event V2 事件溯源 |
| 同步工具执行 (await) | FiberSet 并发工具执行 |
| 重试策略: SessionRetry.policy | 重试: 待实现 |

---

## 4. 边界分析 (Edge Cases)

### 4.1 LLM 错误分类

```typescript
LLMError = {
  module: string,   // "LLM", "SessionRunner" 等
  method: string,   // "generate", "stream" 等
  reason: LLMErrorReason — 10 种:
    ├── InvalidRequest      — 参数错误, 不可重试
    ├── NoRoute             — 找不到路由, 不可重试
    ├── Authentication      — 认证失败 (missing/invalid/expired), 不可重试
    ├── RateLimit           — 限流, 可重试 (含 retryAfterMs)
    ├── QuotaExceeded       — 配额超限, 不可重试
    ├── ContentPolicy       — 内容策略, 不可重试
    ├── ProviderInternal    — 服务端错误, 可重试
    ├── Transport           — 网络错误, 不可重试
    ├── InvalidProviderOutput — 响应解析失败, 不可重试
    └── UnknownProvider     — 未知 provider, 不可重试
}
```

### 4.2 上下文溢出恢复

```typescript
// SessionRunner (runner/llm.ts)
// 流程:
1. llm.stream(request) 发送请求
2. 如果收到 provider-error 且 isContextOverflowFailure
3. 且还没有任何 assistant 输出
4. 调用 compaction.compactAfterOverflow()
5. 压缩完成后用 runAfterOverflowCompaction() 重试
6. 如果重试仍然溢出 → 致命错误
```

### 4.3 工具执行超时和中断

```typescript
// Session 中断处理
1. SessionExecution.interrupt(sessionID) → 设置中断信号
2. SessionRunner 在 turn 开始前检查中断
3. failInterruptedTools() — 将所有 pending/running tool 标记为 failed
4. FiberSet.clear() — 清理所有工具 fibers
5. publisher.failUnsettledTools() — 通知 LLM
```

### 4.4 重复输入检测

```typescript
// SessionInput (session/input.ts)
// 通过 ID 查重: find(db, id) → 如果存在返回现有
// 事件溯源冲突检测: LifecycleConflict
// 投影冲突: admitted_seq + promoted_seq 唯一约束
```

### 4.5 Doom Loop 检测

```typescript
// SessionProcessor (opencode/src/session/processor.ts)
// 检测: 连续 DOOM_LOOP_THRESHOLD(=3) 次重复 tool call
// 触发: permission.ask({ permission: "doom_loop", ... })
// 询问用户是否允许继续
```

---

# 下篇: CScode 源码现状与差距分析

基于直接阅读 CScode Python 源码后的完整对比。

---

## CScode 当前架构总览

```
src/cscode/
├── core/
│   ├── agent.py            # AgentOrchestrator (plan/build 模式)
│   ├── config.py           # Config dataclass + YAML/ENV 加载
│   ├── engine.py           # Agent 类 (run loop + 工具执行, 474 行大函数)
│   ├── events.py           # EventBus (字符串类型订阅/发布)
│   ├── messages.py         # Message dataclass (4 种 role, 简单字符串)
│   ├── session_manager.py  # Session CRUD (内存 dict)
│   ├── permissions.py      # PermissionService (allow/deny/ask)
│   ├── compression.py      # ContextCompressor (truncate, 简单)
│   ├── errors.py           # 5 个 Exception 子类
│   ├── structured.py       # 手动 JSON Schema 校验
│   ├── sub_agent.py        # @mention 子代理调用
│   └── tracker.py          # 任务跟踪投影
├── providers/
│   ├── base.py             # LLMProvider ABC
│   ├── openai.py, anthropic.py, azure.py, gemini.py, ollama.py, openrouter.py
├── tools/
│   ├── base.py             # BaseTool ABC, ToolRegistry
│   ├── read.py, write.py, edit.py, bash.py, grep.py, glob.py, ...
├── storage/
│   ├── db.py               # aiosqlite Database + migrations
│   ├── session.py          # SessionStore (SQLite CRUD)
│   └── event_store.py      # EventStore (append/read/subscribe)
└── server/
    └── app.py              # FastAPI 服务
```

**现状摘要:** CScode 有骨架但缺少所有关键架构层。EventStore 存在但未被 session 系统使用。Engine 有 474 行的超大函数。Tool 系统用简单 JSON dict 通信。没有依赖注入、没有类型安全的 schema、没有标准化的错误模型。

---

## 逐模块差距对比

### 1. 消息系统 (差距: 严重)

| 维度 | OpenCode | CScode |
|------|----------|--------|
| **消息结构** | `Part[]` 数组: Text, Media, ToolCall, ToolResult, Reasoning | `content: str` 单字符串 |
| **消息角色** | system, user, assistant, tool | system, user, assistant, tool |
| **Content Parts** | SystemPart/TextPart/MediaPart/ToolCallPart/ToolResultPart (多态 union) | 纯字符串 |
| **Tool Calls** | 强类型 ToolCall 对象 | `list[dict[str, Any]]` (纯 JSON) |
| **Schema** | Effect Schema (编译+运行双时验证) | 无 (字符串传递) |
| **Image 支持** | MediaPart (多模态, 任意 mime) | ImageAttachment (专用类) |

**影响:** CScode 的消息格式太简单, 无法支持 OpenCode 的所有功能场景 (推理 content、媒体、多工具结果)。每次都是字符串拼接和 JSON 解析, 容易出错且无法类型检查。

### 2. Session 系统 (差距: 严重)

| 特性 | OpenCode | CScode |
|------|----------|--------|
| **架构** | Event Sourcing (EventV2) → Projector → Store/Runner | 内存 dict CRUD |
| **持久化** | 事件表 append-only + 物化视图投影 | SQLite 直接写 session/messages 表 |
| **事件** | 35+ 类型 SessionEvent | 5 类简单事件 (EventBus) |
| **恢复** | SessionExecution.resume() 完整重建 | 无 |
| **输入** | steer + queue 双模式 + 去重 | 直接 append |
| **Fork** | Session.fork() 克隆到指定消息点 | 无 |
| **快照** | Step.Ended 自动快照 + undo/revert | 无 |
| **Token/Cost** | 精确分层计数 + Decimal 计算 | 可能有(粗略) |
| **Epoch** | ContextEpoch 管理压缩 epoch | context_epochs 表存在但未集成 |

**影响:** CScode 的 session 恢复完全不可靠。EventStore 表存在 (`event_sequences`, `events`) 但 `SessionManager` 根本不使用它。消息保存用 "delete + reinsert" 模式, 并发下数据丢失风险高。

### 3. Agent/Engine 系统 (差距: 严重)

| 特性 | OpenCode | CScode |
|------|----------|--------|
| **Agent 管理** | State.create 可重放, 回退选择链 | 硬编码 plan/build 两个模式 |
| **Engine 结构** | SessionRunner (编排) → LLMClient (执行) → ToolRegistry (工具) | 474 行 Agent._run_loop() 内联所有逻辑 |
| **循环控制** | while needsContinuation + 输入队列双循环 | 单 while True 循环 |
| **错误处理** | 结构化 LLMError + ToolFailure + retry 策略 | try/except Exception (catch-all) |
| **超时** | 每步可配超时, 自动 retry | asyncio.wait_for 全局超时 |
| **File Guard** | PermissionV2.evaluate() 统一规则 | 内联字符串匹配 (search_tools/keywords) |
| **并发工具执行** | FiberSet 并发执行 | 顺序 await 逐个执行 |
| **权限集成** | ToolRegistry 自动材料化时过滤 | PermissionService.check 在循环内调用 |
| **中间步骤** | Step.Started/Ended + Text.Started/Ended + Reasoning | "step.started"/"step.ended" 等事件 |

**影响:** `engine.py` 的 `_run_loop()` 和 `run_loop_events()` 有大量重复代码, 职责不清晰 (文件守卫、格式化、权限检查、工具执行、事件发布都在同一函数)。`run` 和 `run_with_permissions` 基本重复。

### 4. 工具系统 (差距: 中等)

| 特性 | OpenCode | CScode |
|------|----------|--------|
| **Tool 定义** | Tool.make({input Schema, output Schema, execute, toModelOutput}) | BaseTool ABC + 类属性 parameters |
| **Schema 验证** | Effect Schema decode → execute → encode | 手动 JSON 解析 |
| **权限关联** | Tool.withPermission("edit") | requires_permission + permission_default 类属性 |
| **注册作用域** | Application(进程) + Registry(Location) | 单例 ToolRegistry dict |
| **输出管理** | ToolOutputStore.bound() 大输出写文件 | ToolResult.data 字符串 |
| **LLM 格式** | Tool.definition(name) → ToolDefinition (Schema 自动生成) | to_llm_format() → dict 手动构建 |
| **Materialize** | 按权限过滤 definitions + 固定 settlement | 无对应概念 |
| **工具 ID** | Tool.validateName 校验 | 无 (直接 dict key) |

**影响:** CScode 工具缺少 schema 验证, 输入参数格式问题只能在运行时暴露。ToolResult 的 `data` 字段可能放大量文本 (大文件读取), 导致消息表记录过大。没有作用域概念, 所有工具全局注册, 无法按 workspace 隔离。

### 5. LLM Provider 系统 (差距: 严重)

| 特性 | OpenCode | CScode |
|------|----------|--------|
| **架构** | Route (Protocol + Endpoint + Auth + Framing) 四轴 | 简单 URL + API Key |
| **Stream 事件** | 16 种 LLMEvent (text/tool/reasoning/error/step) | stream() → AsyncIterator[str] |
| **Complete** | generate + generateObject + stream | complete() + stream() |
| **错误模型** | 10 种 LLMError reason, retryable 标记 | ProviderError Exception |
| **Caching** | 自动 cache 策略 (Anthropic/Bedrock/OAI) | 无 |
| **Provider options** | ProviderOptions (reasoning, store, metadata) | 无 |
| **Route 抽象** | Protocol 定义端点, Endpoint 构造 URL, Auth 管理认证, Framing 解析响应 | 每个 provider 自己拼 URL |
| **多协议** | OpenAI Chat + Responses, Anthropic Messages, Gemini, Bedrock | OpenAI 兼容 + Anthropic + Gemini + Ollama |
| **工具调用** | ToolRuntime.dispatch (强类型) | LLMResult.tool_calls (list[dict]) |

**影响:** CScode 的 provider 层过于简单。所有 `complete()` 实现都在本地拼请求 → 发 HTTP → 解析响应。没有 Route 抽象意味着每个 provider 包含大量重复代码。没有标准化错误意味着重试逻辑各 provider 自实现。

### 6. 权限系统 (差距: 中等)

| 特性 | OpenCode | CScode |
|------|----------|--------|
| **规则模型** | Wildcard 匹配 + last-match-wins | 精确名称匹配 |
| **三级效果** | allow / deny / ask | allow / deny / ask |
| **记忆规则** | "always allow" saved rules (持久化) | _policies (内存) + _resolve_table (内存) |
| **作用域** | agent permissions + session permissions + saved | 全局 |
| **事件** | Permission.Event.Asked/Replied (Deferred) | PermissionAskedEvent + resolve() |
| **拒绝传播** | reject 时自动拒绝同一 session 所有 pending | 无 |
| **断言/等待** | PermissionV2.assert() 阻塞 + Deferred | PermissionResult.ASK + 事件 emit |

**影响:** CScode 的权限系统虽然 API 相似, 但缺少持久化和通配符匹配。`_resolve_table` 内存表在进程重启后丢失, 无法记住用户选择。

### 7. 配置系统 (差距: 中等)

| 特性 | OpenCode | CScode |
|------|----------|--------|
| **配置层级** | global → project → .opencode/ | ~/.config/cscode → .cscode/ → ENV → CLI |
| **配置结构** | Info schema (shell, model, agent, permissions, MCP, plugin, provider) | 单 Config dataclass (provider, model, api_base...) |
| **Agent 配置** | 每个 agent 独立 permissions + options + system prompt | 硬编码 plan/build |
| **Provider 配置** | ProviderOptions + Route 配置 | api_base + api_key |
| **格式** | JSON | YAML + ENV |
| **合并** | deep merge + override 优先级 | Config.merge() 手动字段级 |

**影响:** CScode 的 Config 太简单, 无法表达复杂配置 (每个 agent 的权限、MCP 配置、多个 provider 配置)。配置合并逻辑是手动字段赋值, 扩展性差。

### 8. 存储系统 (差距: 中等偏重)

| 特性 | OpenCode | CScode |
|------|----------|--------|
| **ORM** | Drizzle ORM | aiosqlite 原始 SQL |
| **Session 表** | EventV2 (event_sequence + event + projector) | sessions + messages + event_sequences + events |
| **消息存法** | Event Sourcing append-only | "delete → reinsert" 模式 |
| **事件订阅** | Drizzle SQLite notify | EventStore.subscribe (polling) |
| **迁移** | Drizzle migration | _migration_NNN 函数 |
| **并发控制** | Effect Fiber + ScopedCache | per-aggregate asyncio.Lock |
| **检查点** | 投影状态 + 快照 | context_epochs 表存在 |

**影响:** CScode 虽然已经创建了 event_sequences/events 表 (migration_003), 但 **SessionManager 和 engine.py 完全不使用 EventStore**。session 直接写 sessions/messages 表。EventStore 只是个独立组件, 没有集成到 session 生命周期中。

### 9. 错误处理 (差距: 中等)

| 特性 | OpenCode | CScode |
|------|----------|--------|
| **设计模式** | Schema.TaggedErrorClass (typed errors) | Exception 继承 |
| **工具错误** | ToolFailure { message, error } | ToolResult.error (字符串) |
| **LLM 错误** | LLMError { module, method, reason, ... } | ProviderError (无分类) |
| **结构化** | formatError() 统一格式化 | 无 |

**影响:** CScode 的错误无法精确区分类型。OpenCode 可以用 `Cause.failTagged` 匹配具体错误原因, CScode 只能用 `isinstance` 或字符串匹配。

### 10. 上下文压缩 (差距: 中等)

| 特性 | OpenCode | CScode |
|------|----------|--------|
| **压缩策略** | auto + prune + 溢出恢复 | truncate (keep recent N) |
| **溢出检测** | isContextOverflowFailure() + 自动重试 | 无 |
| **配置** | compaction.auto, compaction.prune, compaction.keep.tokens | threshold + keep_recent |
| **Epoch** | ContextEpoch 管理压缩边界 | context_epochs 表存在但未集成 |
| **递归保护** | 重试溢出 → 致命错误 | 无 |

**影响:** CScode 的 ContextCompressor 只是简单的截断, 没有溢出恢复、没有 epoch 管理。虽然有 context_epochs 表, 但 Compressor 根本不使用。

### 11. 架构差距总览

| 维度 | OpenCode | CScode | 影响 |
|------|----------|--------|------|
| 状态管理 | Effect.ts 纯函数式 (State + FiberSet + Semaphore) | Python 对象直接修改 | 状态竞争 bug |
| 事件溯源 | EventV2 (event_sequence + event + projector) | 简单 SQLite 存消息 | 无投影, 查询性能差 |
| 类型系统 | Effect Schema (编译时 + 运行时) | Pydantic (运行时) | 部分类型错误运行时才暴露 |
| 错误模型 | LLMError 10 种 reason + ToolFailure | 简单 Exception | 错误处理不精细 |
| 依赖注入 | Effect Context (Service + Layer) | 手动传参/全局变量 | 模块耦合度高 |

---

## 核心差距画像

### ✅ 现有可用的 (P0-P1 级)

| CScode 已有 | OpenCode 对应 | 可用性 |
|---|---|---|
| Message | SessionMessage | 基本可用但缺 parts |
| EventStore | EventV2 | 表结构已建, 未集成 |
| EventBus | SessionEvent | 简单可用缺细化 |
| PermissionService | PermissionV2 | 基本功能有, 缺持久化 |
| ToolRegistry | ToolRegistry | 基本注册可用 |
| SessionStore | SessionStore | 缺少事件溯源 |
| Config | Config | YAML 加载可用 |
| LLMProvider | LLMClient | 简单可用 |
| ContextCompressor | Compaction | 基本 truncate |
| errors.py | LLMError/ToolFailure | 语义级不一致 |
| context_epochs | ContextEpoch | 表存在未使用 |

### ❌ 完全缺失的 (P0 级)

| 缺失功能 | OpenCode 所在包 | 影响 |
|---|---|---|
| SessionRunner | core/src/session/runner | 核心循环 |
| toLLMMessages | 同上 | 消息格式转换 |
| Tool.materialize | core/src/tool/registry | 工具过滤+编排 |
| PermissionV2.evaluate | core/src/permission | 规则评估 |
| Wildcard 匹配 | 同上 | 规则灵活性 |
| LLMEvent (16 种) | llm/src/schema | 事件标准化 |
| Route (Protocol+Auth) | llm/src/route | Provider 抽象 |
| LLMError 分类 | llm/src/schema | 错误标准化 |
| Schema 验证 | schema package | 输入输出验证 |
| Application/Registry 分离 | core/src/tool | 作用域隔离 |
| 3 层架构 (llm/core/app) | 各个包 | 架构可维护性 |

### ⚠️ 表面相似但实现不同的 (最危险)

| 功能相似 | OpenCode 实现 | CScode 实现 | 危害 |
|---|---|---|---|
| Tool 循环 | SessionRunner 标准化 | 内联 while True | 行为不一致 |
| Tool 调用 | schema decode → settle | json.loads | 运行时崩溃 |
| 配置加载 | route/endpoint/auth 分离 | 单 Config 字段 | 扩展性差 |
| Session 存储 | Event Sourcing | delete+reinsert | 数据丢失风险 |
| 权限检查 | Wildcard 匹配 | 精确名称匹配 | 漏洞 |
| Stream 处理 | 16 种 LLMEvent | AsyncIterator[str] | 功能受限 |
| Token 计数 | 精确分层计数 + Decimal | 可能有粗略 | 收费不准 |

---

## 重写路线图建议

### Phase 0: Schema 层 (基础)
- 定义 `LLMError` Python 等价物 (10 reason enum)
- 定义 `LLMEvent` Python 等价物 (16 event union)
- 定义 `SessionEvent` Python 等价物
- 定义 Message Part 系统 (text/media/tool_call/tool_result/reasoning)
- 定义 Tool 的 input/output Schema (Pydantic 或类似)

### Phase 1: LLM 层 (替换现有 provider)
- Route 系统: Protocol + Endpoint + Auth + Framing
- LLMClient: generate/stream
- ToolRuntime: dispatch
- 用新 Route 系统重写 OpenAI/Anthropic/Gemini provider

### Phase 2: Core 层 (最关键的改造)
- EventV2: 将现有 EventStore 集成到 session 生命周期
- SessionRunner: 替换 engine.py 的 while True 循环
- ToolRegistry: 分离 Application/Registry 作用域
- PermissionV2: 添加 wildcard 匹配 + saved rules 持久化
- Tool.materialize: 按权限过滤 + 输出管理

### Phase 3: Proto/API 层
- 基于现有 FastAPI 重构为核心与协议分离
- 添加 HTTP API 组 (session, agent, tool, fs, command...)

### Phase 4: 应用层重构
- 将所有 CLI/TUI/Server 入口迁移到新架构
- 删除旧的 engine.py / session_manager.py

---

## 技术选型建议

| 领域 | 推荐 | 替代方案 | 不推荐 |
|---|---|---|---|
| **错误模型** | `result` + tagged errors | `returns` (Result/Option/IO) | 纯 try/except |
| **Schema** | Pydantic v2 | msgspec, marshmallow | 无 |
| **DI** | 手动 Service Locator | `inject` | 全局变量 |
| **并发** | asyncio + TaskGroup | trio, anyio | threading |
| **事件** | pydantic + asyncio.Event | 现有 EventStore | 删除重做 |

**核心原则:** 每次推进一个层, 保持各层独立 (Schema → LLM → Core → Proto → App)。不要试图一次性替换所有。
