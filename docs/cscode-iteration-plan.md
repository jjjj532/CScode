# CScode 迭代优化方案（核查修正版 v2）

> ⚠️ **v2 修正说明**：初版（v1）基于 AGENTS.md 规则与旧文档推断 CScode 现状，经 codegraph 逐一核查真实代码后**严重失实**——初版 P0 五项中三项已实现、两项部分实现。本版以 2026-08-18 核查的**实际代码现状**（版本 0.3.6，分支 `pyinstaller-bundle`，git log `b43c30a P0 复刻完成`）为准重写差距清单与路线图。
> 分析源不变：`docs/deepseek-harness-analysis.md`（792 行）+ OpenCode 最新源码（`github/opencode-dev-10`，3,353 文件 / 57,108 节点 / 198,804 边 codegraph 索引）。

---

## 1. 背景与目标

CScode 是一个 AI 编程助手（Python FastAPI + Textual TUI + React 18 + Tauri v2 + SQLite Event Sourcing）。
当前版本 0.3.6，处于 `pyinstaller-bundle` 分支，177 个测试文件。

**核查结论先行**：CScode 已不是初版假设的「待迁移状态」——2026-07 的 commit `b43c30a` 已完成 P0 复刻
（Agent 系统 / Session 引擎 / Plugin v2 + 全模块测试覆盖）。本方案的真实价值在于：

1. 用 OpenCode/dsh 的架构标尺**验证已实现能力的完整性**（哪些是皮毛、哪些是实心）；
2. 定位**真实差距**（多为「半实现」而非「未实现」）；
3. 给出可执行的补强路线图。

---

## 2. OpenCode 深度分析（分析源，不变）

以下为 `github/opencode-dev-10`（Bun + Turborepo + Effect TS monorepo，30+ packages）的 codegraph 探索结论。

### 2.1 架构总览

```
packages/
├── core/        # 核心代数：session/tool/event/provider/system-context/v1
├── opencode/    # 聚合层：effect runner / tool V1 / agent / acp / session llm / plugin loader
├── llm/         # LLM 层：schema(messages/errors) / route / cache-policy / tool / providers
├── schema/      # 共享 schema：session-message / session-event / durable-event-manifest
├── sdk/js       # 生成式客户端：67 个 HeyApiClient 类 + 事件类型目录
├── plugin/      # 插件 v2：Registration/Hooks/Integration/TuiPlugin
├── codemode/    # 受限代码执行（JS 子集解释器 + 工具树 + 执行预算）
├── tui/         # Ink 终端 UI（插件化）
└── app/ console/ desktop/ web/ ui/ session-ui/  # 客户端
```

**关键设计决策**：Effect TS 贯穿全栈（Schema 代数 + Layer 依赖注入 + Effect 错误通道），
所有跨边界数据用 Schema 校验（parse-don't-validate），持久化用 Drizzle SQLite（双表 EventTable + EventSequenceTable）。

### 2.2 System Context 代数（CONTEXT.md 权威定义）

- **System Context**：模型可见的上下文整体。
- **Context Source**：稳定 key + JSON codec + infallible loader + 纯 baseline/update renderer（可选 removal renderer）。
- **System Context Registry**：Location-scoped 注册表，聚合所有 Context Source。
- **Mid-Conversation System Message**：会话中段注入的 durable 指令（跨 epoch 持久）。
- **Context Epoch**：不可变 provider-cache baseline；只有 compaction / 上下文移动 / 不兼容转换才产生新 epoch。
- **Baseline System Context**：epoch 起点的基础上下文。
- **Context Snapshot**：model-hidden 的可覆写 JSON（工具/客户端可写，模型不可见）。
- **Unavailable Context**：上下文源缺失时的降级路径（infallible loader 保证不炸）。

### 2.3 SessionV2 执行模型

- **SessionInput.admit**（`packages/core/src/session/input.ts`）：幂等入口——同 id 已 admit 直接返回 → publish durable `SessionEvent.PromptAdmitted` → 返回 `Admitted(admittedSeq)`。
- **Runner 状态机**（`packages/opencode/src/effect/runner.ts`）：Idle / Running / Shell / ShellThenRun；`ensureRunning` 合并并发 run；`startShell` 在 Busy 时拒绝；`cancel` 干净中断。
- **SessionExecution / SessionRunCoordinator**：协调 prompt 入队与 drain，保证同 session 串行执行。
- **Session.Message schema**：8 种消息（User/Assistant/System/Shell/Synthetic/AgentSwitched/ModelSwitched/Compaction）+ ToolState 四态机（pending/running/completed/error）。

### 2.4 EventV2 持久事件（Drizzle 双表）

- **EventTable + EventSequenceTable**：事件正文与序列号分离；`readAggregate(aggregate_id, seq>after, 分页)`。
- **publish(commit 选项)**：`commit=true` 时本地投影 + durable 事件原子提交（单一事务）。
- **replay / replayAll**：重建投影的权威路径；`/sync/replay` API 供客户端补拉。
- **Durable 注册表**：`Event.define` + `versionedType` + `Durable.get`；`decodeSerializedEvent` 用 Schema.decodeUnknownSync 校验。
- 事件目录：EventSessionNext*（prompted/prompt-admitted/context-updated/step-started/step-ended/step-failed/text/reasoning/tool/retried/compaction）、EventPermissionAsked、EventPermissionV2*、EventPty*、EventQuestionV2*、EventTodoUpdated、EventLspUpdated、EventMcpToolsChanged、EventModelsDevRefreshed、EventIntegrationUpdated、EventCatalogUpdated。

### 2.5 Tool 系统 V1 / V2

- **Tool V2**：`Tool.make({description, input/output/structured schema, execute, toModelOutput})`；`withPermission` 装饰器；settle 管线 = decode input → execute → encode output → structured → toModelOutput。
- **Tool V1**：`define(id, init)`；`wrap` 自动把 decode 错误转 `InvalidArgumentsError`；`Truncate` 服务统一截断输出（`truncated` + `outputPath`）。
- **ToolResultValue**（`packages/llm/src/schema/messages.ts`）：判别联合 `{json, text, error, content}` + `ToolOutput{structured, content}`。
- **ToolCallPart / ToolResultPart**：携带 `providerExecuted`、`cache(CacheHint)`、`metadata`、`providerMetadata`。

### 2.6 LLM 错误代数

`packages/llm/src/schema/errors.ts`：

- **LLMErrorReason 10 种判别联合**：InvalidRequest / NoRoute / Authentication / RateLimit / QuotaExceeded / ContentPolicy / ProviderInternal / Transport / InvalidProviderOutput / UnknownProvider。
- `retryable` getter（结构化决定是否重试，而非异常消息子串匹配）。
- **LLMError 携带 `module.method`** + `reason` + `cause` + `retryAfterMs`。
- **ToolFailure 独立类型**：工具失败不是 LLM 缺陷——只有非 ToolFailure 才算 defect。
- **HttpContext**：request/response/requestId/rateLimit 全套保留。
- provider 层 `ResponseStreamError` / `ParsedStreamError` 区分「流中断」与「解析失败」。

### 2.7 Compaction 序列化细节

`packages/core/src/session/compaction.ts`：

- 常量：DEFAULT_BUFFER=20_000 tokens / DEFAULT_KEEP_TOKENS=8_000 / TOOL_OUTPUT_MAX_CHARS=2_000 / SUMMARY_OUTPUT_TOKENS=4_096。
- **序列化规则**：user → `[User]: text` + `[Attached mime: name]`；assistant → `[Assistant]: text` / `[Assistant reasoning]` / `[Assistant tool call]: name(input)` / `[Tool result]: truncated` / `[Tool error]: message`；system → `[System update]`；synthetic → `[Synthetic context]`；shell → `[Shell]: command\noutput`。
- **select 算法**：从尾部累积 Token.estimate，切出 head（压缩前段）与 recent（保留段）；head 交给摘要 prompt。

### 2.8 Permission 系统（事件驱动）

- **EventPermissionAsked / EventPermissionReplied**：permission 请求是事件而非同步阻塞调用。
- `client.permission.reply({requestID, reply: "once"|"always"|"reject"})`。
- SDK `Request.list()`（GET /api/permission/request）查询待处理请求。
- Permission V1 与 V2 并存迁移。

### 2.9 Agent / ACP

- **Agent.Info / Agent.Service**：modes = build / plan / subagent。
- **ACP 服务器**：session / loadSession / resumeSession / forkSession / prompt / cancel——与外部 agent 互操作。

### 2.10 Plugin v2（Registration + Hooks + Integration）

- **Registration{Effect, Hooks, RuntimeHandler, Loader, Interface, ExecuteOptions, Runtime, execute}**；effect 与 promise 双 API。
- **Integration 注册**：OAuth（auto/code 两模式）/ Key / Env 三种 method；`IntegrationDraft{list/get/update/remove}` + `IntegrationHooks{connection.active, connection.resolve}`。
- **TuiPlugin**：api 暴露 app/attention/command/keys/keymap/mode/route/ui(10 组件)/kv/state/theme/client/event/renderer/slots/plugins/lifecycle。
- Loader：Plan → Resolve → Attempt → Load → start，带 retry 报告。

### 2.11 codemode：受限代码执行（真正的沙箱解释器）

- **自研 JS 子集解释器**：不跑子进程，解释执行受限 JS。
- **显式工具树**：程序通过 `tools.ns.tool(...)` 调用 host 工具；`assertValidTools` 校验。
- **执行预算**：`ExecutionLimits{timeoutMs, maxToolCalls, maxOutputBytes}`。
- **诊断代数**：DiagnosticKind 10 种，带 location + suggestions。
- **Result 双态**：`Success{ok:true, ...}` / `Failure{ok:false, error:Diagnostic, ...}`——**程序失败是数据不是异常**。
- **工具调用并发**：Semaphore 限流 + SandboxPromise；`drainPendingSettlements` 处理未 await 调用。

### 2.12 TUI（Ink 插件化终端 UI）

- App.tsx：useTuiStartup / useRoute / useTerminalDimensions / createTuiApi → pluginHost.start。
- 命令面板系统化：session/model/agent/mcp/provider/theme/workspace 全量命令。
- 主题 + Renderer.addPostProcessFn。
- **sync 竞态处理**：`--session --fork` 等 `sync.status === "complete"` 再 fork，避免 reconcile 覆盖新建 session。

### 2.13 SDK 生成客户端

- 67 个 `HeyApiClient` 子类，`V2` 门面懒加载，全部端点按 OpenAPI 生成。
- **Persist 作用域键**：global / workspace / session 三级。

---

## 3. DeepSeek Harness 分析摘要（分析源，不变）

### 3.1 核心架构结论

- **Cordis 插件树**：一切皆插件，Profiles + Bundles 组合层。
- **Session log + 投影**：事件溯源，模型消息词汇统一。
- **Capability Seams（能力缝）**：三角色模型——host / agent / seam——「新行为放哪里」有明确决策表。
- **工具分层注册表**：scoped registry + ToolDefinition 契约 + 工具渲染是设计的一部分。
- **LlmAdapter 缝**：SSE 断连重试、超时、chunk 校验 + LlmError 结构化失败。
- **沙箱体系**：平台 runner 链（landlock/seatbelt/E2B），拒绝升级。
- **ApprovalPolicy + permission-presets**：审批策略可组合、可预设。
- **子代理体系**：10 个 provider 实现 + 委托工具（Consumers）。
- **Skill 体系**：skill service + skill-local + tool-skill-catalog/loader。
- **Compaction**：compaction-basic + tool-result-pruner（token 管理）。
- **Workflow**：worker-thread 实现。
- **Native Landlock**：OS 级文件访问限制。

---

## 4. CScode 现状核查（v2 核心章节——codegraph 逐一验证）

> 核查方法：对 `src/cscode/` 全部关键模块做 codegraph_explore + 源码阅读，
> 结论以 2026-08-18 磁盘上的真实代码为准。

### 4.1 已实现且基本完整（初版 v1 误判为缺失）

| 能力域 | 实际实现（文件 + 证据） | 与 OpenCode 对照 | 完整性 |
|---|---|---|---|
| **LLM 错误代数** | `schema/errors.py`——LLMErrorReason 10 枚举（文件头注释直书 "Mirrors OpenCode's LLMError hierarchy"）+ LLMError + ToolFailure | §2.6 基本对齐 | ✅ 完整 |
| **System Context 代数** | `core/system_context/__init__.py`——ContextSource（key/load/baseline/update/removed）+ make/combine/initialize/reconcile + UNAVAILABLE + 内置 env/date/instructions 源 | §2.2 对齐 | ✅ 完整 |
| **Context Epoch** | `core/context_epoch.py`——context_epochs 表 + SNAPSHOT_VERSION + 快照序列化 | §2.2 epoch 概念 | ✅ 完整 |
| **SessionInput admit** | `schema/session_input.py` + `core/session_v2.py`——DeliveryMode STEER/QUEUE + AdmittedInput + admitted_seq/promoted_seq | §2.3 admit 幂等 | ✅ 完整 |
| **SessionRunner** | `core/runner.py`——SessionRunner.run / run_with_execution / run_stream + SessionExecution 生命周期 | §2.3 Runner | ✅ 完整 |
| **AgentMode** | `core/agent/base.py` + build/plan/subagent 实现 + SubAgentOrchestrator | §2.9 build/plan/subagent | ✅ 完整 |
| **工具 settle 管线** | `tools2/registry.py`（ToolRegistryV2 materialize→settle，178 行）+ `app/agent.py` `_settle(tc.name, args)` + 35 个 BaseTool | §2.5 settle | ✅ 完整 |
| **工具缓存提示** | `llm/cache_policy.py`——CacheHint（SPEC §3.4）+ 自动 cache_control 插入（Anthropic/Bedrock）| §2.5 CacheHint | ✅ 完整 |
| **Plugin v2（Python）** | `plugins/sdk.py` + `plugins/context_source.py`（PluginContextSource 集成 System Context）+ hooks/lifecycle/loader/manifest | §2.10 | ✅ 完整 |
| **权限事件流** | `core/events.py` PermissionAskedEvent/PermissionRepliedEvent + `core/permission_v2.py`（427 行 PermissionV2 ALLOW/DENY + SQL 表）+ `core/permissions.py` PermissionService | §2.8 | ✅ 完整 |
| **事件原子性 + 补拉** | `storage/event_store.py`——append 原子（UPDATE event_sequences + INSERT events + commit/rollback）+ read(after_seq) + scan_events_global(after_id) + subscribe + scan_events_by_type | §2.4 双表 + 补拉 | ✅ 完整 |
| **MCP OAuth** | `mcp/auth.py`——OAuthClientProvider + 授权码/PKCE + client credentials + token refresh | 超越 OpenCode 基线 | ✅ 完整 |
| **SyncPanel** | `web/src/components/SyncPanel.tsx` + `/api/sync/events` + `/api/sync/push` | §2.12 sync | ✅ 完整 |
| **Skill 体系** | `skills/loader.py`（140 行）+ skill service | dsh §13 | ✅ 基本 |
| **Integration** | `server/integration.py`（380 行） | §2.10 Integration | ✅ 基本 |
| **providers** | `providers/` 16 个（anthropic/azure/bedrock/cohere/copilot/gemini/grok/mistral/nvidia/ollama/openai/openrouter/perplexity/vertex/xai...） | — | ✅ 完整 |
| **协议组** | `protocol/groups/`（config/sessions/tools）+ `acp/protocol.py` | §2.9 ACP | ⚠️ 见 4.2 |
| **测试** | `tests/` 177 个文件（test_system_context / test_context_epoch / test_session_v2 / test_tools2_contract ...） | — | ✅ 完整 |

### 4.2 真实差距（半实现或未实现）

| # | 差距 | 现状证据 | OpenCode 标尺 | 等级 |
|---|---|---|---|---|
| G-1 | **Compaction 未 token 化、SUMMARIZE 未实现** | `server/compactor.py`：snapshot 是固定文本 `"Previous context with N messages has been compacted."`，非 LLM 摘要；`core/compression.py`：ContextCompressor 用**字符数**（threshold=100_000 chars）非 token 估算，SUMMARIZE 策略 `logger.warning("not yet implemented, falling back to TRUNCATE")` | §2.7：Token.estimate + 序列化规则 + head/recent 切分 + 摘要 prompt | **高** |
| G-2 | **TruncateTool 是 stub** | `tools2/truncate.py`：execute 注释 "In a real implementation this would interact with the conversation store"——只返回假数据，未接入会话存储 | §2.5 Truncate 服务统一截断 | **高** |
| G-3 | **ToolResult 无判别联合** | `tools2/base.py`：ToolResult 只有 success/data/error/tool_call_id/metadata；缺 `{json, text, error, content}` 判别 + ToolOutput{structured, content} + providerExecuted | §2.5 ToolResultValue | 中 |
| G-4 | **codemode/OS 沙箱皆无** | `core/container.py` 是 **ServiceContainer（DI 容器）**非沙箱（无 run_code/subprocess/sandbox）；全文无解释器执行 | §2.11 codemode + dsh sandbox | **高** |
| G-5 | **ACP 仅 93 行极简协议** | `acp/protocol.py`（93 行）只有协议定义，无 session/loadSession/resumeSession/forkSession/prompt/cancel 服务器 | §2.9 ACP 服务器 | 中 |
| G-6 | **TUI 未插件化** | `tui/app.py` 无 plugin 引用（rg 零命中）；Textual 自研，无命令面板系统化/插件 API | §2.12 TuiPlugin | 中 |
| G-7 | **SDK 手写非生成** | 前端 `web/src/lib/api.ts` 手写 REST client；无 OpenAPI 生成 | §2.13 67 HeyApiClient | 低 |
| G-8 | **前端 sync 竞态未显式处理** | SyncPanel 有拉取/推送，但未见 `sync.status === "complete"` 再 fork 的竞态保护 | §2.12 竞态处理 | 低 |

> 初版 v1 的 P0-1/P0-2/P0-3/P0-5 因「已实现」从路线图移除；P0-4（Compaction）修正为 G-1（半实现）；
> 其余按核查结果重排。

---

## 5. 迭代路线图（v2 重排）

### 原则（不变）

1. **分层独立**：Schema → LLM → Core → App，禁止跨层 import。
2. **TDD 先行**：每个能力先写契约测试（压缩序列化、判别联合、截断语义），再写实现。
3. **Ratchet**：每次修复的边界情况 → AGENTS.md 规则 + 测试。
4. **最小迁移**：只补真实差距，不为对标而对标。

### P0 — 架构级（真实差距，影响会话质量与安全）

| # | 能力 | 现状 → 目标 | 目标文件 | 验收标准 |
|---|---|---|---|---|
| P0-1 | **Compaction token 化 + LLM 摘要** | `server/compactor.py` 固定文本 + `core/compression.py` 字符数 → Token.estimate + 序列化规则（`[User]/[Assistant]/[Tool result]`）+ head/recent 切分 + 摘要 prompt 替换固定文本；SUMMARIZE 落地 | `core/compression.py`、`server/compactor.py`、新增 `core/token_estimate.py` | 超长会话（>20k token）可压缩恢复；序列化格式单测锁定；摘要由 LLM 生成而非占位符 |
| P0-2 | **TruncateTool 接入会话存储** | stub → 真实调用 Compactor/EventStore，返回实际 freed tokens | `tools2/truncate.py` | 调用后 context_epochs 新增 epoch；remaining_tokens 反映真实剩余 |
| P0-3 | **ToolResult 判别联合 + providerExecuted** | `tools2/base.py` 简单 dataclass → `{json, text, error, content}` 判别 + ToolOutput{structured, content} + providerExecuted 字段（兼容 Anthropic computer use 等 provider 预执行） | `tools2/base.py`、`schema/messages.py` | 35 个工具迁移后类型检查通过；provider 预执行结果不破坏会话数据模型 |
| P0-4 | **受限执行沙箱（轻量）** | 无 → 借鉴 codemode 思路：**Python 子集解释器或受限 runner**（预算 timeoutMs/maxToolCalls/maxOutputBytes + 诊断代数 + 失败即数据非异常）——先评估解释器 vs 子进程成本 | 新包 `src/cscode/sandbox/` | 模型生成的受限脚本可安全执行；超预算/非法调用返回结构化诊断；OS 沙箱作为 P2 远期 |

### P1 — 能力级（影响扩展性）

| # | 能力 | 说明 |
|---|---|---|
| P1-1 | ACP 服务器完整化 | `acp/protocol.py` 93 行 → session/loadSession/resumeSession/forkSession/prompt/cancel 端点（复用 SessionRunner） |
| P1-2 | TUI 插件化 | Textual 插件 API + 命令面板系统化（session/model/agent/theme 命令对齐 OpenCode） |
| P1-3 | Permission always 记忆持久化 | PermissionV2 已有 ALLOW/DENY 表——补 `once/always/reject` 三态 reply 语义 + 待处理队列查询 API |

### P2 — 增强级（可选，按需）

| # | 能力 | 说明 |
|---|---|---|
| P2-1 | OS 沙箱 | Landlock/Seatbelt 级文件访问限制（dsh §18），在 P0-4 之上增强 |
| P2-2 | SDK 生成客户端 | OpenAPI 生成前端 client（替代手写 api.ts） |
| P2-3 | 前端 sync 竞态处理 | `sync.status === "complete"` 再 fork 的保护逻辑 |

### 批次顺序建议（v2）

```
迭代 1: P0-1 Compaction token 化 + 序列化    （会话质量最高杠杆，契约测试先行）
迭代 2: P0-2 Truncate 接入 + P0-3 ToolResult 判别联合（工具层收尾）
迭代 3: P0-4 受限执行沙箱（先成本评估）
迭代 4: P1-1 ACP → P1-2 TUI 插件化 → P1-3 权限三态
迭代 5+: P2 按需
```

---

## 6. 风险与依赖

- **Python 无 Effect TS**：判别联合用 `@dataclass + Literal + pydantic` 模拟（AGENTS.md 已有类型标注约束）。
- **沙箱成本不确定**：P0-4 必须先做成本评估（解释器 vs 子进程 vs OS 沙箱），避免过度设计——初版教训：假设必须验证。
- **Compaction 摘要依赖 LLM 调用**：P0-1 的 SUMMARIZE 需要 provider 调用，需设计降级路径（摘要失败回退 TRUNCATE，现状已有此骨架）。
- **改动现有工具层风险**：P0-3 改 `tools2/base.py` 影响 35 个工具 + `tests/test_tools2_contract.py`，必须契约测试先行。

---

## 7. 总结（v2）

**核查修正后的结论**：CScode 已完成 OpenCode 架构的 P0 复刻（Agent/Session/Plugin v2/错误代数/上下文代数/事件原子性），
真实差距集中在**四个半实现点**：Compaction 未 token 化（G-1）、Truncate stub（G-2）、ToolResult 无判别联合（G-3）、无任何沙箱（G-4）。
这四件事分别影响**会话质量**、**工具层完整度**、**消息模型健壮性**、**安全执行能力**，构成 v2 的 P0。

> **方法论教训（Ratchet）**：本方案 v1 因「基于规则与旧文档推断现状」而失实。修正后补入 AGENTS.md：
> 「制定迭代方案前，必须用 codegraph 核查目标模块现状，禁止凭文档假设推断已实现能力。」
> 相关文档：`docs/deepseek-harness-analysis.md`（dsh 全量分析）、`docs/opencode-1to1-gap-analysis.md`（旧版差距分析，同样需对照本核查更新）。