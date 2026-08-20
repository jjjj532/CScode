# CScode Capability Seams（能力缝）— 三角色决策表

> 版本：0.4.0 · 更新：2026-08-20（迭代 9，G-10）
> 来源：`docs/deepseek-harness-analysis.md` §6（dsh 分析）→ 本文为 **CScode 落地版**，所有路径引用真实源码
> 关联 spec：`openspec/specs/cscode-iteration-upgrade.md` §6.4

---

## 1. 三角色模型

**Seam（能力缝）= Service Definition + Service Provider + Consumer**。一个包可兼多角色，但单一角色不构成缝；添加能力 = 设计全部三个角色。

- **Service Definition**：声明接口（如 `SandboxRunner`、`ToolRegistry`、`LSPManager`）
- **Service Provider**：实现接口（如 `sandbox/limits.py` 执行限制、16 个 `providers/*.py`）
- **Consumer**：使用服务，通常是模型面向工具（如 `tools2/read.py`、`tools2/bash.py`）

**缝的关键价值**：一次 provider 切换改变整个产品。文件系统与子进程 provider 共享执行世界，把二者指向远程沙箱（E2B），Bash、PTY、LSP 随之一同迁移。

---

## 2. "新行为放哪里"速查表

> 每行目标 → 机制，均引用真实源码路径（`rg` 可验证）。

| 目标 | 机制 | 源码证据 |
|---|---|---|
| 添加模型 provider | 在 `providers/` 新增文件并注册到 `providers/base.py` 协议 | `src/cscode/providers/`（16 个：anthropic/azure/gemini/ollama/openai/openrouter/grok/mistral/nvidia/vertex/xai/bedrock/cohere/copilot/perplexity） |
| 添加模型面向能力（工具） | 在 `tools2/` 新增工具类，`ToolRegistry.register()` 注册 | `src/cscode/tools2/registry.py` + `src/cscode/tools2/*.py`（20 个工具类：ls/lsp/output_store/glob/edit/bash/browser/websearch/task/write/todowrite/read/grep/truncate/skill/apply_patch/pty/question/webfetch/plan） |
| 给某个 session 不同能力集 | 组合 agent preset | `src/cscode/core/agent/registry.py` + `build.py` + `factory.py` |
| 添加 shell 执行 | 注册 bash 工具（spawn 前经沙箱包装 argv） | `src/cscode/tools2/bash.py` + `src/cscode/sandbox/runner.py` |
| 添加持久终端执行 | 注册 PTY 工具 | `src/cscode/tools2/pty.py`（PTYAction/PTYCreateOutput 等） |
| 添加人类命令 | `CommandRegistry.register()` 注册（TUI 命令分发） | `src/cscode/tui/commands.py` + `src/cscode/tui/plugin_api.py`（G-6） |
| 添加后台工作 | `JobStore.add()` 登记异步任务 | `src/cscode/core/background_job.py` |
| 添加文件系统访问/策略 | 扩展 `fs_protected.py` ProtectedPaths 或 `fs_ignore.py` 规则 | `src/cscode/core/fs_protected.py` + `src/cscode/core/fs_ignore.py` |
| 限制 spawned 进程 | `SandboxRunner.run()`（limits/diagnostics/result） | `src/cscode/sandbox/runner.py` + `limits.py`（G-4 路线 B） |
| 拦截请求/工具/turn | 事件系统（PermissionAsked/PermissionRepliedEvent）+ PermissionV2 三态 | `src/cscode/core/events.py` + `src/cscode/core/permission_v2.py`（G-7） |
| 添加模型面向上下文 | 会话消息追加（SessionV2 事件溯源） | `src/cscode/core/session_v2.py` |
| 添加持久 session 状态 | 扩展事件类型（EventStore 事件溯源） | `src/cscode/core/events.py` + `src/cscode/storage/event_store.py` |
| Fork 活跃 session | **预留**：依赖 G-9 `sync.status === "complete"` 检查点，前端/后端当前均无 fork 实现（`rg fork` 零命中） | `src/cscode/web/src/hooks/useSync.ts`（状态机已就绪） |
| 多设备同步 | SyncEngine 推送/拉取增量事件 | `src/cscode/core/sync.py` + `src/cscode/server/app.py:2542,2562`（/api/sync/events + /api/sync/push） |
| 语言服务 | LSPManager 检测语言 + LSPClient 连接 | `src/cscode/lsp/manager.py` + `src/cscode/tools2/lsp.py` |
| 子代理 | SubAgentOrchestrator 处理 @mention 委托 | `src/cscode/core/sub_agent.py` + `src/cscode/core/agent/subagent.py` |

---

## 3. 缝清单（Definition / Provider / Consumer 实证）

| 缝 | Service Definition | Service Provider | Consumer |
|---|---|---|---|
| 沙箱 | `sandbox/runner.py` `SandboxRunner.run()` | `sandbox/limits.py` ExecutionLimits + `runner.py` 超时/输出上限 | `tools2/bash.py` spawn 前包装 argv |
| 工具系统 | `tools2/registry.py` `ToolRegistry.register()` | 20 个 `tools2/*.py` 工具类 | `llm/tool_runtime.py` + `core/tool_registry.py` |
| Agent preset | `core/agent/registry.py` | `core/agent/base.py` + `build.py` + `factory.py` | `app/` agent 工厂 |
| TUI 命令 | `tui/commands.py` `CommandRegistry.register()` | `tui/plugin_api.py` TuiPluginAPI | `server/app.py` `_handle_session_command` |
| 后台任务 | `core/background_job.py` JobStore | `core/background_job.py` Job 模型 | TUI 任务面板 / 前端 |
| 事件/权限 | `core/events.py` PermissionAsked/RepliedEvent | `core/permission_v2.py` PermissionV2（once/always/reject） | `tools2/` 工具权限确认 |
| Provider | `providers/base.py` 协议 | 16 个 `providers/*.py` | `llm/route.py` + `llm/client.py` |
| 文件系统 | `core/fs_protected.py` ProtectedPaths + `core/fs_ignore.py` | `core/fs_watcher.py` | `tools2/read.py` / `write.py` / `grep.py` / `glob.py` |
| 终端 | `tools2/pty.py` PTYAction/PTYInput/PTYCreateOutput | `tools2/pty.py` PTY 后端 | TUI 终端面板 |
| LSP | `lsp/manager.py` LSPManager | `lsp/manager.py` LSPClient | `tools2/lsp.py` |
| Sub-agent | `core/sub_agent.py` SubAgentOrchestrator | `core/agent/subagent.py` | `core/runner.py` 会话调度 |
| 同步 | `core/sync.py` SyncEngine | `server/app.py:2542,2562` /api/sync/* 端点 | `web/src/hooks/useSync.ts`（G-9 状态机） |

---

## 4. 与 dsh 的差异（Ratchet 记录）

| 差异 | dsh（opencode 分析） | CScode 实际 |
|---|---|---|
| Fork session | `ctx.sessions.fork(source, boundary?, childSessionId?)` | **不存在**（前后端零命中）；预留：依赖 G-9 `sync.status` 检查点 |
| Provider 数量 | 30+（含 alibaba/anthropic/azure/bedrock/cohere/grok/mistral/nvidia/openrouter/perplexity/vertex/xai…） | 16 个（已扩至 anthropic/azure/gemini/ollama/openai/openrouter/grok/mistral/nvidia/vertex/xai/bedrock/cohere/copilot/perplexity + base） |
| 权限事件流 | EventPermissionAsked / EventPermissionReplied | `core/events.py` PermissionAsked/RepliedEvent + `core/permission_v2.py`（G-7 三态 once/always/reject） |
| 沙箱 | `ctx.sandbox` 后端 | `sandbox/runner.py` SandboxRunner（G-4 路线 B：limits + diagnostics + result） |

---

## 5. 维护约定（Ratchet）

1. **新增能力时**：先查本表"目标 → 机制"定位缝，再决定 Definition/Provider/Consumer 归属
2. **新增缝时**：必须补齐三列源码引用（缺一列不构成缝）
3. **本表路径变更时**：同步更新（`rg` 验证失效即更新）