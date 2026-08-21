# DeepSeek Harness 深度源代码分析

> 分析对象：`https://github.com/deepseek-ai/deepseek-harness.git`（本地 `/Users/mac/AI/DeepSeekHarness`）
> 分析方式：codegraph（3,867 文件 / 40,483 节点 / 228,054 边）+ 源码精读
> 分析目的：提取 DeepSeek Harness 的优秀能力，为迁移到 CScode 应用提供依据
> 分析日期：2026-08-18（仓库当前为 developer preview，兼容性破坏性变更频繁）

---

## 1. 项目概览

DeepSeek Harness（`dsh`）是 DeepSeek AI 开源的 **Agent Harness**（代理运行时），采用 **"一切皆插件"（everything is a plugin）** 架构，构建在自研 vendored 的 [Cordis](https://github.com/cordiverse/cordis) 框架之上。

### 1.1 一句话定位

> 一个以 **追加式会话事件日志（SessionEvent log）** 为单一事实来源、以 **可替换能力缝（capability seam）** 为扩展机制、所有产品功能都以插件形式挂载的 agent 运行时。

### 1.2 技术栈

| 层 | 技术 |
|---|---|
| 运行时 | Node.js（^22.19 \|\| >=24），ESM-only，TypeScript strict |
| 框架 | Cordis（vendored，插件/服务/事件/效应模型） |
| 配置 | YAML（`cordis.yml` / `cordis.patch.yml`）+ schemastery schema 校验 |
| 构建 | pnpm workspaces，tsc + tsdown |
| 测试 | vitest，单文件 100% 覆盖率门槛，snapshot 测试，real-API e2e |
| 原生 | Rust addon（`landlock-run`，Linux 沙箱启动器） |
| Python | 独立 SDK（`python/sdk`，JSON-RPC over stdio） |

### 1.3 仓库布局（关键部分）

```
vendor/          vendored Cordis 源码（manifest + sync procedure）
packages/        @deepseek-ai/dsh-<pkg> workspaces，按组分布：
  core/           产品 API 脊柱：session, system-prompt, tools, agent, agent-loop
  llm/            LLM 能力：Service Definition/Consumer + DeepSeek providers
  e2b/            E2B POC：远程沙箱 + FS/subprocess 适配器
  shell/          bash 能力 + local/pwsh providers + shell Consumers
  subprocess/     subprocess 能力 + local process-tree provider
  terminal/       持久 PTY 会话
  fs/             文件系统能力 + 策略
  lsp/            language-server 能力
  skill/          skill provider 注册表 + 本地实现 + catalog/loader 工具
  web/            web 能力：Service Definition + search/fetch providers + tool Consumer
  compaction/     压缩能力 + 基础实现
  subagent/       subagent 能力：Service Definition + providers + 委托 Consumers
  workflow/       workflow 能力 + worker-thread provider + tool Consumer
  todo/           todo_write 工具
  plan/           plan mode（作为已记录状态）
  preset/         按 session 组合 agent（preset cordis.yml）
  guard/          loop-hygiene + tool-timeout 插件
  hooks/          Claude Code/Codex hook 桥 + wire-protocol 库
  session/        持久会话数据：持久化、投影、标题、遥测
  settings/       user-settings 能力 + file provider
  credentials/    credential-reference 能力 + env/.env provider
  acp/            Agent Client Protocol 服务器
  interaction/    approval/interaction 能力、permission、commands、ask-user
  boot/           共享 app-bin 胶水
  sdk/            JSON-RPC 协议、服务器、TypeScript 客户端
  api/            Remote BFF 组装 + Typert RPC 网关
  typert/         类型图生成器、loader、运行时注册表
apps/
  cli/            dsh CLI（profile 引导、headless）
  web/            Web UI
python/
  sdk/            Python SDK（DeepSeekHarness/Session 对）
  sdk-runtime/    Python 运行时
native/
  landlock-run/   Rust 源码（node addon，按平台分包）
examples/        可运行的 cordis.yml 叶子
docs/             架构文档、生成目录、cookbook、事后分析
```

---

## 2. 核心架构：Cordis 插件树

### 2.1 一切皆插件

dsh 没有"特权核心"。**模型适配器、工具注册表、会话日志、agent 循环本身都是插件**，因此每一部分都可以从配置替换。扩展 dsh 的方式是"在旁边挂一个插件"——注册是 **效应（effect）**，插件卸载时自动回滚（`ctx.effect()` / `ctx.on()`，registry 的 `register()` 返回 disposer）。

关键机制：
- **服务（Service）**：通过 `ctx.<key>` 注入的具名能力（如 `ctx.sessions`、`ctx.tools`、`ctx.llm`）
- **类型化事件（typed events）**：用 TypeScript 声明合并（declaration merging）扩展事件映射，如 `declare module '@deepseek-ai/cordis' { interface Events { ... } }`
- **可逆效应（reversible effects）**：所有注册都是 effect，卸载即撤销

### 2.2 Profiles 与 Bundles（组合层）

运行中的 dsh 是一棵插件树，由 boot 时按有序层组合：

- **Profile**：一个具名组合，存于 Harness home（`$DSH_HOME/profiles/<name>/`），列出它堆叠的 bundles，持有用户的 `cordis.patch.yml`。`web` 和 `headless` 是内置模板。
- **Bundle**：Cordis 配置行 + 其挂载代码的分发格式，插入的内容仍可被上层 patch。
- **层应用顺序**：每个 bundle（按 profile 列出的顺序）→ profile 的 `cordis.patch.yml` → home 级 patch → 任何 `--patch` 覆盖层。patch 按行 id 定位并替换整行配置，或插入新行。
- 每个包在自身 `package.json` 的 `dsh` 字段声明角色：`dsh.profile.bundles`（profile 的 bundle 列表）、`dsh.bundle.patch`（bundle 的 patch 文件路径）。
- 用 `dsh --profile web --dump-config` 可打印实际 boot 的完整树，任意一行都可被自己的 patch 替换。

```ts
// packages/boot/app-boot/src/profile.ts — Profile 结构
export interface Profile {
  name: string        // profile 目录 basename
  dir: string         // 绝对 profile 目录
  layers: ProfileLayer[]  // dsh.profile.bundles 顺序解析出的 bundle 层
  patchPath: string   // 用户 patch 文件绝对路径
  patches: PatchOptions[]  // profile 自身 patch
}
```

### 2.3 核心包职责表

| 包 | 负责 | ctx 键 |
|---|---|---|
| `core/session` | 追加式 `SessionEvent` 日志 + 内存存储 | `ctx.sessions` |
| `core/system-prompt` | prompt section 与工具 schema 组装 | `ctx.systemPrompt` |
| `core/tools` | 作用域工具注册表 + 守卫执行管线 | `ctx.tools` |
| `core/agent` | `Agent` 接口、活动注册表、`agent/*` 事件 | `ctx.agents` |
| `core/agent-loop` | 实现该接口的默认驱动器 | `ctx.agentLoop` |
| `core/scope` | 每 agent 作用域注册原语 | 库，无键 |
| `llm/llm` | 消息与流词汇 + 适配器缝 | `ctx.llm` |

---

## 3. 事件系统（扩展点）

选择正确的领域是大多数改动的第一个决策。三类事件：

| 类型 | 语义 | 例子 |
|---|---|---|
| **Session events** | 追加到日志的**持久事实**，通过 `session/event` 广播；重载后仍存活 | `turn/*`、`step/*`、`user/message`、`assistant/*`、`tool/*` |
| **Agent events** (`agent/*`) | 携带**活的 `Agent`**：inbox、step、status、request、validation、continuation；用于观察/拦截在途工作 | `agent/pre-step`、`agent/request`、`agent/turn-stopping` |
| **Capability events** | 给缝（`fs/*`、`tools/*`、`telemetry/*`）挂策略与适配器，不 import 循环 | `fs/*`、`tools/*` |

**Waterfall 语义**：`agent/pre-step`、`agent/request`、`llm/stream`、`tools/*` 是瀑布事件——监听者**必须调用 `next()`** 委托，不调用即短路链条。`agent/turn-stopping` 是串行事件，没有 `next()`。

```ts
// 事件声明（类型化，declaration merging）
declare module '@deepseek-ai/cordis' {
  interface Events {
    /** 工具被注册或注销；@mode emit */
    'tools/change'(): void
  }
}
```

---

## 4. Turn 流程（agent-loop）

### 4.1 概念

- **step**：一次模型请求 + 它调用的工具
- **turn**：零或多个 step；在第一个输入被认领前打开，无所欠时关闭

### 4.2 完整流程图（来自 docs/architecture.md）

```text
turn/start
  claim next-step input plus one queued message
  assemble prompt sections + tool schemas
  -> agent/pre-step                   reject | enter(messages)
     reject, or a first enter rewritten empty -> close the turn with no step
     step/start
     append entered messages as user/message
     derive model history from the log
     agent/request -> llm/stream -> assistant/chunk* -> assistant/message
     tool/call* -> tools/pre-execute -> tools/execute -> tools/post-execute -> tool/result*
     step/end
     tools owe another request, or next-step input arrived -> claim -> next step
  -> agent/turn-stopping
turn/end
```

### 4.3 实现细节（`packages/core/agent-loop/src/agent.ts`）

`ReactLoopAgent implements Agent`，核心状态机是 `Phase` 判别联合：

```ts
type Phase =
  | { kind: 'idle'; lastTurn: number }
  | { kind: 'maintenance'; abort: AbortController; lastTurn: number; wakeRequested: boolean }
  | { kind: 'running'; abort: AbortController; turn: number; step: number; wakeRequested: boolean }
```

turn 循环关键逻辑：
- **max-tokens 粘性**：任何 step 触顶后，后续正常完成的 step 不能把 turn 结局降级
- **结构化错误**：`LlmError` 保留事实；其他错误压平为 `errorChain` 文本 + `UNKNOWN` code
- **输入经一个 inbox 到达**：某些消息立即唤醒；注入的上下文在 inbox 等待直到另一条消息唤醒
- **Model-visible ⟺ logged（运行时不变量）**：任何到达模型请求的内容必须能从会话日志重建，新模型可见输入需要新的 session event 类型

```ts
// turn 主循环骨架（精简）
while (true) {
  signal.throwIfAborted()
  const decision = await this.preStep(target, { turn, step })
  if (decision.kind === 'reject') { turnEnds = { kind: 'blocked' }; return false }
  if (turnEnds && decision.messages.length === 0) break
  this.session.append('step/start', { turn, step })
  const stepEnd = await this.step(decision.assembly)   // 单次模型请求
  this.session.append('step/end', { turn, step })
  if (turnEnds && this.inbox.nextStep.length === 0) {
    await this.dispatch.serial('agent/turn-stopping', { turn, signal })
  }
  if (turnEnds && this.inbox.nextStep.length === 0) break
  target = 'next-step'
}
```

---

## 5. 会话日志（Session log）与投影

### 5.1 设计核心

- 会话日志是**模型看到上下文的唯一来源**：`deriveMessages()` 从日志投影模型历史；原始 `assistant/chunk` 事件保留重放与 UI 保真
- Fork、resume、transcripts、telemetry、persistence 全部派生自这一事件流
- `SessionEventMap` 可扩展（declaration merging），新增模型可见输入必须扩展事件映射

### 5.2 持久化（`packages/session/session-persistence*`）

- **`PersistenceCoordinator`**（`session-persistence`）：协调器，抽象后端
- **`SqliteSessionPersistence`**：SQLite 后端
- **`JsonlSessionPersistence`**：JSONL 后端（含 zstd 压缩测试）
- **会话投影**（`session-projection` / `session-projection-cache`）：投影缓存
- **会话统计**（`session-stats`）：`sessionStats` 投影
- **会话标题**（`session-title*`）：LLM 生成（first-prompt / all-prompts）
- **遥测**（`session-telemetry` / `session-telemetry-otel`）：OpenTelemetry

### 5.3 模型消息词汇（`packages/llm/llm/src/message.ts`）

统一的不可变消息表示，跨传递、持久历史、模型请求三个边界共享：

```ts
export interface Message {
  readonly id: MessageId          // 稳定身份，跨表示边界保留
  readonly role: 'system' | 'user' | 'assistant'
  readonly content: ContentBlock[]  // 精确模型面向块
  readonly source: MessageSource    // 生产者来源
}
```

**`MessageSourceMap`（merge-extensible 和类型，插件添加自己的 `kind`）**：

```ts
export interface MessageSourceMap {
  user: { kind: 'user' }
  plugin: { kind: 'plugin'; plugin: string } & ContextFormed
  model: ModelMessageSource      // provider + model + 可选 replayState
  tool: ToolMessageSource        // kind: 'tool'; callId
}
```

**`ContextForm`（语义化上下文形式）** —— dsh 极有设计感的一点，词汇是**语义**而非视觉：

```ts
export type ContextForm =
  | 'instructions'  // 从工作区文件读出的指令
  | 'catalog'       // 本 session 可用条目目录（变化时重发布）
  | 'snapshot'      // 当前状态快照（后一个快照取代前一个）
  | 'notice'        // 一次性事件说明（不取代任何东西）
  | 'relay'         // 另一 agent 给本 agent 的消息
  | 'recall'        // 从另一 session 日志提取的材料（可能已缩减）
```

快照形式要求 `sections`（具名贡献，按组装顺序）；notice 要求 `summary`（≤120 字符）。

---

## 6. Capability Seams（能力缝）

### 6.1 三角色模型

**Seam = Service Definition + Service Provider + Consumer**（一个包可兼多角色，但单一角色不构成缝；添加能力 = 设计全部三个角色）。

- **Service Definition**：声明接口（如 `SandboxProvider`、`WebFetchProvider`、`SubagentProvider`、`TerminalBackend`）
- **Service Provider**：实现它（如 `LocalSandboxProvider`、`HttpFetchProvider`、`ClaudeCodeProvider`、`BashTerminalBackend`）
- **Consumer**：使用它，通常是模型面向工具（如 `tool-web`、`tool-bash`）

### 6.2 缝的关键价值

**一次 provider 切换改变整个产品**：文件系统与子进程 provider 共享一个执行世界，把二者指向远程沙箱（E2B），Bash、PTY、LSP 随之一同迁移，无需 provider fork。Subagent providers 在同一接口后变化极大——从全新子代理到另一产品的委托 turn。

### 6.3 "新行为放哪里"速查表（来自 docs/architecture.md）

| 目标 | 机制 |
|---|---|
| 添加模型 provider | 在 `ctx.llm` 注册适配器 |
| 添加模型面向能力 | 在 `ctx.tools` 注册；其 schema 加入 prompt 组装 |
| 给某个 session 不同能力集 | 组合 agent preset；service 行需要 `isolate` realm |
| 添加 shell 执行 | 注册 `ctx.shell` 后端；本地经由 `ctx.subprocess` spawn |
| 添加持久终端执行 | 注册 `ctx.terminals` 后端 + `dsh-tool-terminal` |
| 添加人类命令 | 在 `ctx.commands` 注册；无需模型 turn 即分发 |
| 添加后台工作 | 在 `ctx.jobs` 注册；`job_*` 工具收集/停止 |
| 添加文件系统访问/策略 | 注册 `ctx.fs` provider 或监听 `fs/*` 事件 |
| 限制 spawned 进程 | 用 `ctx.sandbox` 后端；consumers 在 spawn 前包装 argv |
| 拦截请求/工具/turn | 用 `agent/*` 或 `tools/*` 事件；`agent/turn-stopping` 停 turn |
| 添加模型面向上下文 | 调用 `agent.inject()`；落入下一次被认可的请求 |
| 添加持久 session 状态 | 扩展 `SessionEventMap`；从日志渲染与重放 |
| Fork 活跃 session | `ctx.sessions.fork(source, boundary?, childSessionId?)` |

---

## 7. 工具系统（core/tools）—— 深度剖析

### 7.1 分层注册表（scoped registry）

`ToolRegistry` 的核心是 **分层（layers）** 模型，每个 agent 作用域有自己的层：

```ts
class ToolLayer implements ScopeLayer {
  readonly tools: NamedEntries<ToolDefinition>
  readonly restrictions = new AnonymousEntries<CompiledToolRestriction>()
  readonly guards = new AnonymousEntries<ToolGuard>()
}
```

- `register(definition)`：全局或调用 agent 作用域注册；**作用域工具遮蔽全局**；同名重复与保留名 `run_code` 失败
- `guard(guard)`：注册同步守卫，返回字符串即拒绝执行
- `get(name, scope?)`：解析作用域可见定义
- `execute(exec)`：完整执行管线（pre-execute → execute → post-execute 瀑布）

### 7.2 ToolDefinition 契约

```ts
// 精简
export interface ToolDefinition {
  name: string
  schema: ObjectJsonSchema       // 必须支持的 JSON schema 子集
  timeoutMs?: number
  output: {                       // 必填：声明输出 schema + 渲染
    schema: ObjectJsonSchema
    render(...): ToolResultView
    presentationMeta?(...): PresentationMeta
  }
  execute(input: ToolExecutionInput): Promise<ToolExecutionResult>
}
```

`execute` 返回判别联合 `ToolExecutionResult = ToolExecutionSuccess | ToolExecutionFailure`；错误结构化为 `{ code, message, retryable, cause? }`。

### 7.3 工具渲染是设计的一部分

> "A tool's UI render intent is part of its design, decided up front（`generic`/`terminal`/`diff`，`locations`）；presentation methods are pure functions of `args`"

即工具的 UI 渲染意图在**设计时就定**，表示方法必须是 args 的纯函数——这是 dsh 对工具 UX 的强约束。

### 7.4 Code Mode / `run_code`

- `run_code` 名称被**无条件保留**：任何 agent 都可能为自己选择 code mode，故该名字在部署默认下空闲也会成为 preset 挂载时的冲突
- Code Mode 需要 `ctx.codeRuntime`（如 `@deepseek-ai/dsh-code-runtime-worker-thread`）；`requireCodeRuntime(mode)` 校验渲染器语言
- 工具执行有嵌套语义：`rootCallId`（根模型请求调用）+ `token`（注册表分配的嵌套不透明令牌）+ `parent`

### 7.5 人类命令（interaction/commands）

与工具不同，**命令不经模型 turn**，直接分发：

- `ctx.commands.register(definition)`：`name`、`description`、可选 `input.hint`、`recordInput`、`handler`
- `command/run` ↔ `command/done` 事件对（按 `commandId` 配对），记录 handler 的规范化结果
- `CommandResult = { kind: 'success'; text?; sourceEventSeq? } | { kind: 'error'; text }`

---

## 8. LLM 层（llm/llm + llm-deepseek）

### 8.1 适配器缝（LlmAdapter）

`DeepSeekAdapter` 是第一个真实适配器，一个实例服务它注册的每个模型名（harness 模型名 == wire 模型名）。

核心能力：
- `providerInfo(provider)`：提供方元数据
- `providerRetryPolicy(provider)`：解析重试策略（llm-retry 包）
- `listModels(provider)` / `resolveModel(provider, model)`：模型目录 + 解析（contextWindow、maxTokens、reasoning efforts）
- `stream(options)`：**AsyncIterable<StreamChunk>** 流式接口

### 8.2 流式调用的健壮性（值得迁移的设计）

```ts
async * stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
  // 每次流调用一次解析：连接事实与凭据在此冻结并持续整个请求
  const connection = this.config.options()
  const apiKey = await this.config.resolveApiKey(connection)
  // 凭据从同一快照解析 → endpoint 与其密钥永不来自不同配置代
  const consumer = new AbortController()
  const upstream = options.signal === undefined ? consumer.signal
    : AbortSignal.any([options.signal, consumer.signal])
  using watchdog = idleWatchdog(upstream, connection.streamIdleTimeoutMs, STREAM_IDLE_TIMEOUT_CODE)
  ...
}
```

- **凭据/配置快照一致性**：在途流永不观察到配置变更；密钥解析自同一快照
- **空闲看门狗**：每次读取有 idle timeout（`STREAM_IDLE_TIMEOUT` code）
- **错误码规范化** `httpErrorCode(status, error)`：
  - 401/403 → `AUTH`
  - 429 → `RATE_LIMIT`
  - 400 + 上下文超窗 → `CONTEXT_WINDOW_EXCEEDED`，否则 `INVALID_REQUEST`
  - ≥500 → `SERVER`
  - 超时 → `TIMEOUT`、调用方中止 → `ABORTED`、传输失败 → `TRANSPORT`、空响应 → `EMPTY_RESPONSE`
- **`Retry-After` 解析**：`providerRetryAfterMs` 支持数字秒与 HTTP-date
- **请求 ID 透传**：`x-request-id` / `x-deepseek-request-id` → `ProviderRequestId`
- **归属头**：`x-deepseek-harness-user-id`、`x-deepseek-harness-session-id`、`x-deepseek-harness-compact`（压缩请求标记）
- **fetch 错误包装**：裸 `TypeError: fetch failed` 包装为带 endpoint 的 `TRANSPORT` LlmError 并链上 cause，使 `errorChain` 能渲染完整诊断

### 8.3 LlmError 结构化失败

`LlmError` 保留事实（status、providerRetryAfterMs、requestId、cause），任何非 LlmError 压平为 `errorChain` 文本 + `UNKNOWN`。这使压缩循环（compaction）能针对 `CONTEXT_WINDOW_EXCEEDED` 触发自动恢复（见 §14）。

---

## 9. 沙箱体系（sandbox）—— 深度剖析

### 9.1 服务定义（packages/sandbox/sandbox）

```ts
export abstract class SandboxProvider extends Service {
  abstract confine(argv: readonly string[], policy: SandboxPolicy): ConfinedArgv
}
```

- **`SandboxPolicy`**：每调用携带的文件效应策略 `mode: 'read-only' | 'workspace-write' | 'danger-full-access'` + `workspaceRoot` + 可选 `sessionId`
- **`ConfinedArgv`**：被包装的 argv + `enforcement: 'full' | 'partial'` + 该后端的 `denialSignatures` + `runnerFailureRules`
- **fail-closed**：无法强制时抛 `SandboxUnavailableError`（`SANDBOX_UNAVAILABLE`），**静默无约束透传被禁止**

### 9.2 平台 runner 链（packages/sandbox/sandbox-local）

`LocalSandboxProvider.selectRunner()` 按平台/内核探测仲裁多 runner 链：

| runner | 平台 | 机制 |
|---|---|---|
| `bwrap` | Linux | bubblewrap（read-only binds） |
| `landlock` | Linux | Rust addon `@deepseek-ai/node-addon-landlock-run`（`LAUNCHER_BIN`），旧 ABI 部分强制 |
| `seatbelt` | macOS | `sandbox-exec` |
| `windows-acl` | Windows | 受限令牌 runner + 每 workspace 写 SID 授权（`AclWriteGrant`：workspace 级常驻授权 + 每 live session/workspace 私有临时目录可撤销授权） |

关键设计——**拒绝方言（denial dialect）**：

```ts
const DENIAL_SIGNATURES = {
  bwrap: ['read-only file system'],          // EROFS
  landlock: ['permission denied'],           // EACCES
  seatbelt: ['operation not permitted'],     // EPERM
  'windows-acl': ['access is denied', 'access to the path', 'permission denied'],
} as const
```

consumer 从失败运行的 stderr 推断拒绝时，只匹配**该后端实际产生**的方言，而不是跨后端并集——并集会声称后端从未产生的拒绝。

### 9.3 拒绝升级（escalation）

`escalation.ts` 导出 `approveEscalation`、`WIDER_MODES`、`sandboxDenialMarker`、`validateEscalationArgs`：批准的升级重试是**带更宽策略的新调用**，有 `sandbox_permissions` 标记让模型请求沙箱升级（见 §11 审批策略）。

### 9.4 终端后端缝（terminal）

```ts
export interface TerminalBackend {
  readonly type: string
  spawn(spec: TerminalBackendSpawnSpec): Promise<TerminalBackendSession>
}

export interface TerminalBackendSession {
  readonly motd: string
  readonly pid?: number
  startSend(request: TerminalSendRequest): TerminalSendOperation  // 每个 PTY session 同时仅一个活跃 send
  read(request: TerminalReadRequest): TerminalReadResult          // 有界 scrollback 页
  signal(signal: TerminalSignal): Promise<TerminalSignalResult>   // 给验证过的前台进程组发信号
  status(): TerminalSessionStatus
  close(reason: string): Promise<void>                            // 幂等关闭捕获的 owned 进程树
}
```

- `TerminalSignal`：`SIGINT | SIGTERM | SIGKILL | SIGTSTP | SIGHUP`（与 subprocess 缝保持成员一致）
- 后台实现：`BashTerminalBackend`（本地 PTY）、E2B 远程 PTY（`spawnE2BTerminal`：写 runner.bash/environment/argv/output-marker 到远程 state dir，bootstrap 输出过滤，等待就绪标记再发布）
- 唯一活跃 send：`startSend` 返回 `TerminalSendOperation`（`done` promise + `readOutput()` 增量 + `cancel()` 发 SIGINT）

### 9.5 E2B 远程沙箱（e2b 组）

`E2BRuntime.getSandbox()` → 远程沙箱对象，`subprocess-e2b` 在其上实现终端与命令执行。FS 与 subprocess 适配器共享同一远程世界——验证了"一次 provider 切换改变整个产品"。

---

## 10. Web 能力（web 组）

### 10.1 结构

- **`web/web`**：`WebRuntime` 服务 + `WebFetchProvider` 缝 + `mountWeb`/`mountTools`
- **`web/web-fetch-http`**：匿名 HTTP fetch provider（`HttpFetchProvider`）
- **`web/web-search-deepseek` / `web-search-exa` / `web-search-perplexity`**：三个搜索 provider
- **`web/tool-web`**：`web_fetch` 工具 Consumer + HTML→markdown 转换

### 10.2 HttpFetchProvider 健壮性设计

- 上限：`maxUrlLength`、`maxResponseBytes`、`maxBodyChars`、`timeoutMs`、`maxRedirects`、自定义 `User-Agent`
- **重定向策略**：只跟随**同源**重定向；跨源重定向拒绝并提示直接访问该 URL（`WEB_REDIRECT_BLOCKED`）；重定向目标重新过一遍 `validateFetchUrl`（防绕过）
- **内容类型分类**：`classifyContentType` → html/text，不支持类型拒绝（`WEB_UNSUPPORTED_CONTENT_TYPE`）
- **字节上限读取**：`Content-Length` 超限立即拒绝（`WEB_FETCH_TOO_LARGE`）；流式增长超限截断而非拒绝；恰好达到上限不误报 truncated
- **字符集解码**：解析 charset 后选 decoder，解码失败不消费流、先取消 body 防 socket 泄漏
- **HTML→markdown**：turndown 转换；`exceedsConversionDepth` 词法守卫（栈式标签解析）防止 DOM 递归 RangeError；转换失败降级为原始 HTML（"降级的页面优于报错"）；截断页脚 `(Content truncated. Fetch a more specific URL or section for the full text.)`

### 10.3 渲染

`renderBody` 同步处理上限 `maxInputChars`；输出再受 `maxOutputChars` 上限；`WebFetchMeta`（最终 URL/statusCode/truncated）随结果携带，前端展示。

---

## 11. 审批与交互（interaction 组）

### 11.1 ApprovalPolicy

```ts
export type ApprovalPolicy = 'ask' | 'never'
```

- `'ask'`：向 answerer 链（人）发起审批
- `'never'`：确定性拒绝，模型面向句子为 "Approval prompts are disabled in this session: actions that require approval are rejected automatically — do not request sandbox escalation (do not set `sandbox_permissions`)."
- **审批事件**（log-only 审计，非 surface 事件）：`approval/asked`（id + toolName + callId? + reason?）、`approval/decided`（outcome）、`approval/policy`（策略切换；最后一条是 session 覆盖；`source: 'delegation'` 标记注入子代理的覆盖）
- 策略是 **durable、replayable** 的 session event，但**永不进模型 transcript**——模型从 runtime-context snapshot 与 live switch notices 得知策略

### 11.2 权限预设（permission-presets）

`PermissionPresetService`：将策略组合成预设（如 headless 严格模式）。

### 11.3 ask-user 与用户问题

`UserQuestionService.ask(request)`：同步询问人类，用于工具与 plan mode。

---

## 12. 子代理体系（subagent 组）—— 深度剖析

### 12.1 Service Definition

```ts
export interface SubagentProvider {
  readonly capabilities: SubagentCapabilities
  // outputSchema | depthLimit | toolFilter | persona
  readonly inheritsParentContext: boolean
  start(request: ResolvedSubagentStartRequest): SubagentRun
}
```

`SubagentRun` 携带 `id`、`result: Promise<SubagentResult>`（**绝不 reject**——失败压平为 stop reason）、`dispose()`。

### 12.2 10 个 provider 实现（runtime dispatch）

| Provider | 类型 | 说明 |
|---|---|---|
| `AcpProvider` | 进程外 | ACP 子代理（`command` + `args`），`permission: allow/reject` 自动应答子代理的 `session/request_permission`，无提示给人类 |
| `ClaudeCodeProvider` | 进程外 | 驱动 Claude Code（真实产品测试存在） |
| `CodexProvider` | 进程外 | 驱动 Codex CLI |
| `SdkSubagentProvider` | 进程外 | 完整 dsh runtime 子进程，stdio JSON-RPC（`dsh-sdk` client） |
| `ForkInProcessProvider` | 进程内 | fork 子代理 |
| `SpawnInProcessProvider` | 进程内 | spawn 子代理 |
| `ScriptedSubagentProvider` | 测试 | 脚本化 |
| `StubProvider` ×3 | 测试 | 桩 |

**进程外 provider 的关键约定**：
- 每个子进程有自己的进程、session、模型、工具 → **共享零 Cordis 上下文**，不宣称父强制的 start capabilities（`NO_START_CAPABILITIES`：outputSchema/depthLimit/toolFilter/persona 全 false，服务在 `start` 前拒绝需要它们的请求）
- 从 `request.parent.session.header.cwd` 读取工作区 cwd（唯一读父的东西）；无 cwd 则 fail-loud（不回退到服务器进程 cwd——一个服务器进程服务多个 session，各自有 cwd）
- **env 凭据清洗**：子进程 env 是父 env 的凭据清洗副本 + 显式 `env` 覆盖——ambient secrets 不隐式泄漏，显式 key 可达
- **dispose 分级宽限**：`disposeEofGraceMs`（EOF 驱动 quiesce，子进程刷新持久化与嵌套子进程）→ 升级到信号；`disposeGraceMs` 终止确认窗口

### 12.3 委托工具（Consumers）

`tool-subagent` 暴露委托给模型；子代理结果有 stop reason 判别联合（goal completed / delegated / cancelled / errored / …）。

---

## 13. Skill 体系（skill 组）—— 深度剖析

### 13.1 Service Definition（`skill/src/provider.ts`）

```ts
export interface SkillProvider {
  readonly type: string
  list(scope: SkillScope): Promise<SkillListing[]>     // 目录
  load(scope: SkillScope, name: string): Promise<SkillEntry | null>  // 按需加载
  watch?(scope: SkillScope, listener: SkillWatcherListener): () => void  // 可选热重载
}
```

- `list` 返回目录（名称、描述、供应商、id 冲突信息）；`load` 按需取回条目——**目录与内容分离，避免全部加载**
- `watch` 可选：文件系统变更时热重载（本地 provider 实现，用于迭代开发）
- `SkillWatcherListener`：`{ type: 'changed' | 'deleted'; name: string; description?: string }`

### 13.2 本地实现（`skill-local`）

`FileSystemSkillProvider` 的**根目录发现顺序**（同 id 冲突时靠前优先）：

```text
1. <session-root>/.dsh/skills/         # 会话根目录（默认 workspace 根）
2. <session-root>/.agents/skills/      # 会话根目录（Claude Code 兼容）
3. <user-home>/.dsh/skills/            # 用户级
4. <bundled>/skills/                   # 随 dsh 分发的内置 skills
```

- 多目录挂载顺序与优先级可配置；`validateSkillMeta` 校验 SKILL.md 结构（`YAML front matter` 要求 `name` 必填）
- `load` 解析 SKILL.md 的 front matter + 描述 + body；不存在的技能返回 `null`，由上层生成"未找到"错误
- `resolveSkillRoots` 组装根目录列表；目录不存在则跳过

### 13.3 工具层（`tool-skill-catalog` / `tool-skill-loader`）

- **`tool-skill-catalog`**：`skill_catalog` 工具——列出可用 skills，**变更感知**（skill 目录变化时重新发布 catalog，不重复）
- **`tool-skill-loader`**：`skill_loader` 工具——按名称加载技能内容到模型上下文；支持 `path` 或 `name` 解析；防重复加载（同 id 已加载则返回已加载状态）

### 13.4 与 CScode 的对照

CScode 已有 `agent-skills`（CLAUDE.md / GEMINI.md / cursor-setup 等用户级 skill 文档），但**没有系统化的技能目录发现与按需加载机制**。dsh 的 `SkillProvider.list/load/watch` 三方法契约 + 根目录发现顺序是可移植的成熟设计。

---

## 14. Compaction（压缩）与 Token 管理

### 14.1 组织

- **`compaction/compaction`**：Service Definition（`CompactionService`）+ 压缩请求类型
- **`compaction/compaction-basic`**：基础实现——region summarization + token-meter 预算
- **`compaction/tool-result-pruner`**：工具结果裁剪插件
- **`compaction/command-compact`**：人类命令触发的压缩
- **`llm/token-meter`**：token 计量（`TokenMeter`）

### 14.2 基本压缩引擎（`compaction-basic/src/index.ts`）

`BasicCompactionEngine` 的核心循环（`engine.ts`）：

```ts
// 核心算法骨架（精简）
async compact(request: CompactionRequest): Promise<CompactionResult> {
  const tokenMeter = this.tokenMeter(request.tokens)   // 按目标模型解析 TokenMeter
  // 1. 估算当前上下文 token 使用（从 session 日志）
  // 2. 从后向前遍历 region，累积摘要直到达到 token 预算
  // 3. 摘要不可用时，从较早 region 开始裁剪工具结果（tool-result-pruner）
  // 4. 生成压缩消息（summarized regions 替换原文）
}
```

- **region**：会话日志的分段单位（如若干 turn / 若干消息）；每个 region 可缓存其摘要
- **token-meter**：跨模型解析 token 计数（不同模型 contextWindow 不同）；`TokenMeter` 负责计费/计量
- **摘要优先、裁剪兜底**：预算不足时先尝试摘要较早 region，摘要不可用则裁剪工具结果，最后才是丢弃
- **上下文溢出自动恢复**：`CONTEXT_WINDOW_EXCEEDED` LlmError 触发压缩循环（`loop-hygiene` guard 插件监听），压缩后重试

### 14.3 Tool-result-pruner

`tool-result-pruner`：对超预算的工具结果做**降级保留**——保留调用参数与结果元数据（code/message/retryable），裁剪长文本 body。被裁剪结果标记 `truncated: true`，模型仍能看到工具调用结构。

---

## 15. Workflow（workflow 组）

### 15.1 Service Definition（`workflow/src/provider.ts`）

```ts
export interface WorkflowProvider {
  readonly capabilities: WorkflowCapabilities
  start(request: ResolvedWorkflowStartRequest): WorkflowRun
}
```

### 15.2 worker-thread 实现（`workflow-worker-thread`）

在 **worker_threads + vm 沙箱** 内运行 workflow 脚本，隔离主线程：

```ts
// runtime.ts 关键结构
const context = vm.createContext({ ... })
const agentFn = ...      // workflow 内可调用的 agent 函数
const parallelFn = ...   // 并行执行多个 agent
const pipelineFn = ...   // 管道组合
const phaseFn = ...      // 阶段标记
const logFn = ...        // 日志
```

- 组合子：`agent()` / `parallel()` / `pipeline()` / `phase()` / `log()`
- 上限：`maxConcurrentAgents`、`maxTotalAgents`、`maxItemsPerCall`（防资源耗尽）
- worker-thread 隔离：workflow 脚本运行在 worker 线程的 vm 沙箱中，崩溃不影响主进程；主线程通过消息通道与 worker 通信
- `tool-workflow`：`workflow` 工具暴露给模型执行 workflow

---

## 16. Settings / Credentials / Boot / API

### 16.1 Settings（`settings/settings` + `settings-file`）

- **`SettingsScopeController`**：作用域设置控制器（session scope 覆盖 user scope 覆盖 default）
- **revision-fenced 写**：设置写入带 revision 校验，防止并发覆盖（乐观并发控制）
- `settings-file`：文件后端（`settings.yaml`）

### 16.2 Credentials（`credentials/credentials` + `credentials-env`）

- **`CredentialReference`**：`credential-reference` 能力——`{ type: 'env', name: 'ANTHROPIC_API_KEY' }` 等引用
- 凭据解析不落盘、不进日志；provider 从引用解析实际密钥（见 §8.2 快照一致性）

### 16.3 Boot（`boot/app-boot`）

`app-boot` 共享胶水：profile 解析、bundle 层组合、`cordis.patch.yml` 应用、headless one-shot 驱动器（`--profile headless --prompt "..."` 单次运行）。`headless` 是内置 profile 模板，权限预设为严格模式。

### 16.4 SDK / API / Typert

- **`sdk/`**：JSON-RPC 协议 + 服务器 + TypeScript 客户端（`dsh-sdk`）
- **`api/`**：Remote BFF 组装 + Typert RPC 网关（类型图生成器 → loader → 运行时注册表）
- **`typert/`**：类型图生成器——把 TypeScript 类型生成可序列化的类型图，跨进程传递类型安全的 RPC

---

## 17. Python SDK（python/sdk）

### 17.1 结构

```
python/sdk/src/deepseek_harness/
  models/     # pydantic 模型（SessionConfig, RunResult, Message, ToolCall...）
  client.py   # DeepSeekHarness 客户端（session 管理）
  session.py  # Session 封装（prompt/ask/tools 注册）
  api/        # 低级 JSON-RPC 传输（stdio）
  errors.py   # HarnessError 层次
```

### 17.2 核心用法

```python
from deepseek_harness import DeepSeekHarness, SessionConfig

harness = DeepSeekHarness()                       # 启动 dsh runtime 子进程
session = harness.create_session(SessionConfig(...))
result = session.prompt("Hello")                  # 同步/异步 prompt
# result: RunResult（含消息历史、usage、stop reason）
```

- **JSON-RPC over stdio**：与 `dsh-sdk` 同一协议——Python 与 TS 客户端可互换
- pydantic 模型层：类型安全的请求/响应；`errors.py` 提供 `HarnessError` 层次（协议错误、运行时错误、会话错误）
- `sdk-runtime/`：Python 运行时（构建/打包 Python 依赖）

---

## 18. Native Landlock（native/landlock-run）

- **Rust node addon**（`@deepseek-ai/node-addon-landlock-run`），Linux-only
- 机制：`landlock` LSM 限制进程的文件系统访问（read-only binds / workspace-write）
- 按平台分包：`packages/{entry,linux-x64,linux-arm64}`（node-gyp / napi 平台包）
- 失败约定：`LAUNCHER_FAILURE_EXIT = 125`（launcher 失败退出码，与 argv 包装结果区分）
- 消费方：`sandbox-local` 的 `landlock` runner（`LAUNCHER_BIN` 环境变量定位二进制）

---

## 19. 对 CScode 的迁移建议（能力映射表）

> CScode 现状：Python 后端（FastAPI + Textual TUI + SQLite Event Sourcing + SessionV2/EventStore）、React 18 前端、Tauri v2 桌面端、mcp-websearch、PTY 系统、workspace/sync/session 系统。

| # | dsh 能力 | CScode 现状 | 迁移建议 | 优先级 |
|---|---|---|---|---|
| 1 | **Append-only SessionEvent 日志 + deriveMessages 投影** | SessionV2 EventStore（事件溯源） | 已对齐；补 `assistant/chunk` 保真重放与 fork | 高 |
| 2 | **ContextForm 语义化上下文词汇**（instructions/catalog/snapshot/notice/relay/recall） | `build_context()` 手动注入 system message | 引入 ContextForm 判别联合，让上下文有语义而非视觉 | 高 |
| 3 | **Compaction + TokenMeter + CONTEXT_WINDOW_EXCEEDED 自动恢复** | `check_overflow()` 仅计数消息（阈值 100） | 引入 token 计量 + region 摘要 + 溢出自动压缩 | 高 |
| 4 | **Capability Seam 三角色**（Definition/Provider/Consumer） | 模块直接耦合 | 沙箱/搜索/子代理/终端抽接口，一个 provider 切换改变产品 | 高 |
| 5 | **LlmError 错误码规范化**（AUTH/RATE_LIMIT/CONTEXT_WINDOW_EXCEEDED/... + Retry-After + 请求 ID 透传） | 异常处理分散 | 统一结构化 LLM 错误层次 + 快照一致性凭据 | 高 |
| 6 | **Sandbox 分层 runner 链 + fail-closed + denial dialect** | 无沙箱（本地直跑） | 先 landlock（Linux）/seatbelt（macOS）runner；CScode 是 Tauri+Rust，可直接复用 landlock-run 模式 | 高 |
| 7 | **SkillProvider list/load/watch 契约 + 根目录发现** | agent-skills 为静态文档 | 系统化技能目录 + 按需加载 + skill_catalog/skill_loader 工具 | 中 |
| 8 | **SubagentProvider 10 实现 + env 凭据清洗 + NO_START_CAPABILITIES** | 委托机制简单 | 进程外子代理 + 凭据清洗 + dispose 分级宽限 | 中 |
| 9 | **ApprovalPolicy durable session event（永不进 transcript）** | 权限确认流（APPLICATION_TOOLS） | 审批策略做成 durable/replayable 事件，从 runtime snapshot 得知 | 中 |
| 10 | **Tool guard 管线（pre/execute/post-execute 瀑布）** | 权限确认在调用点 | 引入瀑布守卫，拦截/审计/策略解耦 | 中 |
| 11 | **Workflow 组合子（agent/parallel/pipeline/phase）在 vm 沙箱** | 无 | Python 用 `asyncio.gather` + 受限子进程实现 parallel/agent 组合 | 中 |
| 12 | **HttpFetchProvider 重定向/字节上限/降级 HTML→markdown** | websearch 工具存在 | 移植同源重定向 + 字节上限 + turndown 降级 | 中 |
| 13 | **TerminalBackend 缝（唯一活跃 send + 有界 scrollback）** | PTY 系统已有 | 对齐 send/signal/close 契约；CScode PTY 有 ratchet 规则需保留 | 低 |
| 14 | **Profile/Bundle 分层配置 + patch 按行 id 覆盖** | 无 profile 概念 | 引入配置层组合，用户 patch 覆盖默认 | 低 |
| 15 | **Settings revision-fenced 写** | Config 简单读写 | 乐观并发控制防覆盖 | 低 |
| 16 | **LSP 能力 + hooks 桥（Claude Code/Codex hook）** | 无 | 二期：hook 兼容层让 CScode 复用 Claude Code 生态 | 低 |

### 19.1 迁移原则（Ratchet 视角）

1. **接口契约优先**：每个迁移先定义 Service Definition + Provider + Consumer 三角色接口，再写实现
2. **分层独立**：Schema → LLM → Core → App，禁止跨层 import（对齐 CScode 已有分层规则）
3. **TDD 先行**：先写契约测试（provider 可替换性测试），再写实现
4. **Ratchet**：每次迁移的边界情况（超时、重试、拒绝方言）转化为 AGENTS.md 规则 + 测试

### 19.2 关键坑位提醒（迁移时）

- **landlock-run 是 Rust**：CScode 桌面端是 Tauri+Rust，可直接在 `desktop/src-tauri` 内实现 sandbox runner，无需 node addon 桥
- **LLM 流式 idle watchdog**：CScode 的 LLM 调用若没有空闲超时，长连接挂死会耗尽连接池——移植 `idleWatchdog`
- **凭据快照一致性**：CScode 的 API key 解析若在流中途读取配置，可能端点半途切换——必须冻结快照
- **compaction 的摘要缓存**：region 摘要缓存避免重复 LLM 调用——CScode 的 overflow 检测目前是纯计数，升级后需 token 预算
- **skill 根目录 `.agents/skills`**：CScode 桌面端内置 skills 应放 bundled 目录，用户级放 `~/.cscode/skills`

---

## 20. 总结

DeepSeek Harness 最值得 CScode 借鉴的五件事：

1. **追加式会话事件日志作为唯一事实来源**（模型可见输入 ⟺ 日志可重建）——CScode 已有 EventStore 基础，差距在"模型历史投影"与"chunk 保真重放"
2. **Capability Seam 三角色**——把沙箱/搜索/子代理/终端全部抽成 Definition/Provider/Consumer，一次 provider 切换改变整个产品
3. **结构化错误 + 自动恢复**——LlmError 错误码（CONTEXT_WINDOW_EXCEEDED 触发 compaction 循环）把"出错"变成"可恢复的循环"
4. **健壮性细节**——同源重定向、字节上限、idle watchdog、凭据快照一致性、denial dialect，全部是可移植的工程经验
5. **可组合的配置层**——Profile/Bundle/patch 分层，让产品能力按层组合、用户可 patch 任意行

迁移路线建议：**先做 1/2/3（事件投影 + 能力缝 + 压缩恢复）**，这三项是架构级差距；4/5 随后跟进；其余按优先级列表逐项落地。
