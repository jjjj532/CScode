# CScode ↔ OpenCode 1:1 功能对齐差距分析报告

> 生成时间：2026-07-04（基于最新 CScode 源码全面重新核对）
> 分析基准：OpenCode 源码（`/Users/mac/AI/CScode/github/opencode-full`，25+ packages）
> 分析对象：CScode 源码（`/Users/mac/AI/CScode/src/cscode`，单 Python 包 + Tauri 桌面端）
> 对照文档：`docs/opencode-analysis/source-analysis.md`、`docs/technical-specification.md`
> 任务范围：**仅做 1:1 功能差距对比，不写代码**
> 验证方法：逐文件核对 `src/cscode/` 下 20+ 子包 + 70+ 测试文件

---

## 0. 总体差距概览

| 维度 | OpenCode | CScode | 覆盖率 |
|------|----------|--------|--------|
| Packages 数量 | 25+（app/cli/core/opencode/protocol/schema/sdk/server/tui/ui/desktop/plugin/llm…） | 1（monorepo src/cscode + desktop/） | — |
| 核心子包/模块 | ~50 个顶层模块 | 21 个子包（acp/app/auth/enterprise/git/llm/lsp/mcp/plugins/providers/schema/server/sharing/skills/storage/tools/tools2/tui/utils/web） | — |
| API 端点 | ~60 个（18 个 protocol group + 21 个 instance group） | 28 个等价端点 + session 单数别名 | ~47% |
| 工具数量 | 18+（含 lsp/plan/task/skill/apply_patch/question） | 18 个（tools2/ 下 18 个实际工具） | ~90% |
| Provider 数量 | 30+（plugin/provider/ 下含 alibaba/anthropic/azure/bedrock/cohere/grok/mistral/nvidia/openrouter/perplexity/vertex/xai…） | 7（anthropic/azure/gemini/ollama/openai/openrouter + base） | ~23% |
| 事件系统 | EventStore + Projector + v2 schema + PublicEventManifest | EventStore + Projector + Compactor + EventSourcing + SSE streaming | ~75% |
| 前端组件 | React 18 + 18 国语言 + 桌面 + Web + TUI + 独立 ui 包 | React 18 + 20+ 组件 + 单语 + 桌面(Tauri) + TUI(Textual) | ~50% |
| 测试覆盖 | — | 70+ 测试文件（pytest + Playwright + Jest） | — |
| **整体功能覆盖率** | — | — | **约 42%–50%** |

### 已对齐 / 已实现的系统（25 个）

1. **Session V2 事件溯源** — SessionV2 + EventStore + SessionProjector + SessionCoordinator + SessionRunner
2. **Tool 系统（基础）** — 18 个工具（bash/read/write/edit/glob/grep/apply_patch/question/todowrite/webfetch/websearch/skill/truncate/plan/task/ls/browser/output_store）
3. **Compaction 系统** — Compactor + ContextCompressor + context_epochs 表 + compact API
4. **Permission V2 系统** — PermissionV2 + Wildcard + Ruleset + SavedRules（数据库持久化）+ CRUD API
5. **Config V2 系统** — 结构化多层配置（7 个子配置 + 6 层合并：默认/全局/项目/本地opencode/数据库/CLI）
6. **Question 系统** — QuestionRegistry + question 工具 + questions API（list/reply/reject + always_allow）
7. **LSP Manager** — LSPManager + LSPClient（支持 Python/TypeScript/JavaScript/Go/Rust/Ruby/Java/PHP 8 种语言）
8. **MCP 系统** — MCPClient + MCPServer + mcp 配置
9. **Plugin 系统（基础）** — PluginLoader + PluginManifest + Hooks + SDK
10. **Skill 系统（基础）** — SkillLoader + discover + skill 工具
11. **Sharing 系统（基础）** — ShareManager + links + serializer
12. **Event 系统** — EventStore + Projector + LLMEvent schema + SSE streaming + subscribe
13. **Database 系统** — aiosqlite + MigrationRegistry + MigrationRunner（5 个 migration）
14. **Agent V2** — AgentV2 + AgentFactory + SubAgentOrchestrator
15. **LLM 层** — LLMClient + ToolRuntime + route + adapters + protocols（OpenAI/Anthropic）
16. **Task Tracker** — TaskTracker + task_verifications 表 + expected_tasks 表
17. **Git 工具** — git/diff + git/review + git/snapshot
18. **Enterprise 模块** — audit + policies + remote_config
19. **Auth 模块** — tokens + github + openai_oauth
20. **ACP 协议** — acp/protocol
21. **Schema 层** — events/messages/options/tool/ids/errors（6 个 schema 模块）
22. **Images 模块** — core/images.py（图像处理）
23. **Structured 输出** — core/structured.py（结构化输出支持）
24. **Container 模式** — core/container.py（依赖注入容器）
25. **Config Variable** — config_variable.py + config_scanner.py（配置变量解析 + 扫描）

### 完全缺失的系统（CScode 未实现，16 个）

1. **PTY 系统**（伪终端、长时会话、共享 PTY、PTY ticket）
2. **Integration 系统**（IDE/WebSocket 集成、外部客户端连接）
3. **Credential 系统**（独立凭证存储、OAuth 令牌管理、凭证 CRUD API）
4. **Project / Workspace 系统**（多项目管理、workspace 隔离、project-copy）
5. **Revert 系统**（会话回滚、消息撤销、revert API）
6. **Control-Plane 系统**（move-session、workspace adapter、worktree）
7. **Sync 系统**（多设备同步、共享会话状态）
8. **Account 系统**（账户管理、SQL 持久化）
9. **Background Job 系统**（异步任务调度）
10. **Policy / Reference 系统**（策略管理、上下文引用增强、reference guidance）
11. **Observability 系统**（OTLP 上报、结构化日志）
12. **NPM 集成**（npm 包发现、安装、配置）
13. **GitHub Copilot 深度集成**（copilot-provider 全套 chat + responses）
14. **Catalog 系统**（model/provider/agent 目录服务）
15. **Installation / Version 管理**
16. **Repository Cache**（仓库缓存层）

### 部分缺失的系统（CScode 已实现但功能不完整，14 个）

1. **Session 系统** — 缺 revert、input-inbox、run-state、message-updater、summary、history、info、reminders、retry、overflow、instruction
2. **Tool 系统** — 缺 lsp 工具、http-body 工具、application-tools、external-directory、mcp-websearch
3. **Permission 系统** — 缺 policy 深度联动、session 级 saved permission（目前是全局内存存储）
4. **Config 系统** — 缺 attachments、experimental、formatter、markdown、tool-output、watcher、lsp、reference、tui-cwd、tui-host-attention
5. **Filesystem 系统** — 缺 ignore 规则、protected 路径、watcher、fff 抽象层
6. **Agent 系统** — 缺 prompt 模板库（15+ 个 prompt hardcode）、subagent-permissions、plugin agent
7. **LLM 系统** — 缺 cache-policy、record、auth route、native-request/runtime、aisdk
8. **MCP 系统** — 缺 oauth-callback、oauth-provider、catalog
9. **LSP 系统** — 缺 diagnostic、language、launch、server 完整生命周期、lsp 工具封装
10. **Plugin 系统** — 缺 plugin/provider/（30+ 内置 provider 插件）、command 模板、agent、skill、tui
11. **Sharing 系统** — 缺 share-next、持久化（目前内存）、完整分享 schema
12. **Skill 系统** — 缺 guidance、config、plugin skill
13. **TUI 系统** — 缺 routes、prompt、plugin slots、scrollback、kv、attention、audio、clipboard、editor-zed
14. **Provider 系统** — 缺 23+ 个 provider、catalog、models-dev、model-status

---

## 1. 架构层对比

### OpenCode 5 层架构

```
schema → llm → core → opencode → protocol/server/sdk/tui/app/desktop/cli
```

| 层 | 职责 | 关键文件 |
|----|------|---------|
| schema | 类型定义、Schema 编码 | `packages/schema/src/*.ts` |
| llm | LLM 调用、工具运行时、缓存策略 | `packages/llm/src/llm.ts`、`provider.ts`、`tool-runtime.ts` |
| core | 业务核心（session/tool/permission/config/pty/credential/project/filesystem/integration/plugin/event/database/skill） | `packages/core/src/*.ts` |
| opencode | 应用层（agent/cli/server/session/tool/lsp/mcp/plugin/skill/share/sync/control-plane/worktree） | `packages/opencode/src/*.ts` |
| protocol | API 契约（HttpApiGroup、OpenAPI 注解） | `packages/protocol/src/groups/*.ts` |

### CScode 4 层架构

```
schema → llm → core → app+server+web
```

| 层 | 职责 | 关键文件 |
|----|------|---------|
| schema | events/messages/options/tool/ids/errors | `src/cscode/schema/*.py`（6 个模块） |
| llm | client/route/service/tool_runtime/adapters/protocols | `src/cscode/llm/*.py`（7 个模块） |
| core | config/container/coordinator/compression/events/messages/permission_v2/runner/session/tool_registry/tracker/sub_agent/tui_sessions/images/structured/config_scanner/config_variable/errors | `src/cscode/core/*.py`（19 个模块） |
| app + server + web | agent/factory + app/compactor/projector/question_registry + React 前端 | `src/cscode/app/*.py`、`src/cscode/server/*.py`、`src/cscode/web/` |

### 差距分析

- **架构层级基本对齐**，但 OpenCode 把 `opencode` 包独立成应用层，CScode 把应用层逻辑混在 `app/`、`server/` 和顶层目录
- **OpenCode 单独的 protocol 包**（HttpApiGroup + OpenAPI 注解）CScode 没有等价物，CScode 的 API 是 FastAPI 直接定义路由
- **OpenCode 的 sdk/sdk-next/client 包**（HTTP 客户端、SDK 生成）CScode 没有
- **OpenCode 的 ui/tui/app/desktop 是独立的 4 个前端包**，CScode 只有 `web/`（React）+ `tui/`（Textual）+ `desktop/`（Tauri），架构更扁平
- **CScode 的分层更扁平**，core 层承担了 OpenCode core + opencode 两层的部分职责
- **CScode 多了企业版模块**（enterprise/）和认证模块（auth/），OpenCode 是独立 npm 包

---

## 2. 20 个核心模块逐项对比

### 2.1 Session 系统

| 子功能 | OpenCode | CScode | 状态 |
|-------|----------|--------|------|
| 会话创建/列表/删除 | `core/session.ts` + `protocol/groups/session.ts` | `core/session.py` + `server/app.py` | ✅ 已对齐 |
| 会话消息存储 | `core/session/message.ts` + `core/session/sql.ts` | `storage/event_store.py` + `core/session.py` | ✅ 已对齐 |
| 会话投影 | `core/session/projector.ts` + `core/session/store.ts` | `core/session.py` SessionProjector + `server/projector.py` | ✅ 已对齐 |
| **会话 Compaction** | `core/session/compaction.ts` + `agent/prompt/compaction.txt` | `server/compactor.py` + `core/compression.py` + context_epochs 表 + `/compact` API | ✅ 已对齐 |
| **Context Epoch** | `core/session/context-epoch.ts` | `server/compactor.py` 中 context_epochs 表 | ✅ 已对齐 |
| **会话 Metadata** | `core/session/sql.ts` metadata 字段 | `SessionV2.update_metadata()`（title/model/agent） | ✅ 已对齐 |
| **会话 Status** | `core/session/status.ts` | `SessionState.status`（active/deleted） | ✅ 已对齐 |
| **会话协调器** | `core/session/run-coordinator.ts` | `core/coordinator.py` SessionCoordinator（IDLE/DRAINING/QUEUED） | ✅ 已对齐 |
| **会话 Runner** | `core/session/runner/`（llm/max-steps/model） | `core/runner.py` SessionRunner | ✅ 已对齐 |
| **会话 Event** | `core/session/event.ts` | `core/events.py` + `schema/events.py` | ✅ 已对齐 |
| **会话输入** | `core/session/input.ts`（event_sourced） | `SessionV2.prompt()`（单条输入） | ⚠️ 部分 |
| 会话信息（Info） | `core/session/info.ts` | ❌ 无独立 info 模块 | 缺失 |
| 会话历史 | `core/session/history.ts` | ❌ 无 | 缺失 |
| **会话 Revert** | `core/session/revert.ts` + `schema/revert.ts` | ❌ 完全无 | **缺失** |
| **会话 Run State** | `core/session/run-state.ts` | `core/tracker.py`（部分，task tracker） | ⚠️ 部分 |
| **会话 Message Updater** | `core/session/message-updater.ts` | ❌ 无 | **缺失** |
| 会话 Todo | `core/session/todo.ts` | `tools2/todowrite.py`（仅工具） | ⚠️ 部分 |
| 会话 Error | `core/session/error.ts` | `core/errors.py`（通用） | ⚠️ 部分 |
| 会话 Share | `core/share/sql.ts` + `opencode/src/share/` | `sharing/manager.py`（内存存储） | ⚠️ 部分 |
| 会话 Sync | `opencode/src/sync/` | ❌ 完全无 | **缺失** |
| 会话 Summary | `core/session/summary.ts` + `agent/prompt/summary.txt` | ❌ 无 | 缺失 |
| 会话 System Prompt | `core/session/system.ts` | `_build_system_prompt()`（hardcode） | ⚠️ 部分 |
| 会话 Reminders | `core/session/reminders.ts` | ❌ 无 | 缺失 |
| 会话 Retry | `core/session/retry.ts` | ❌ 无 | 缺失 |
| 会话 Overflow | `core/session/overflow.ts` | ❌ 无 | 缺失 |
| 会话 Instruction | `core/session/instruction.ts` | ❌ 无 | 缺失 |
| 会话导入/导出 | — | `/export` + `/import` API | CScode 多出 |

**结论：Session 系统覆盖率约 55%**，基础 CRUD + 事件存储 + compaction + coordinator + runner 已对齐，缺 revert/message-updater/summary/history/info 等高级功能。

---

### 2.2 Tool 系统

| 工具 | OpenCode | CScode | 状态 |
|------|----------|--------|------|
| bash / shell | `core/tool/bash.ts` + `opencode/src/tool/shell.ts` + `shell/` 子目录 | `tools2/bash.py` | ✅ |
| read | `core/tool/read.ts` + `opencode/src/tool/read.ts` | `tools2/read.py` | ✅ |
| write | `core/tool/write.ts` + `opencode/src/tool/write.ts` | `tools2/write.py` | ✅ |
| edit | `core/tool/edit.ts` + `opencode/src/tool/edit.ts` | `tools2/edit.py` | ✅ |
| glob | `core/tool/glob.ts` + `opencode/src/tool/glob.ts` | `tools2/glob.py` | ✅ |
| grep | `core/tool/grep.ts` + `opencode/src/tool/grep.ts` | `tools2/grep.py` | ✅ |
| apply_patch | `core/tool/apply-patch.ts` + `opencode/src/tool/apply_patch.ts` | `tools2/apply_patch.py` | ✅ |
| question | `core/tool/question.ts` + `opencode/src/tool/question.ts` | `tools2/question.py` | ✅ |
| todowrite | `core/tool/todowrite.ts` + `opencode/src/tool/todo.ts` | `tools2/todowrite.py` | ✅ |
| webfetch | `core/tool/webfetch.ts` + `opencode/src/tool/webfetch.ts` | `tools2/webfetch.py` | ✅ |
| websearch | `core/tool/websearch.ts` + `opencode/src/tool/websearch.ts` | `tools2/websearch.py` | ✅ |
| skill | `core/tool/skill.ts` + `opencode/src/tool/skill.ts` | `tools2/skill.py` | ✅ |
| truncate | `opencode/src/tool/truncate.ts` + `truncation-dir.ts` | `tools2/truncate.py` | ✅ |
| **plan** | `opencode/src/tool/plan.ts` + plan-enter/exit.txt | `tools2/plan.py` PlanTool | ✅ |
| **task** | `opencode/src/tool/task.ts` + task.txt | `tools2/task.py` TaskTool | ✅ |
| **output_store** | `core/tool-output-store.ts` | `tools2/output_store.py` OutputStoreTool | ✅ |
| **lsp** | `opencode/src/tool/lsp.ts` + lsp.txt | ❌ 无（有 LSPManager 但无工具封装） | **缺失** |
| mcp-websearch | `opencode/src/tool/mcp-websearch.ts` | ❌ 无 | 缺失 |
| http-body | `core/tool/http-body.ts` | ❌ 无 | 缺失 |
| application-tools | `core/tool/application-tools.ts` | ❌ 无 | 缺失 |
| external-directory | `opencode/src/tool/external-directory.ts` | ❌ 无 | 缺失 |
| browser | ❌ OpenCode 无 | `tools2/browser.py` | CScode 多出 |
| ls | ❌ OpenCode 无（用 glob） | `tools2/ls.py` | CScode 多出 |
| **registry** | `core/tool/registry.ts` + `opencode/src/tool/registry.ts` | `tools2/registry.py` + `core/tool_registry.py` ToolRegistryV2 | ✅ |
| **tool 通用接口** | `core/tool/tool.ts` + `opencode/src/tool/tool.ts` | `tools2/base.py` Tool（泛型基类） | ✅ |

**结论：Tool 系统覆盖率约 90%**，18 个工具中 17 个已对齐，缺 lsp 工具（LSPManager 已有但未封装为 tool）。CScode 多了 browser 和 ls 两个工具。

---

### 2.3 Permission 系统

| 子功能 | OpenCode | CScode | 状态 |
|-------|----------|--------|------|
| 权限管理器 | `core/permission.ts` + `core/permission/saved.ts` + `core/permission/sql.ts` | `core/permission_v2.py` PermissionV2 | ✅ 已对齐 |
| 权限评估 | `opencode/src/permission/evaluate.ts` + `arity.ts` | `PermissionV2.evaluate()` | ✅ 已对齐 |
| Wildcard 匹配 | （内置） | `Wildcard` 类（支持 `*`/`**`/`?`） | ✅ 已对齐 |
| **已保存权限（持久化）** | `core/permission/saved.ts` + SQL 表 | `SavedRules` 类 + `saved_rules` 表 | ✅ 已对齐 |
| Ruleset | （内置） | `Ruleset` 数据类 | ✅ 已对齐 |
| Rule | （内置） | `Rule` 数据类（action/resource/effect） | ✅ 已对齐 |
| **Permission Rules API** | `protocol/groups/permission.ts` | `/api/permission-rules` GET/POST/DELETE | ✅ 已对齐 |
| 权限策略联动 | `core/policy.ts` | `enterprise/policies.py`（企业版） | ⚠️ 部分 |
| Question 流程 | `core/question.ts` + `protocol/groups/question.ts` | `tools2/question.py` + `server/question_registry.py` + `/questions` API | ✅ 已对齐 |

**结论：Permission 系统覆盖率约 80%**，核心功能 + SavedRules 持久化 + API 已对齐，缺 policy 深度联动、session 级权限。

---

### 2.4 Config 系统

| 子功能 | OpenCode | CScode | 状态 |
|-------|----------|--------|------|
| 主配置 | `core/config.ts` + `opencode/src/config/config.ts` | `core/config.py` + `core/config_v2.py` ConfigV2 | ✅ 已对齐 |
| **多层合并** | v1 配置（全局/项目/本地） | ConfigV2（6 层：默认/全局/项目/本地opencode/数据库/CLI） | ✅ 已对齐 |
| **Shell 配置** | （内置） | `ShellConfig`（shell + timezone） | ✅ |
| **Model 配置** | `core/config/` 分散 | `ModelConfig`（provider/model/api_base/api_key/max_tokens/temperature/top_p） | ✅ |
| **Agent 配置** | `core/config/agent.ts` | `AgentConfig`（system_prompt + max_tool_rounds） | ✅ |
| **MCP 配置** | `core/config/mcp.ts` | `MCPConfig`（name/command/args/env） | ✅ |
| **Plugin 配置** | `core/config/plugin.ts` + `opencode/src/config/plugin.ts` | `PluginConfig`（name/enabled/config） | ✅ |
| **Provider 配置** | `core/config/provider.ts` | `ProviderConfig`（api_key + api_base） + provider 字典 | ✅ |
| **Permission 配置** | （内置） | `Ruleset` 列表 | ✅ |
| Variable 解析 | `opencode/src/config/variable.ts` | `core/config_variable.py` | ✅ |
| Config Scanner / Watcher | `core/config/watcher.ts` | `core/config_scanner.py` | ⚠️ 部分 |
| Paths 管理 | `opencode/src/config/paths.ts` | `core/config.py`（部分） | ⚠️ |
| LSP 配置 | `core/config/lsp.ts` | ❌ 无 | 缺失 |
| Reference 配置 | `core/config/reference.ts` | ❌ 无 | 缺失 |
| Tool 输出配置 | `core/config/tool-output.ts` | ❌ 无 | 缺失 |
| **Attachments** | `core/config/attachments.ts` | ❌ 无 | **缺失** |
| **Experimental** | `core/config/experimental.ts` | ❌ 无 | **缺失** |
| **Formatter** | `core/config/formatter.ts` | ❌ 无 | **缺失** |
| **Markdown** | `core/config/markdown.ts` | ❌ 无 | **缺失** |
| **TUI 配置** | `opencode/src/config/tui.ts` + `tui-cwd.ts` + `tui-host-attention.ts` + `tui-migrate.ts` | `tui/themes.py`（仅主题） | ⚠️ 部分 |
| Command 配置 | `core/config/command.ts` + `opencode/src/command/` | ❌ 无 | 缺失 |
| 配置 API | — | `/api/config` GET/POST | ✅ |

**结论：Config 系统覆盖率约 65%**，主配置 + 7 个子配置 + 6 层合并已对齐，缺 attachments/experimental/formatter/markdown/tool-output/lsp/reference 等子配置。

---

### 2.5 PTY 系统（完全缺失）

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| PTY 主模块 | `core/pty.ts` | ❌ 无 |
| PTY 协议 | `core/pty/protocol.ts` | ❌ 无 |
| PTY Bun 实现 | `core/pty/pty.bun.ts` | ❌ 无 |
| PTY Node 实现 | `core/pty/pty.node.ts` | ❌ 无 |
| PTY Schema | `core/pty/schema.ts` | ❌ 无 |
| PTY Ticket | `core/pty/ticket.ts` + `opencode/src/server/shared/pty-ticket.ts` | ❌ 无 |
| PTY API Group | `protocol/groups/pty.ts` | ❌ 无 |
| PTY Handler | `opencode/src/server/.../handlers/pty.ts` | ❌ 无 |
| PTY Environment | `opencode/src/plugin/pty-environment.ts` | ❌ 无 |

**结论：PTY 系统覆盖率 0%**，长时会话、共享终端、外部 PTY 客户端完全不支持。

---

### 2.6 Integration 系统（完全缺失）

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Integration 主模块 | `core/integration.ts` | ❌ 无 |
| Connection | `core/integration/connection.ts` | ❌ 无 |
| API Group | `protocol/groups/integration.ts` | ❌ 无 |
| Location Layer | `core/location-layer.ts` + `core/location-mutation.ts` + `core/location.ts` | ❌ 无 |

**结论：Integration 系统覆盖率 0%**，无法与外部 IDE/WebSocket 客户端建立持久连接。

---

### 2.7 Credential 系统（完全缺失）

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Credential 主模块 | `core/credential.ts` | ❌ 无 |
| Credential SQL | `core/credential/sql.ts` | ❌ 无 |
| API Group | `protocol/groups/credential.ts` | ❌ 无 |
| OAuth 令牌管理 | `core/oauth/page.ts` + `opencode/src/mcp/auth.ts` + `oauth-callback.ts` + `oauth-provider.ts` | `auth/`（仅 GitHub + OpenAI OAuth，非 credential 系统） | ⚠️ 部分 |

**结论：Credential 系统覆盖率 0%**，凭证只能存环境变量或配置文件，无法独立管理、轮换、共享。

---

### 2.8 Project / Workspace 系统（完全缺失）

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Project 主模块 | `core/project.ts` | ❌ 无 |
| Project SQL | `core/project/sql.ts` | ❌ 无 |
| Project Schema | `core/project/schema.ts` + `core/project/directories.ts` | ❌ 无 |
| Project Copy | `core/project/copy.ts` + `copy-strategies.ts` + `protocol/groups/project-copy.ts` | ❌ 无 |
| Workspace | `core/workspace.ts` | ❌ 无 |
| Control-Plane | `core/control-plane/move-session.ts` + `workspace.sql.ts` | ❌ 无 |
| Workspace Adapter | `opencode/src/control-plane/adapters/worktree.ts` + `workspace-adapter-runtime.ts` | ❌ 无 |
| Project Bootstrap | `opencode/src/project/bootstrap-service.ts` + `bootstrap.ts` + `instance-context.ts` + `instance-layer.ts` + `instance-runtime.ts` + `instance-store.ts` | ❌ 无 |
| Project VCS | `opencode/src/project/vcs.ts` | `git/`（diff/review/snapshot） | ⚠️ 部分 |
| Workspace Routing | `opencode/src/server/shared/workspace-routing.ts` + `middleware/workspace-routing.ts` | ❌ 无 |
| Worktree | `opencode/src/worktree/index.ts` | ❌ 无 |

**结论：Project/Workspace 系统覆盖率 0%**（VCS 部分除外），无法管理多项目、多工作区。

---

### 2.9 Filesystem 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Filesystem 主模块 | `core/filesystem.ts` | 散落（tools2/ + git/ + server/files 路由） |
| FFF 抽象层 | `core/filesystem/fff.bun.ts` + `fff.node.ts` | ❌ 无 |
| **Ignore 规则** | `core/filesystem/ignore.ts` | ❌ 无 |
| **Protected 路径** | `core/filesystem/protected.ts` | ❌ 无 |
| **Watcher** | `core/filesystem/watcher.ts` | ❌ 无 |
| **Search** | `core/filesystem/search.ts` | `/api/files/search`（简单搜索） | ⚠️ 部分 |
| File mutation | `core/file-mutation.ts` | ❌ 无 |
| File | `core/file.ts` | ❌ 无 |
| FS Util | `core/fs-util.ts` | ❌ 无 |
| Ripgrep | `core/ripgrep.ts` + `ripgrep/binary.ts` | `tools2/grep.py`（Python grep） | ⚠️ |
| API Group | `protocol/groups/fs.ts` | `/api/files/search` + `/api/files/read` + `/api/files/list` | ⚠️ 部分 |
| File Handler | `opencode/src/server/.../handlers/fs.ts` + `server/src/handlers/fs.ts` | `server/app.py` 中 files 路由 | ⚠️ 部分 |
| Patch | `core/patch.ts` + `opencode/src/patch/index.ts` | `tools2/apply_patch.py` | ✅ |
| Snapshot | `core/snapshot.ts` + `opencode/src/snapshot/index.ts` | `git/snapshot.py` | ✅ |
| Git | `core/git.ts` + `opencode/src/git/index.ts` | `git/`（diff/review/snapshot） | ✅ |

**结论：Filesystem 系统覆盖率约 35%**，基础文件操作通过工具实现，缺 ignore/protected/watcher/fff 抽象层。

---

### 2.10 Agent 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Agent 主模块 | `core/agent.ts` + `opencode/src/agent/agent.ts` | `app/agent.py` AgentV2 | ✅ |
| **Sub-agent** | `opencode/src/agent/subagent-permissions.ts` | `core/sub_agent.py` SubAgentOrchestrator | ⚠️ 部分 |
| **Agent Factory** | （内置） | `app/factory.py` create_agent_v2 / create_tool_registry | ✅ |
| **Prompt 模板** | `agent/prompt/` 15+ 个（compaction/explore/summary/title/generate/default/beast/codex/copilot-gpt-5/gemini/gpt/kimi/plan*/trinity） | ❌ 无独立模板（hardcode 在 agent.py） | **缺失** |
| Agent ID | `schema/agent.ts` | ❌ 无 | 缺失 |
| Agent API Group | `protocol/groups/agent.ts` | ❌ 无 | 缺失 |
| Agent Config | `core/config/agent.ts` | `AgentConfig`（在 ConfigV2 中） | ✅ |
| Plugin Agent | `core/plugin/agent.ts` | ❌ 无 | 缺失 |
| ACP Agent | `opencode/src/acp/agent.ts` | `acp/protocol.py`（仅协议） | ⚠️ 部分 |

**结论：Agent 系统覆盖率约 55%**，AgentV2 + Factory + SubAgentOrchestrator 已实现，缺 prompt 模板库、plugin agent。

---

### 2.11 Model / Provider 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Model 主模块 | `core/model.ts` | `llm/client.py`（部分） | ⚠️ |
| Provider 主模块 | `core/provider.ts` + `opencode/src/provider/provider.ts` | `providers/` 7 个文件（6 个 provider + base） | ✅ 基础 |
| Provider 状态 | `opencode/src/provider/model-status.ts` + `provider.ts` | ❌ 无 | 缺失 |
| Provider Auth | `opencode/src/provider/auth.ts` | `auth/`（部分） | ⚠️ |
| Provider Error | `opencode/src/provider/error.ts` | `core/errors.py`（通用） | ⚠️ |
| Provider Transform | `opencode/src/provider/transform.ts` | `llm/route.py`（部分） | ⚠️ |
| Models Dev | `core/models-dev.ts` | ❌ 无 | 缺失 |
| Catalog | `core/catalog.ts` + `schema/catalog.ts` | ❌ 无 | 缺失 |
| AISDK | `core/aisdk.ts` | ❌ 无 | 缺失 |
| Model API Group | `protocol/groups/model.ts` | ❌ 无 | 缺失 |
| Provider API Group | `protocol/groups/provider.ts` | ❌ 无 | 缺失 |
| **Plugin Provider（30+）** | `core/plugin/provider/`（30+ provider 插件） | `providers/`（6 个：anthropic/azure/gemini/ollama/openai/openrouter） | ⚠️ 仅 20% |
| **LLM 层** | `packages/llm/`（llm/provider/tool-runtime/tool/route/cache-policy/schema） | `llm/`（client/route/service/tool_runtime/types/adapters/protocols） | ⚠️ 部分 |
| Tool Runtime | `packages/llm/src/tool-runtime.ts` | `llm/tool_runtime.py` | ✅ |

**结论：Model/Provider 系统覆盖率约 35%**，6 个 provider + LLM 层基础已实现，缺 24+ 个 provider、catalog、models-dev、model-status。

---

### 2.12 Question 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Question 主模块 | `core/question.ts` | `tools2/question.py` |
| Question Schema | `schema/question.ts` | `schema/options.py`（部分） | ⚠️ |
| **Question Registry** | `opencode/src/question/index.ts` + `schema.ts` | `server/question_registry.py` QuestionRegistry | ✅ |
| Question API Group | `protocol/groups/question.ts` | `/questions` list + `/reply` + `/reject` | ✅ |
| Question Handler | `opencode/src/server/.../handlers/question.ts` | `server/app.py` question 路由 | ⚠️ 部分 |
| Question Tool | `opencode/src/tool/question.ts` + `question.txt` | `tools2/question.py` | ✅ |
| **always_allow 自动保存权限** | （内置） | question reply 中 `always_allow` → 自动存权限规则 | ✅ |

**结论：Question 系统覆盖率约 85%**，已基本对齐。

---

### 2.13 Skill 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Skill 主模块 | `core/skill.ts` + `opencode/src/skill/index.ts` | `skills/loader.py` SkillLoader |
| **Skill Discovery** | `core/skill/discovery.ts` + `opencode/src/skill/discovery.ts` | `SkillLoader.discover()`（扫描目录 md 文件） | ✅ |
| **Skill Guidance** | `core/skill/guidance.ts` + `core/reference/guidance.ts` | ❌ 无 | **缺失** |
| Skill API Group | `protocol/groups/skill.ts` | ❌ 无 | 缺失 |
| Skill Tool | `opencode/src/tool/skill.ts` + `skill.txt` | `tools2/skill.py` | ✅ |
| Skill Config | `core/config/skill/` | ❌ 无 | 缺失 |
| Plugin Skill | `core/plugin/skill.ts` | ❌ 无 | 缺失 |

**结论：Skill 系统覆盖率约 50%**，loader + discover + tool 已对齐，缺 guidance/config/plugin skill。

---

### 2.14 Plugin 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Plugin 主模块 | `core/plugin.ts` + `opencode/src/plugin/index.ts` | `plugins/` |
| Plugin Host | `core/plugin/host.ts` | `plugins/loader.py`（部分） | ⚠️ |
| Plugin Command | `core/plugin/command.ts` + `opencode/src/command/` | `plugins/hooks.py`（部分） | ⚠️ |
| Plugin Agent | `core/plugin/agent.ts` | ❌ 无 | 缺失 |
| Plugin Skill | `core/plugin/skill.ts` | ❌ 无 | 缺失 |
| **Plugin Provider（30+）** | `core/plugin/provider/`（30+ provider 插件） | ❌ 无 | **完全缺失** |
| Plugin Internal | `core/plugin/internal.ts` | ❌ 无 | 缺失 |
| Plugin Promise | `core/plugin/promise.ts` | ❌ 无 | 缺失 |
| Plugin Variant | `core/plugin/variant.ts` | ❌ 无 | 缺失 |
| Plugin Models Dev | `core/plugin/models-dev.ts` | ❌ 无 | 缺失 |
| Plugin Loader（opencode） | `opencode/src/plugin/loader.ts` + `install.ts` + `meta.ts` + `shared.ts` | `plugins/loader.py` | ⚠️ |
| Plugin TUI | `opencode/src/plugin/tui/` | ❌ 无 | 缺失 |
| Plugin Package | `packages/plugin/`（独立 npm 包） | ❌ 无 | 缺失 |
| Plugin SDK | （内置） | `plugins/sdk.py` | ✅ |
| Plugin Manifest | （内置） | `plugins/manifest.py` | ✅ |

**结论：Plugin 系统覆盖率约 25%**，基础 loader + manifest + hooks + sdk 有，缺 30+ 内置 provider 插件、command 模板、TUI 集成。

---

### 2.15 Event 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Event 主模块 | `core/event.ts` | `core/events.py` + `schema/events.py` |
| Event SQL | `core/event/sql.ts` | `storage/event_store.py` EventStore | ✅ |
| **Event Schema** | `schema/event.ts` + `session-event.ts` + `ide-event.ts` + `lsp-event.ts` + `mcp-event.ts` + `tui-event.ts` + `vcs-event.ts` | `schema/events.py`（LLMEvent: TextDelta/TextEnded/ToolCallEnded/ToolResult/ToolFailure/Finish/Error） | ⚠️ 部分 |
| **Event API Group** | `protocol/groups/event.ts` | `/api/events` + `/sessions/{id}/events` | ✅ |
| Event V2 Bridge | `opencode/src/event-v2-bridge.ts` | ❌ 无 | 缺失 |
| Public Event Manifest | `core/public-event-manifest.ts` + `opencode/src/event-manifest.ts` | ❌ 无 | 缺失 |
| **Event Projectors** | `opencode/src/server/projectors.ts` + `init-projectors.ts` | `server/projector.py` Projector | ✅ |
| Event Bus | `opencode/src/bus/global.ts` | ❌ 无 | 缺失 |
| **SSE Streaming** | （内置） | `/chat/stream` SSE + `_llm_event_to_dict()` + `EventStore.subscribe()` | ✅ |

**结论：Event 系统覆盖率约 70%**，核心事件 + EventStore + Projector + SSE 已对齐，缺 v2-bridge、public-manifest、event-bus。

---

### 2.16 Database 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Database 主模块 | `core/database/database.ts` | `storage/db.py` Database |
| **Migration 系统** | `core/database/migration/`（37 个 migration） + `migration.gen.ts` + `migration.ts` | `storage/migration.py` MigrationRegistry + `migration_runner.py` MigrationRunner（5 个 migration） | ⚠️ 部分 |
| Path 管理 | `core/database/path.ts` | `storage/db.py`（部分） | ⚠️ |
| Schema | `core/database/schema.gen.ts` + `schema.sql.ts` | ❌ 无 schema.gen | 缺失 |
| SQLite 抽象 | `core/database/sqlite.ts` + `sqlite.node.ts` + `sqlite.bun.ts` | `storage/db.py`（aiosqlite） | ✅ |
| Drizzle 配置 | `core/drizzle.config.ts` | ❌ 无（SQL 手写） | 缺失 |

**已实现的 5 个 Migration：**
1. v1: sessions + messages 表
2. v2: config 表
3. v3: event_sequences + events 表（EventStore）
4. v4: context_epochs 表（Compaction）
5. v5: expected_tasks + task_verifications 表（TaskTracker）

**结论：Database 系统覆盖率约 55%**，基础 + migration 框架已对齐，但 OpenCode 有 37 个 migration（涵盖 workspace/session-message-cursor/events/session-usage/data-migration-state/session-metadata/context-epoch/credential 等），CScode 只有 5 个。

---

### 2.17 LSP 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| LSP Client | `core/lsp.ts` | `lsp/client.py` LSPClient | ✅ |
| LSP Manager | `opencode/src/lsp/` | `lsp/manager.py` LSPManager | ✅ |
| 支持语言 | — | Python/TypeScript/JavaScript/Go/Rust/Ruby/Java/PHP（8 种） | ✅ |
| LSP 工具 | `opencode/src/tool/lsp.ts` | ❌ 无（未封装为工具） | **缺失** |
| Diagnostic | `core/lsp/diagnostic.ts` | ❌ 无 | 缺失 |
| Language 配置 | `core/lsp/language.ts` | ❌ 无 | 缺失 |
| Launch 管理 | `core/lsp/launch.ts` | ❌ 无 | 缺失 |
| Server 生命周期 | `opencode/src/lsp/server.ts` | `lsp/manager.py`（基础） | ⚠️ 部分 |

**结论：LSP 系统覆盖率约 50%**，LSPClient + LSPManager 已实现，缺 lsp 工具封装、diagnostic、完整 server 生命周期。

---

### 2.18 MCP 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| MCP Client | `core/mcp.ts` + `opencode/src/mcp/client.ts` | `mcp/client.py` MCPClient | ✅ |
| MCP Server | `opencode/src/mcp/server.ts` | `mcp/server.py` MCPServer | ✅ |
| MCP 配置 | `core/config/mcp.ts` | （ConfigV2 中 MCPConfig） | ✅ |
| MCP OAuth | `opencode/src/mcp/auth.ts` + `oauth-callback.ts` + `oauth-provider.ts` | ❌ 无 | **缺失** |
| MCP Catalog | `core/mcp/catalog.ts` | ❌ 无 | 缺失 |
| MCP 工具集成 | `opencode/src/tool/mcp-websearch.ts` | ❌ 无 | 缺失 |

**结论：MCP 系统覆盖率约 50%**，基础 client + server 已实现，缺 OAuth、catalog、工具集成。

---

### 2.19 Auth 模块

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Token 管理 | `core/auth/token.ts` | `auth/tokens.py` | ✅ |
| GitHub OAuth | `core/auth/github.ts` | `auth/github.py` GitHubOAuth | ✅ |
| OpenAI OAuth | `opencode/src/provider/openai-oauth.ts` | `auth/openai_oauth.py` | ✅ |
| OAuth 回调处理 | `opencode/src/server/.../oauth/` | ❌ 无完整回调流程 | 缺失 |

**结论：Auth 模块覆盖率约 60%**，基础认证 + GitHub/OpenAI OAuth 客户端已实现，缺完整回调流程、credential 集成。

---

### 2.20 Enterprise 模块

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Audit 日志 | `packages/enterprise/src/audit/` | `enterprise/audit.py` AuditLogger | ✅ |
| Policy 管理 | `packages/enterprise/src/policy/` | `enterprise/policies.py` | ⚠️ 部分 |
| Remote Config | `packages/enterprise/src/remote-config/` | `enterprise/remote_config.py` | ⚠️ 部分 |

**结论：Enterprise 模块覆盖率约 50%**，基础框架已实现，功能深度不足。

---

## 3. API 端点对比

### 3.1 CScode 已实现的 28 个 API 端点（+ session 单数别名）

| 端点 | 方法 | 功能 | 对应 OpenCode |
|------|------|------|--------------|
| `/api/health` | GET | 健康检查 | health group |
| `/api/chat` | POST | 非流式对话 | chat |
| `/api/chat/stream` | POST | 流式对话（SSE） | chat/stream |
| `/api/events` | GET | 全局事件订阅 | event group |
| `/api/sessions/{id}/events` | GET | 会话事件订阅 | session/event |
| `/api/sessions` | GET | 会话列表 | session.list |
| `/api/sessions` | POST | 创建会话 | session.create |
| `/api/sessions/{id}` | DELETE | 删除会话 | session.delete |
| `/api/sessions/{id}` | PATCH | 更新会话（title 等） | session.update |
| `/api/sessions/{id}/stop` | POST | 停止会话 | session.stop |
| `/api/sessions/{id}/export` | POST | 导出会话 | session.export |
| `/api/sessions/import` | POST | 导入会话 | session.import |
| `/api/sessions/{id}/messages` | GET | 会话消息列表 | session.message.list |
| `/api/sessions/{id}/context` | GET | 会话上下文 | session.context |
| `/api/sessions/{id}/model` | POST | 切换模型 | session.model |
| `/api/sessions/{id}/agent` | POST | 切换 agent | session.agent |
| `/api/sessions/{id}/questions` | GET | 问题列表 | question.list |
| `/api/sessions/{id}/questions/{rid}/reply` | POST | 回复问题 | question.reply |
| `/api/sessions/{id}/questions/{rid}/reject` | POST | 拒绝问题 | question.reject |
| `/api/sessions/{id}/compact` | POST | 压缩会话 | session.compact |
| `/api/config` | GET | 获取配置 | config.get |
| `/api/config` | POST | 保存配置 | config.set |
| `/api/permission-rules` | GET | 权限规则列表 | permission.list |
| `/api/permission-rules` | POST | 创建权限规则 | permission.create |
| `/api/permission-rules/{id}` | DELETE | 删除权限规则 | permission.delete |
| `/api/files/search` | GET | 文件搜索 | fs.search |
| `/api/files/read` | POST | 读取文件 | fs.read |
| `/api/files/list` | GET | 文件列表 | fs.list |

> 注：所有 `/api/sessions/...` 路由都有对应的 `/api/session/...` 单数别名。

### 3.2 OpenCode Protocol API Groups（18 个）

| Group | CScode 覆盖度 |
|-------|-------------|
| session | ⚠️ 部分（缺 revert/share/input/summarize/message-feedback） |
| message | ⚠️ 部分（缺单消息 CRUD、feedback） |
| event | ✅ 基本对齐 |
| agent | ❌ 无 |
| command | ❌ 无 |
| credential | ❌ 无 |
| integration | ❌ 无 |
| location | ❌ 无 |
| model | ❌ 无 |
| provider | ❌ 无 |
| permission | ✅ 基本对齐（CRUD） |
| project-copy | ❌ 无 |
| pty | ❌ 无 |
| question | ✅ 基本对齐 |
| reference | ❌ 无 |
| skill | ❌ 无 |
| fs | ⚠️ 部分（search/read/list） |
| health | ✅ 对齐 |

### 3.3 OpenCode Instance HTTP API Groups（21 个）

config、control-plane、control、event、experimental、file、global、instance、mcp、metadata、permission、project-copy、project、provider、pty、query、question、session、sync、tui、workspace

CScode 覆盖情况：session ✅ 部分、event ✅、question ✅、config ✅、permission ✅、file ⚠️ 部分、mcp ❌、其余 ❌

**API 端点覆盖率约 47%**（28 / 60）。

---

## 4. 前端功能对比

| 模块 | OpenCode | CScode | 状态 |
|------|----------|--------|------|
| Web App | `packages/app/`（context: file/mcp/sdk/sync/tabs、i18n: 18 国、pages、utils、wsl） | `src/cscode/web/`（components/hooks/lib/stores/themes） | ⚠️ 部分 |
| **核心聊天 UI** | （内置） | MessageList + Message + Composer + ThinkingIndicator | ✅ |
| **侧栏** | （内置） | Sidebar + ThreadsHeader + ProjectList + ProjectItem | ✅ |
| **设置面板** | （内置） | SettingsPanel（provider/model/温度/top_p/system_prompt/MCP/plugins/keybindings/permissions） | ✅ |
| **命令面板** | （内置） | CommandPalette（新建会话/切换会话/切换主题/切换侧边栏/设置） | ✅ |
| **主题系统** | `packages/ui/src/theme/` | ThemeProvider + themes（深色/浅色） | ✅ |
| **问题对话框** | （内置） | QuestionDialog | ✅ |
| **工具调用显示** | （内置） | ToolCallDisplay | ✅ |
| **Markdown 渲染** | （内置） | MarkdownRenderer + CodeBlock | ✅ |
| **Toast 通知** | （内置） | ToastContainer + useToastStore | ✅ |
| **模式切换** | （内置） | ModeToggle | ✅ |
| **自动完成** | （内置） | AutocompletePopup | ✅ |
| **错误边界** | （内置） | ErrorBoundary | ✅ |
| **组件数量** | — | 20+ 组件（chat/4 + layout/3 + markdown/2 + sidebar/3 + ui/10） | ✅ |
| **状态管理** | — | 4 个 store（config/session/toast/ui） | ✅ |
| **TUI** | `packages/tui/`（config/context/plugin/prompt/routes/theme/ui/util + app/attention/audio/clipboard/editor/editor-zed/keymap/logo/runtime） | `src/cscode/tui/`（app + themes） | ⚠️ 部分 |
| **Desktop** | `packages/desktop/`（main: apps/ipc/menu） | `desktop/src-tauri/`（Rust + Tauri v2） | ⚠️ 部分 |
| **UI 组件库** | `packages/ui/`（components/context/hooks/i18n/styles/theme） | 复用 web/ | ⚠️ 部分 |
| Session UI | `packages/session-ui/`（独立包） | ❌ 无 | 缺失 |
| Storybook | `packages/storybook/` | ❌ 无 | 缺失 |
| Stats App | `packages/stats/` | ❌ 无 | 缺失 |
| Console | `packages/console/` | ❌ 无 | 缺失 |
| **Enterprise** | `packages/enterprise/` | `src/cscode/enterprise/`（audit/policies/remote_config） | ⚠️ 部分 |
| Slack 集成 | `packages/slack/` | ❌ 无 | 缺失 |
| **i18n 多语言** | 18 国语言（ar/br/bs/da/de/en/es/fr/ja/ko/no/pl/ru/th/tr/uk/zh/zht） | ❌ 仅中文（硬编码英文 label） | **缺失** |
| **File Context** | `packages/app/src/context/file.tsx` | ❌ 无 | 缺失 |
| **MCP Context** | `packages/app/src/context/mcp.ts` | ❌ 无 | 缺失 |
| **SDK Context** | `packages/app/src/context/sdk.tsx` | ❌ 无 | 缺失 |
| **Sync Context** | `packages/app/src/context/sync.tsx` | ❌ 无 | 缺失 |
| **Tabs Context** | `packages/app/src/context/tabs.tsx` | ❌ 无 | 缺失 |
| **WSL 支持** | `packages/app/src/wsl/` | ❌ 无 | 缺失 |
| **桌面菜单** | `packages/desktop/src/main/menu.ts` | ❌ 无（Tauri 默认菜单） | 缺失 |
| **测试覆盖** | — | Jest 单元测试 + Playwright E2E 测试 | ✅ |

**前端功能覆盖率约 50%**，核心聊天 UI + 设置 + 命令面板 + 主题已对齐，缺 i18n、多 context、session-ui、storybook、stats 等。

---

## 5. 测试覆盖对比

| 类别 | CScode | 说明 |
|------|--------|------|
| 测试文件数 | 70+ | `tests/` 目录下 |
| Python 单元测试 | 60+ | pytest + pytest-asyncio |
| 前端单元测试 | 10+ | Jest + React Testing Library |
| E2E 测试 | 1 | Playwright |
| 核心模块测试覆盖 | 高 | session/permission/config/event_store/tools/lsp/mcp 等均有测试 |

---

## 6. 优先级建议（四阶段路线图）

### P0 — 必须对齐（影响核心功能，8 项）

| 项 | 缺失内容 | 影响 |
|----|---------|------|
| **Tool: lsp** | 封装 LSPManager 为 lsp 工具 + lsp.txt prompt | LLM 无法利用 LSP 信息做代码分析 |
| **Session: revert** | session revert 功能 + revert API | 无法回滚错误的工具调用 |
| **Session: input-inbox** | event-sourced session input | 用户输入与 LLM 流并发冲突 |
| **Config: attachments** | 附件配置 + 文件上传完整流程 | 文件附件功能不完整 |
| **Filesystem: ignore** | .gitignore / .opencodeignore 规则 | 工具误读 node_modules/.git 等 |
| **Filesystem: protected** | 受保护路径（防止误改系统文件） | 工具可能误改关键系统文件 |
| **Agent: prompt 模板** | 抽离 system prompt / compaction / summary / title 模板 | prompt 散落 hardcode，难维护 |
| **Provider: model-status** | provider 可用性检测 | 无法提前知道 provider 是否可用 |

### P1 — 重要补充（影响扩展性，15 项）

| 项 | 缺失内容 | 影响 |
|----|---------|------|
| **Credential 系统** | credential 存储 + API + OAuth 管理 | 凭证只能存环境变量，不安全 |
| **Plugin Provider 扩充** | 加 Bedrock/Cohere/Grok/Mistral/Nvidia/Perplexity/Vertex/XAI 等 | provider 生态薄弱（仅 6 个 vs 30+） |
| **Skill Guidance** | skill guidance + reference guidance | 技能无法提供上下文指导 |
| **Catalog** | model/provider/agent catalog + models.dev | 模型/Provider 目录缺失 |
| **Filesystem: watcher** | 文件系统 watcher | 文件变更不感知 |
| **Config 子模块** | experimental/formatter/markdown/tool-output/lsp/reference | 配置项不完整 |
| **Session: message-updater** | message updater 模式 | 消息更新机制不灵活 |
| **Session: summary** | 会话摘要 + summary API | 长会话无法快速预览 |
| **Sharing: 持久化** | share 持久化到数据库 + share API | 分享功能无法持久化 |
| **MCP: OAuth** | mcp oauth-callback + oauth-provider | MCP 服务器 OAuth 无法用 |
| **Background Job** | 后台任务调度 | 异步任务无法管理 |
| **i18n 多语言** | 至少中英文 + i18n 框架 | 仅中文，国际化能力弱 |
| **Permission: session 级** | session 级 saved permission（目前是全局内存） | 权限粒度太粗 |
| **LSP: diagnostic** | LSP diagnostic + language 配置 | LSP 功能不完整 |
| **Auth: 回调流程** | OAuth 回调完整流程 | OAuth 无法完整使用 |

### P2 — 增强能力（可选，18 项）

| 项 | 缺失内容 |
|----|---------|
| PTY 系统 | `core/pty.ts` + pty/ 子目录 + API + handler + ticket |
| Integration 系统 | `core/integration.ts` + connection + API |
| Project/Workspace | `core/project.ts` + `core/workspace.ts` + project SQL |
| Control-Plane | `core/control-plane/` + workspace adapter + worktree |
| Sync 系统 | `opencode/src/sync/` + sync context |
| Account 系统 | `core/account.ts` + SQL |
| Reference 系统 | `core/reference.ts` + guidance |
| Policy 系统 | `core/policy.ts` + 深度联动 |
| Repository Cache | `core/repository-cache.ts` + `repository.ts` |
| Observability | `core/observability/`（logging/otlp） |
| NPM 集成 | `core/npm.ts` + `npm-config.ts` |
| GitHub Copilot 深度集成 | `core/github-copilot/`（chat + responses 全套） |
| Event V2 Bridge | `opencode/src/event-v2-bridge.ts` |
| Public Event Manifest | `core/public-event-manifest.ts` |
| Event Bus | `opencode/src/bus/global.ts` |
| Share Next | `opencode/src/share/share-next.ts` |
| TUI 完整 | `packages/tui/` 全套（routes/prompt/plugin/scrollback/attention/audio/clipboard/editor-zed） |
| Storybook | `packages/storybook/` |

### P3 — 长期演进（10 项）

| 项 | 缺失内容 |
|----|---------|
| SDK/Client 独立包 | `packages/sdk/` + `sdk-next/` + `client/` |
| Plugin 独立包 | `packages/plugin/` |
| Container 集成 | `packages/containers/` |
| Function 集成 | `packages/function/` |
| Http Recorder | `packages/http-recorder/` |
| Installation/Version 管理 | `core/installation/` |
| Migration 全量对齐 | OpenCode 37 个 migration vs CScode 5 个 |
| Session-ui 独立包 | 组件库化 |
| Stats App / Console | 运维工具 |
| Slack 集成 | 消息平台集成 |

---

## 7. 关键差距汇总

### 7.1 完全无对齐（16 个系统）

PTY、Integration、Credential、Project/Workspace、Revert、Control-Plane、Sync、Account、Background Job、Policy/Reference、Observability、NPM、GitHub Copilot、Catalog、Installation、Repository Cache

### 7.2 部分对齐但功能不全（14 个系统）

Session、Tool（缺 lsp 工具）、Config、Filesystem、Agent、Model/Provider、MCP、LSP、Plugin、Sharing、Skill、TUI、Event、Database

### 7.3 已基本对齐（10 个系统）

Question、Permission V2、Compaction、Coordinator/Runner、Tool 基础（18 个中 17 个）、ConfigV2、前端核心 UI、Git、Auth、Enterprise

### 7.4 CScode 多出（无对应 OpenCode 需求）

- `tools/browser.py`（OpenCode 无浏览器工具，但有 mcp-websearch）
- `tools/ls.py`（OpenCode 用 glob）
- `TaskTracker`（任务验证追踪，OpenCode 无直接对应）
- `expected_tasks` / `task_verifications` 表（测试验证系统）
- `core/images.py`（图像处理模块）
- `core/structured.py`（结构化输出）
- `core/container.py`（依赖注入容器）
- 70+ 测试文件（高测试覆盖）

---

## 8. 验证方法

完成每个阶段后，使用以下命令验证对齐度：

```bash
# 验证 OpenCode 端点定义
rg "HttpApiEndpoint\.(get|post|patch|delete|put)" github/opencode-full/packages/protocol/src/groups/ -c

# 验证 CScode 端点定义
rg "@api_router\.(get|post|patch|delete|put)" src/cscode/server/app.py -c

# 验证工具对齐
ls src/cscode/tools2/ | sort
ls github/opencode-full/packages/opencode/src/tool/*.ts | xargs -n1 basename | sort

# 验证 Provider 对齐
ls src/cscode/providers/ | sort
ls github/opencode-full/packages/core/src/plugin/provider/*.ts | xargs -n1 basename | sort

# 验证 Schema 对齐
ls src/cscode/schema/ | sort
ls github/opencode-full/packages/schema/src/*.ts | xargs -n1 basename | sort

# 验证 Migration 数量
rg "register\(Migration\(" src/cscode/storage/db.py -c
ls github/opencode-full/packages/core/src/database/migration/*.ts | wc -l

# 验证测试覆盖
ls tests/ | wc -l
```

---

## 9. 总结

基于最新 CScode 源码的全面重新核对（逐文件检查 21 个子包 + 70+ 测试文件），整体功能覆盖率从初版的 25–35% 修正为 **42%–50%**：

**核心功能已对齐（可用）：**
- Session V2 事件溯源（SessionV2 + EventStore + Projector + Coordinator + Runner）
- Compaction 系统（Compactor + ContextCompressor + context_epochs + compact API）
- Permission V2 系统（PermissionV2 + Wildcard + Ruleset + SavedRules + CRUD API）
- Config V2 系统（7 个子配置 + 6 层合并 + config API）
- Question 系统（QuestionRegistry + question 工具 + questions API + always_allow）
- Tool 系统（18 个工具，含 plan/task/output_store，覆盖率 ~90%）
- LSP Manager（8 种语言支持：Python/TS/JS/Go/Rust/Ruby/Java/PHP）
- MCP 系统（MCPClient + MCPServer）
- Agent V2 + SubAgentOrchestrator + AgentFactory
- TaskTracker 任务验证 + expected_tasks 表
- 前端核心 UI（20+ 组件 + 4 个 store + 聊天/侧栏/设置/命令面板/主题/Markdown）
- Git 模块（diff/review/snapshot）
- Auth 模块（tokens + GitHub + OpenAI OAuth）
- Enterprise 模块（audit + policies + remote_config）
- ACP 协议
- 高测试覆盖（70+ 测试文件）

**关键短板（P0 8 项）：**
1. LSP 工具封装（有 LSPManager 但没给 LLM 用）
2. Session Revert（无法回滚）
3. Session Input Inbox（并发输入处理）
4. Config Attachments（附件配置）
5. Filesystem Ignore（忽略规则）
6. Filesystem Protected（保护路径）
7. Agent Prompt 模板库（15+ 个 prompt hardcode）
8. Provider Model Status（可用性检测）

建议按 P0 → P1 → P2 → P3 四阶段逐步对齐，P0 阶段（8 项）应在近期优先完成。
