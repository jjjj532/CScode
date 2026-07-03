# CScode ↔ OpenCode 1:1 功能对齐差距分析报告

> 生成时间：2026-07-03
> 分析基准：OpenCode 源码（`/Users/mac/AI/CScode/github/opencode-full`，25+ packages）
> 分析对象：CScode 源码（`/Users/mac/AI/CScode/src/cscode`，单 Python 包）
> 对照文档：`docs/opencode-analysis/source-analysis.md`、`docs/technical-specification.md`
> 任务范围：**仅做 1:1 功能差距对比，不写代码**

---

## 0. 总体差距概览

| 维度 | OpenCode | CScode | 覆盖率 |
|------|----------|--------|--------|
| Packages 数量 | 25+（app/cli/core/opencode/protocol/schema/sdk/server/tui/ui/desktop/plugin/llm…） | 1（monorepo src/cscode） | — |
| 核心模块（core/src） | ~50 个顶层模块 | ~17 个子包 | — |
| API 端点 | ~60 个（18 个 protocol group + 21 个 instance group） | ~19 个等价端点 | ~30% |
| 工具数量 | 18+（含 lsp/plan/task/skill/apply_patch/question） | 17（tools/ + tools2/ 合集） | ~70% |
| Provider 数量 | 30+（plugin/provider/ 下含 alibaba/anthropic/azure/bedrock/cohere/grok/mistral/nvidia/openrouter/perplexity/vertex/xai…） | 6（anthropic/azure/gemini/ollama/openai/openrouter） | ~20% |
| 事件系统 | EventStore + Projector + v2 schema + PublicEventManifest | EventStore + Projector（已对齐） | ~70% |
| 前端 | React 18 + 18 国语言 + 桌面 + Web + TUI | React 18 + 单语 + 桌面 + TUI | ~40% |
| **整体功能覆盖率** | — | — | **约 25%–35%** |

### 完全缺失的系统（CScode 未实现）

1. **PTY 系统**（伪终端、长时会话、共享 PTY）
2. **Integration 系统**（IDE/WebSocket 集成、外部客户端连接）
3. **Credential 系统**（独立凭证存储、OAuth 令牌管理）
4. **Project / Workspace 系统**（多项目管理、workspace 隔离、control-plane）
5. **Revert 系统**（会话回滚、消息撤销）
6. **Control-Plane 系统**（move-session、workspace adapter、worktree）
7. **Sync 系统**（多设备同步、共享会话状态）
8. **Account 系统**（账户管理、SQL 持久化）
9. **Background Job 系统**（异步任务调度）
10. **Policy / Reference 系统**（策略管理、上下文引用增强）
11. **Observability 系统**（OTLP 上报、结构化日志）
12. **NPM 集成**（npm 包发现、安装、配置）
13. **Image 处理**（photon 图像处理库）
14. **GitHub Copilot 深度集成**（copilot-provider 全套）
15. **Catalog 系统**（model/provider/agent 目录服务）
16. **Installation / Version 管理**
17. **Repository Cache**（仓库缓存层）

### 部分缺失的系统（CScode 已实现但功能不完整）

1. **Session 系统** —— 缺 revert、context-epoch、compaction、input-inbox、run-state、metadata
2. **Tool 系统** —— 缺 lsp 工具、plan 工具、task 工具、http-body 工具
3. **Permission 系统** —— 缺 saved-permission 持久化、policy 联动
4. **Config 系统** —— 缺 attachments、compaction、experimental、formatter、markdown、tool-output、watcher、tui-cwd、tui-host-attention
5. **Filesystem 系统** —— 缺 ignore 规则、protected 路径、watcher、search
6. **Agent 系统** —— 缺 subagent-permissions、prompt 模板（compaction/explore/summary/title）
7. **LLM 系统** —— 缺 cache-policy、record、auth route、native-request/runtime
8. **MCP 系统** —— 缺 oauth-callback、oauth-provider、catalog
9. **LSP 系统** —— 缺 diagnostic、language、launch、server 完整生命周期
10. **Plugin 系统** —— 缺 plugin/provider/（30+ 内置 provider 插件）、command 模板
11. **Sharing 系统** —— 缺 share-next、完整会话分享 schema
12. **Skill 系统** —— 缺 discovery、guidance
13. **TUI 系统** —— 缺 routes、prompt、plugin slots、scrollback、kv、attention、audio、clipboard、editor-zed

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
schema → llm → core → app+server
```

| 层 | 职责 | 关键文件 |
|----|------|---------|
| schema | events/messages/options/tool/ids/errors | `src/cscode/schema/*.py` |
| llm | client/route/service/tool_runtime/adapters/protocols | `src/cscode/llm/*.py` |
| core | config/container/coordinator/events/messages/permissions/runner/session/tool_registry/tracker | `src/cscode/core/*.py` |
| app + server | agent/factory + app/compactor/projector/question_registry | `src/cscode/app/*.py`、`src/cscode/server/*.py` |

### 差距分析

- **架构层级基本对齐**，但 OpenCode 把 `opencode` 包独立成应用层（agent/server/session/tool/lsp/mcp/plugin/skill/share/sync/control-plane），CScode 把这些混在 `app/` 和顶层目录，没有清晰的边界
- **OpenCode 单独的 protocol 包**（HttpApiGroup + OpenAPI 注解）CScode 没有等价物，CScode 的 API 是 FastAPI 直接定义路由
- **OpenCode 的 sdk/sdk-next/client 包**（HTTP 客户端、SDK 生成）CScode 没有
- **OpenCode 的 ui/tui/app/desktop 是独立的 4 个前端包**，CScode 只有 `web/`（React）+ `tui/`（Textual），没有独立桌面包

---

## 2. 16 个核心模块逐项对比

### 2.1 Session 系统

| 子功能 | OpenCode | CScode | 状态 |
|-------|----------|--------|------|
| 会话创建/列表/删除 | `core/session.ts` + `protocol/groups/session.ts` | `core/session.py` + `server/app.py` | ✅ 已对齐 |
| 会话消息存储 | `core/session/message.ts` + `core/session/sql.ts` | `storage/session.py` + `storage/event_store.py` | ✅ 已对齐 |
| 会话投影 | `core/session/projector.ts` + `core/session/store.ts` | `server/projector.py` + `server/compactor.py` | ✅ 已对齐 |
| 会话信息（Info） | `core/session/info.ts` | ❌ 无 | 缺失 |
| 会话历史 | `core/session/history.ts` | ❌ 无 | 缺失 |
| 会话输入队列 | `core/session/input.ts` + `core/session/sql.ts`（event_sourced_session_input） | ❌ 无 | 缺失 |
| 会话执行（Execution） | `core/session/execution/local.ts` | `app/agent.py`（部分） | ⚠️ 部分 |
| 会话 Runner | `core/session/runner/`（llm/max-steps/model/publish-llm-event/to-llm-message） | `core/runner.py`（部分） | ⚠️ 部分 |
| 会话 Prompt | `core/session/prompt.ts` | ❌ 无（hardcode 在 agent.py） | 缺失 |
| **会话 Revert** | `core/session/revert.ts` + `schema/revert.ts` | ❌ 完全无 | **缺失** |
| **会话 Compaction** | `core/session/compaction.ts` + `agent/prompt/compaction.txt` | ❌ 无 | **缺失** |
| **会话 Context Epoch** | `core/session/context-epoch.ts` | ❌ 无 | **缺失** |
| **会话 Run State** | `core/session/run-state.ts` | ❌ 无（用 tracker.py 部分） | **缺失** |
| **会话 Metadata** | `core/session/sql.ts` 的 metadata 字段 | ❌ 无 | **缺失** |
| **会话 Todo** | `core/session/todo.ts` | `tools/todowrite.py`（仅工具） | ⚠️ 部分 |
| **会话 Message Updater** | `core/session/message-updater.ts` | ❌ 无 | **缺失** |
| **会话 Error** | `core/session/error.ts` | `core/errors.py`（通用） | ⚠️ 部分 |
| **会话 Event** | `core/session/event.ts` | `core/events.py` | ✅ 已对齐 |
| 会话 Share | `core/share/sql.ts` + `opencode/src/share/` | `sharing/` | ⚠️ 部分 |
| 会话 Sync | `opencode/src/sync/` | ❌ 完全无 | **缺失** |
| 会话 Status | `core/session/status.ts` | ❌ 无 | 缺失 |
| 会话 Summary | `core/session/summary.ts` + `agent/prompt/summary.txt` | ❌ 无 | 缺失 |
| 会话 System Prompt | `core/session/system.ts` | ❌ 无 | 缺失 |
| 会话 Reminders | `core/session/reminders.ts` | ❌ 无 | 缺失 |
| 会话 Retry | `core/session/retry.ts` | ❌ 无 | 缺失 |
| 会话 Overflow | `core/session/overflow.ts` | ❌ 无 | 缺失 |
| 会话 Instruction | `core/session/instruction.ts` | ❌ 无 | 缺失 |

**结论：Session 系统覆盖率约 30%**，仅基础 CRUD + 事件存储已对齐，缺 revert/compaction/context-epoch/run-state/input-inbox/metadata 等高级功能。

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
| **plan** | `opencode/src/tool/plan.ts` + plan-enter/exit.txt | ❌ 无 | **缺失** |
| **task** | `opencode/src/tool/task.ts` + task.txt | ❌ 无（已有 `task.py` 占位但不完整） | **缺失** |
| **lsp** | `opencode/src/tool/lsp.ts` + lsp.txt | ❌ 无 | **缺失** |
| **mcp-websearch** | `opencode/src/tool/mcp-websearch.ts` | ❌ 无 | 缺失 |
| **http-body** | `core/tool/http-body.ts` | ❌ 无 | 缺失 |
| **application-tools** | `core/tool/application-tools.ts` | ❌ 无 | 缺失 |
| **external-directory** | `opencode/src/tool/external-directory.ts` | ❌ 无 | 缺失 |
| browser | ❌ OpenCode 无 | `tools2/browser.py` | CScode 多出 |
| ls | ❌ OpenCode 无（用 glob） | `tools2/ls.py` | CScode 多出 |
| echo | ❌ OpenCode 无 | `tools/echo.py` | CScode 多出 |
| **registry** | `core/tool/registry.ts` + `opencode/src/tool/registry.ts` | `tools2/registry.py` + `core/tool_registry.py` | ✅ |
| **tool.ts 通用接口** | `core/tool/tool.ts` + `opencode/src/tool/tool.ts` | `tools2/base.py` | ✅ |

**结论：Tool 系统覆盖率约 75%**，基础工具齐全，缺 plan/task/lsp 三个关键工具。

---

### 2.3 Permission 系统

| 子功能 | OpenCode | CScode | 状态 |
|-------|----------|--------|------|
| 权限管理器 | `core/permission.ts` + `core/permission/saved.ts` + `core/permission/sql.ts` | `core/permission_v2.py` + `core/permissions.py` | ⚠️ 部分 |
| 权限评估 | `opencode/src/permission/evaluate.ts` + `arity.ts` | `core/permission_v2.py`（部分） | ⚠️ 部分 |
| 已保存权限 | `core/permission/saved.ts` + SQL 表 | ❌ 无持久化 | **缺失** |
| 权限策略联动 | `core/policy.ts` | ❌ 无 | **缺失** |
| Question 流程 | `core/question.ts` + `protocol/groups/question.ts` | `tools2/question.py` + `server/question_registry.py` | ✅ 已对齐 |

**结论：Permission 系统覆盖率约 50%**，Question 流程已对齐，但 saved-permission 持久化、policy 联动缺失。

---

### 2.4 Config 系统

| 子功能 | OpenCode | CScode | 状态 |
|-------|----------|--------|------|
| 主配置 | `core/config.ts` + `opencode/src/config/config.ts` | `core/config.py` + `core/config_v2.py` + `core/config_variable.py` | ✅ 已对齐 |
| Agent 配置 | `core/config/agent.ts` | ❌ 无（hardcode） | 缺失 |
| LSP 配置 | `core/config/lsp.ts` | ❌ 无 | 缺失 |
| MCP 配置 | `core/config/mcp.ts` | ❌ 无 | 缺失 |
| Plugin 配置 | `core/config/plugin.ts` + `opencode/src/config/plugin.ts` | `plugins/manifest.py`（部分） | ⚠️ 部分 |
| Provider 配置 | `core/config/provider.ts` | `core/config.py`（部分） | ⚠️ 部分 |
| Reference 配置 | `core/config/reference.ts` | ❌ 无 | 缺失 |
| Tool 输出配置 | `core/config/tool-output.ts` | ❌ 无 | 缺失 |
| Watcher | `core/config/watcher.ts` | `core/config_scanner.py`（部分） | ⚠️ 部分 |
| **Attachments** | `core/config/attachments.ts` | ❌ 无 | **缺失** |
| **Compaction** | `core/config/compaction.ts` | ❌ 无 | **缺失** |
| **Experimental** | `core/config/experimental.ts` | ❌ 无 | **缺失** |
| **Formatter** | `core/config/formatter.ts` | ❌ 无 | **缺失** |
| **Markdown** | `core/config/markdown.ts` | ❌ 无 | **缺失** |
| **TUI 配置** | `opencode/src/config/tui.ts` + `tui-cwd.ts` + `tui-host-attention.ts` + `tui-migrate.ts` | `tui/themes.py`（部分） | ⚠️ 部分 |
| Variable 解析 | `opencode/src/config/variable.ts` | `core/config_variable.py` | ✅ |
| Paths 管理 | `opencode/src/config/paths.ts` | `core/config.py`（部分） | ⚠️ |

**结论：Config 系统覆盖率约 40%**，主配置已对齐，缺 attachments/compaction/experimental/formatter/markdown 等子配置。

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
| PTY Handler | `opencode/src/server/routes/instance/httpapi/handlers/pty.ts` | ❌ 无 |
| PTY Environment | `opencode/src/plugin/pty-environment.ts` | ❌ 无 |

**结论：PTY 系统覆盖率 0%**，长时会话、共享终端、外部 PTY 客户端完全不支持。

---

### 2.6 Integration 系统（完全缺失）

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Integration 主模块 | `core/integration.ts` | ❌ 无 |
| Connection | `core/integration/connection.ts` | ❌ 无 |
| API Group | `protocol/groups/integration.ts` | ❌ 无 |

**结论：Integration 系统覆盖率 0%**，无法与外部 IDE/WebSocket 客户端建立持久连接。

---

### 2.7 Credential 系统（完全缺失）

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Credential 主模块 | `core/credential.ts` | ❌ 无 |
| Credential SQL | `core/credential/sql.ts` | ❌ 无 |
| API Group | `protocol/groups/credential.ts` | ❌ 无 |
| OAuth 令牌管理 | `core/oauth/page.ts` + `opencode/src/mcp/auth.ts` + `oauth-callback.ts` + `oauth-provider.ts` | ❌ 无 |

**结论：Credential 系统覆盖率 0%**，凭证只能存环境变量，无法持久化、轮换、共享。

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
| Project VCS | `opencode/src/project/vcs.ts` | `git/`（部分） | ⚠️ 部分 |
| Workspace Routing | `opencode/src/server/shared/workspace-routing.ts` + `middleware/workspace-routing.ts` | ❌ 无 |
| Worktree | `opencode/src/worktree/index.ts` | ❌ 无 |

**结论：Project/Workspace 系统覆盖率 0%**（VCS 部分除外），无法管理多项目、多工作区。

---

### 2.9 Filesystem 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Filesystem 主模块 | `core/filesystem.ts` | `tools2/ls.py` 等（散落） |
| FFF Bun | `core/filesystem/fff.bun.ts` | ❌ 无 |
| FFF Node | `core/filesystem/fff.node.ts` | ❌ 无 |
| **Ignore 规则** | `core/filesystem/ignore.ts` | ❌ 无 |
| **Protected 路径** | `core/filesystem/protected.ts` | ❌ 无 |
| **Watcher** | `core/filesystem/watcher.ts` | ❌ 无 |
| **Search** | `core/filesystem/search.ts` | ❌ 无 |
| File mutation | `core/file-mutation.ts` | ❌ 无 |
| File | `core/file.ts` | ❌ 无 |
| FS Util | `core/fs-util.ts` | ❌ 无 |
| Ripgrep | `core/ripgrep.ts` + `ripgrep/binary.ts` | `tools2/grep.py`（部分） | ⚠️ |
| API Group | `protocol/groups/fs.ts` | ❌ 无 |
| File Handler | `opencode/src/server/routes/instance/httpapi/handlers/fs.ts` + `server/src/handlers/fs.ts` | ❌ 无 |
| Patch | `core/patch.ts` + `opencode/src/patch/index.ts` | `tools2/apply_patch.py`（部分） | ⚠️ |
| Snapshot | `core/snapshot.ts` + `opencode/src/snapshot/index.ts` | `git/snapshot.py`（部分） | ⚠️ |
| Git | `core/git.ts` + `opencode/src/git/index.ts` | `git/` | ✅ |

**结论：Filesystem 系统覆盖率约 20%**，缺 ignore/protected/watcher/search 等关键能力。

---

### 2.10 Agent 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Agent 主模块 | `core/agent.ts` + `opencode/src/agent/agent.ts` | `app/agent.py` |
| Sub-agent | `core/sub_agent.py`（CScode） / `opencode/src/agent/subagent-permissions.ts` | `core/sub_agent.py` | ⚠️ 部分 |
| **Prompt 模板** | `agent/prompt/compaction.txt` + `explore.txt` + `summary.txt` + `title.txt` + `generate.txt` | ❌ 无 | **缺失** |
| Agent ID | `schema/agent.ts` | ❌ 无 | 缺失 |
| Agent API Group | `protocol/groups/agent.ts` | ❌ 无 | 缺失 |
| Plugin Agent | `core/plugin/agent.ts` | ❌ 无 | 缺失 |
| Agent Config | `core/config/agent.ts` | ❌ 无 | 缺失 |
| ACP Agent | `opencode/src/acp/agent.ts` | `acp/protocol.py`（部分） | ⚠️ |

**结论：Agent 系统覆盖率约 30%**，仅基础 Agent 调用对齐，缺 prompt 模板、subagent-permissions、agent config。

---

### 2.11 Model / Provider 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Model 主模块 | `core/model.ts` | `llm/client.py`（部分） | ⚠️ |
| Provider 主模块 | `core/provider.ts` + `opencode/src/provider/provider.ts` | `providers/` | ✅ |
| Provider 状态 | `opencode/src/provider/model-status.ts` + `provider.ts` | ❌ 无 | 缺失 |
| Provider Auth | `opencode/src/provider/auth.ts` | `auth/`（部分） | ⚠️ |
| Provider Error | `opencode/src/provider/error.ts` | `core/errors.py`（通用） | ⚠️ |
| Provider Transform | `opencode/src/provider/transform.ts` | `llm/route.py`（部分） | ⚠️ |
| Models Dev | `core/models-dev.ts` | ❌ 无 | 缺失 |
| Catalog | `core/catalog.ts` + `schema/catalog.ts` | ❌ 无 | 缺失 |
| AISDK | `core/aisdk.ts` | ❌ 无 | 缺失 |
| Model API Group | `protocol/groups/model.ts` | ❌ 无 | 缺失 |
| Provider API Group | `protocol/groups/provider.ts` | ❌ 无 | 缺失 |
| Plugin Provider（30+） | `core/plugin/provider/`（alibaba/anthropic/azure/bedrock/cohere/grok/mistral/nvidia/openrouter/perplexity/vertex/xai…） | `providers/`（6 个） | ⚠️ 仅 20% |

**结论：Model/Provider 系统覆盖率约 25%**，仅 6 个 provider 实现，缺 catalog/models-dev/aisdk/model-status。

---

### 2.12 Question 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Question 主模块 | `core/question.ts` | `tools2/question.py` |
| Question Schema | `schema/question.ts` | `schema/options.py`（部分） | ⚠️ |
| Question Index | `opencode/src/question/index.ts` + `schema.ts` | `server/question_registry.py` | ✅ |
| Question API Group | `protocol/groups/question.ts` | `/api/sessions/{id}/questions` | ✅ |
| Question Handler | `opencode/src/server/.../handlers/question.ts` | `server/app.py`（部分） | ⚠️ |
| Question Tool | `opencode/src/tool/question.ts` + `question.txt` | `tools2/question.py` | ✅ |

**结论：Question 系统覆盖率约 70%**，已基本对齐。

---

### 2.13 Skill 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Skill 主模块 | `core/skill.ts` + `opencode/src/skill/index.ts` | `skills/loader.py` |
| **Skill Discovery** | `core/skill/discovery.ts` + `opencode/src/skill/discovery.ts` | ❌ 无 | **缺失** |
| **Skill Guidance** | `core/skill/guidance.ts` + `core/reference/guidance.ts` | ❌ 无 | **缺失** |
| Skill API Group | `protocol/groups/skill.ts` | ❌ 无 | 缺失 |
| Skill Tool | `opencode/src/tool/skill.ts` + `skill.txt` | `tools2/skill.py` | ✅ |
| Skill Config | `core/config/skill/` | ❌ 无 | 缺失 |
| Plugin Skill | `core/plugin/skill.ts` | ❌ 无 | 缺失 |

**结论：Skill 系统覆盖率约 30%**，仅 loader 和 tool 对齐，缺 discovery/guidance/config。

---

### 2.14 Plugin 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Plugin 主模块 | `core/plugin.ts` + `opencode/src/plugin/index.ts` | `plugins/` |
| Plugin Host | `core/plugin/host.ts` | `plugins/loader.py`（部分） | ⚠️ |
| Plugin Command | `core/plugin/command.ts` + `opencode/src/command/` | `plugins/hooks.py`（部分） | ⚠️ |
| Plugin Agent | `core/plugin/agent.ts` | ❌ 无 | 缺失 |
| Plugin Skill | `core/plugin/skill.ts` | ❌ 无 | 缺失 |
| **Plugin Provider（30+）** | `core/plugin/provider/` | ❌ 无 | **完全缺失** |
| Plugin Internal | `core/plugin/internal.ts` | ❌ 无 | 缺失 |
| Plugin Promise | `core/plugin/promise.ts` | ❌ 无 | 缺失 |
| Plugin Variant | `core/plugin/variant.ts` | ❌ 无 | 缺失 |
| Plugin Models Dev | `core/plugin/models-dev.ts` | ❌ 无 | 缺失 |
| Plugin Loader（opencode） | `opencode/src/plugin/loader.ts` + `install.ts` + `meta.ts` + `shared.ts` | `plugins/loader.py` | ⚠️ |
| Plugin TUI | `opencode/src/plugin/tui/` | ❌ 无 | 缺失 |
| Plugin Package | `packages/plugin/`（独立 npm 包） | ❌ 无 | 缺失 |

**结论：Plugin 系统覆盖率约 15%**，仅基础 loader 和 hooks，缺 30+ 内置 provider 插件、command 模板、TUI 集成。

---

### 2.15 Event 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Event 主模块 | `core/event.ts` | `core/events.py` |
| Event SQL | `core/event/sql.ts` | `storage/event_store.py` | ✅ |
| Event Schema | `schema/event.ts` + `session-event.ts` + `ide-event.ts` + `lsp-event.ts` + `mcp-event.ts` + `tui-event.ts` + `vcs-event.ts` | `schema/events.py` | ⚠️ 部分 |
| Event API Group | `protocol/groups/event.ts` | `/api/sessions/{id}/events` | ✅ |
| Event V2 Bridge | `opencode/src/event-v2-bridge.ts` | ❌ 无 | 缺失 |
| Public Event Manifest | `core/public-event-manifest.ts` + `opencode/src/event-manifest.ts` | ❌ 无 | 缺失 |
| Event Projectors | `opencode/src/server/projectors.ts` + `init-projectors.ts` | `server/projector.py` | ✅ |
| Event Bus | `opencode/src/bus/global.ts` | ❌ 无 | 缺失 |

**结论：Event 系统覆盖率约 60%**，已基本对齐，缺 v2-bridge、public-manifest、event-bus。

---

### 2.16 Database 系统

| 子功能 | OpenCode | CScode |
|-------|----------|--------|
| Database 主模块 | `core/database/database.ts` | `storage/db.py` |
| Migration 系统 | `core/database/migration/`（37 个 migration 文件） + `migration.gen.ts` + `migration.ts` | `storage/migration.py` + `migration_runner.py` + `data_migration.py` | ⚠️ 部分 |
| Path 管理 | `core/database/path.ts` | `storage/db.py`（部分） | ⚠️ |
| Schema | `core/database/schema.gen.ts` + `schema.sql.ts` | ❌ 无 schema.gen | 缺失 |
| SQLite Bun | `core/database/sqlite.bun.ts` | ❌ 无 | 缺失 |
| SQLite Node | `core/database/sqlite.node.ts` | `storage/db.py`（sqlite3） | ✅ |
| SQLite 抽象 | `core/database/sqlite.ts` | `storage/db.py` | ✅ |
| Drizzle 配置 | `core/drizzle.config.ts` | ❌ 无 | 缺失 |

**结论：Database 系统覆盖率约 50%**，基础已对齐，但 OpenCode 有 37 个 migration（涵盖 workspace/session-message-cursor/events/session-usage/data-migration-state/session-metadata/context-epoch 等），CScode 的 migration 数量远少。

---

## 3. API 端点对比

### 3.1 OpenCode Protocol API Groups（18 个，`packages/protocol/src/groups/`）

| Group | 端点示例 | CScode 是否有等价端点 |
|-------|---------|----------------------|
| session | `/api/session` GET/POST、`/api/session/{id}` GET/PATCH/DELETE、`/api/session/{id}/message`、`/api/session/{id}/event`、`/api/session/{id}/summarize`、`/api/session/{id}/revert`、`/api/session/{id}/share`、`/api/session/{id}/input` | ⚠️ 部分（缺 revert/share/input/summarize） |
| message | `/api/session/{id}/message/{mid}` GET/DELETE、`/api/session/{id}/message/{mid}/feedback` | ⚠️ 部分（缺 feedback） |
| event | `/api/event` GET、`/api/event/{id}` | ✅ |
| agent | `/api/agent` GET、`/api/agent/{id}` | ❌ 无 |
| command | `/api/command` | ❌ 无 |
| credential | `/api/credential` CRUD | ❌ 无 |
| integration | `/api/integration` CRUD | ❌ 无 |
| location | `/api/location` CRUD | ❌ 无 |
| model | `/api/model` GET | ❌ 无 |
| provider | `/api/provider` CRUD | ❌ 无 |
| permission | `/api/permission` CRUD、`/api/permission/saved` | ❌ 无 |
| project-copy | `/api/project/copy` | ❌ 无 |
| pty | `/api/pty` CRUD、`/api/pty/{id}/resize`、`/api/pty/{id}/data` | ❌ 无 |
| question | `/api/session/{id}/question` | ✅ |
| reference | `/api/reference` | ❌ 无 |
| skill | `/api/skill` GET | ❌ 无 |
| fs | `/api/fs`（ls/read/write） | ❌ 无 |
| health | `/api/health` | ⚠️ 部分 |

### 3.2 OpenCode Instance HTTP API Groups（21 个，`opencode/src/server/routes/instance/httpapi/groups/`）

config、control-plane、control、event、experimental、file、global、instance、mcp、metadata、permission、project-copy、project、provider、pty、query、question、session、sync、tui、workspace

CScode 等价端点只有 ~19 个，覆盖：session（部分）、event（部分）、question（部分）、config（部分）、health。

**API 端点覆盖率约 30%**。

---

## 4. 前端功能对比

| 模块 | OpenCode | CScode | 状态 |
|------|----------|--------|------|
| Web App | `packages/app/`（context: file/mcp/sdk/sync/tabs、i18n: 18 国、pages、utils、wsl） | `src/cscode/web/`（components/hooks/lib/stores/themes） | ⚠️ 部分 |
| TUI | `packages/tui/`（config/context/plugin/prompt/routes/theme/ui/util + app/attention/audio/clipboard/editor/editor-zed/keymap/logo/runtime） | `src/cscode/tui/`（app/themes） | ⚠️ 部分 |
| Desktop | `packages/desktop/`（main: apps/ipc/menu） | `desktop/src-tauri/`（Rust + Tauri） | ⚠️ 部分 |
| UI 组件库 | `packages/ui/`（components/context/hooks/i18n/styles/theme） | 复用 web/ | ⚠️ 部分 |
| Session UI | `packages/session-ui/`（独立包） | ❌ 无 | 缺失 |
| Storybook | `packages/storybook/` | ❌ 无 | 缺失 |
| Stats App | `packages/stats/` | ❌ 无 | 缺失 |
| Console | `packages/console/` | ❌ 无 | 缺失 |
| Enterprise | `packages/enterprise/` | `src/cscode/enterprise/`（audit/policies/remote_config） | ⚠️ 部分 |
| Slack 集成 | `packages/slack/` | ❌ 无 | 缺失 |

**前端功能覆盖率约 40%**，主要缺 i18n 多语言、session-ui、storybook、stats、console、slack。

---

## 5. 优先级建议（四阶段路线图）

### P0 — 必须对齐（影响核心功能）

| 项 | 缺失内容 | 影响 |
|----|---------|------|
| **Tool: plan** | `tool/plan.ts` + plan-enter/exit.txt | LLM 无法进入规划模式 |
| **Tool: task** | `tool/task.ts` + task.txt | 无法委托子任务 |
| **Tool: lsp** | `tool/lsp.ts` + lsp.txt | LLM 无法利用 LSP 信息 |
| **Session: revert** | `core/session/revert.ts` + `schema/revert.ts` | 无法回滚会话 |
| **Session: compaction** | `core/session/compaction.ts` + compaction.txt | 上下文超长无法压缩 |
| **Session: input-inbox** | `core/session/input.ts` + event_sourced_session_input | 用户输入与 LLM 流并发冲突 |
| **Config: attachments** | `core/config/attachments.ts` | 文件附件无法配置 |
| **Config: compaction** | `core/config/compaction.ts` | 压缩策略无法配置 |
| **Permission: saved** | `core/permission/saved.ts` + SQL | 用户每次都要重新授权 |
| **Filesystem: ignore** | `core/filesystem/ignore.ts` | 工具误读 node_modules/.git |
| **Filesystem: protected** | `core/filesystem/protected.ts` | 工具误改关键系统文件 |
| **Provider: 状态管理** | `provider/model-status.ts` | 无法检测 provider 可用性 |

### P1 — 重要补充（影响扩展性）

| 项 | 缺失内容 | 影响 |
|----|---------|------|
| **Project/Workspace** | `core/project.ts` + `core/workspace.ts` + control-plane | 无法管理多项目 |
| **Credential 系统** | `core/credential.ts` + SQL + API | 凭证无法持久化 |
| **Plugin Provider 30+** | `core/plugin/provider/` | provider 生态薄弱 |
| **Agent Prompt 模板** | `agent/prompt/*.txt`（compaction/explore/summary/title/generate） | prompt 散落 hardcode |
| **Skill Discovery** | `core/skill/discovery.ts` | 技能无法自动发现 |
| **Catalog** | `core/catalog.ts` + `schema/catalog.ts` | 模型/Provider 目录缺失 |
| **Models Dev** | `core/models-dev.ts` | 无法从 models.dev 拉取 |
| **Filesystem: watcher** | `core/filesystem/watcher.ts` | 文件变更不感知 |
| **Filesystem: search** | `core/filesystem/search.ts` | 文件搜索能力弱 |
| **Background Job** | `core/background-job.ts` | 异步任务调度缺失 |
| **Sync 系统** | `opencode/src/sync/` | 多设备同步缺失 |
| **Config: experimental** | `core/config/experimental.ts` | 实验特性开关缺失 |
| **Config: formatter** | `core/config/formatter.ts` | 输出格式化缺失 |
| **Config: markdown** | `core/config/markdown.ts` | Markdown 渲染配置缺失 |
| **Config: tool-output** | `core/config/tool-output.ts` | 工具输出配置缺失 |
| **i18n 多语言** | `packages/app/src/i18n/`（18 国） | 仅支持中文 |

### P2 — 增强能力（可选）

| 项 | 缺失内容 |
|----|---------|
| PTY 系统 | `core/pty.ts` + `pty/` 子目录 + API + handler |
| Integration 系统 | `core/integration.ts` + API |
| Control-Plane | `core/control-plane/` + workspace adapter + worktree |
| Account 系统 | `core/account.ts` + SQL |
| Reference 系统 | `core/reference.ts` + guidance |
| Policy 系统 | `core/policy.ts` |
| Repository Cache | `core/repository-cache.ts` + `repository.ts` |
| Observability | `core/observability/`（logging/otlp） |
| NPM 集成 | `core/npm.ts` + `npm-config.ts` |
| Image 处理 | `core/image.ts` + `image/photon.ts` |
| GitHub Copilot 深度集成 | `core/github-copilot/`（chat + responses 全套） |
| Event V2 Bridge | `opencode/src/event-v2-bridge.ts` |
| Public Event Manifest | `core/public-event-manifest.ts` |
| Event Bus | `opencode/src/bus/global.ts` |
| Share Next | `opencode/src/share/share-next.ts` |
| TUI 完整 | `packages/tui/` 全套（routes/prompt/plugin/scrollback/attention/audio/clipboard/editor-zed） |
| Storybook | `packages/storybook/` |
| Stats App | `packages/stats/` |
| Console | `packages/console/` |
| Slack 集成 | `packages/slack/` |

### P3 — 长期演进

| 项 | 缺失内容 |
|----|---------|
| SDK 独立包 | `packages/sdk/` + `sdk-next/` |
| Client 独立包 | `packages/client/` |
| Plugin 独立 npm 包 | `packages/plugin/` |
| Container 集成 | `packages/containers/` |
| Function 集成 | `packages/function/` |
| Http Recorder | `packages/http-recorder/` |
| Installation/Version 管理 | `core/installation/` |
| Migration 全量对齐 | OpenCode 37 个 migration vs CScode 少量 |

---

## 6. 关键差距汇总

### 6.1 完全无对齐（13 个系统）

PTY、Integration、Credential、Project/Workspace、Revert、Control-Plane、Sync、Account、Background Job、Policy/Reference、Observability、NPM、Image、GitHub Copilot、Catalog、Installation、Repository Cache

### 6.2 部分对齐但功能不全（13 个系统）

Session、Tool、Permission、Config、Filesystem、Agent、Model/Provider、MCP、LSP、Plugin、Sharing、Skill、TUI

### 6.3 已基本对齐（3 个系统）

Question、Event、Database

### 6.4 CScode 多出（无对应需求）

- `tools/browser.py`（OpenCode 无浏览器工具，但有 mcp-websearch）
- `tools/ls.py`（OpenCode 用 glob）
- `tools/echo.py`（测试用）
- `enterprise/`（OpenCode 是独立 npm 包，CScode 是 Python 模块）
- `auth/`（CScode 独立实现，OpenCode 在 `opencode/src/auth/`）

---

## 7. 实施建议

### 7.1 第一阶段（P0，立即对齐）

1. 实现 `tool/plan.ts` 等价物 —— Python `tools2/plan.py`
2. 实现 `tool/task.ts` 等价物 —— Python `tools2/task.py`（已占位需补全）
3. 实现 `tool/lsp.ts` 等价物 —— Python `tools2/lsp.py`
4. 实现 `session/revert.ts` 等价物 —— Python `core/session_revert.py`
5. 实现 `session/compaction.ts` 等价物 —— Python `core/compaction.py`
6. 实现 `session/input.ts` 等价物 —— Python `core/input_inbox.py`
7. 实现 `permission/saved.ts` 等价物 —— Python `core/permission_saved.py` + SQL
8. 实现 `filesystem/ignore.ts` 等价物 —— Python `core/fs_ignore.py`
9. 实现 `filesystem/protected.ts` 等价物 —— Python `core/fs_protected.py`
10. 补全 `config/attachments.ts`、`config/compaction.ts` 等价物

### 7.2 第二阶段（P1，扩展性）

1. 实现 Project/Workspace 系统
2. 实现 Credential 系统
3. 补全 Plugin Provider（至少加 Bedrock/Cohere/Grok/Mistral/Nvidia/Perplexity/Vertex/XAI）
4. 抽离 Agent Prompt 模板（参考 `opencode/src/agent/prompt/*.txt`）
5. 实现 Skill Discovery
6. 实现 Catalog + Models Dev
7. 实现 Filesystem watcher/search
8. 补全 Config 子模块（experimental/formatter/markdown/tool-output）

### 7.3 第三阶段（P2，生态）

1. 实现 PTY 系统
2. 实现 Integration 系统
3. 实现 Control-Plane + Worktree
4. 实现 Sync 系统
5. 补全 i18n 多语言（至少英文/日文）
6. 补全 TUI 完整功能

### 7.4 第四阶段（P3，长期）

1. SDK/Client 独立包
2. Plugin 独立包
3. Observability
4. 全量 migration 对齐

---

## 8. 验证方法

完成每个阶段后，使用以下命令验证对齐度：

```bash
# 验证 OpenCode 端点定义
rg "HttpApiEndpoint\.(get|post|patch|delete|put)" github/opencode-full/packages/protocol/src/groups/ -c

# 验证 CScode 端点定义
rg "@app\.(get|post|patch|delete|put)" src/cscode/server/app.py -c

# 验证工具对齐
ls src/cscode/tools2/ | sort
ls github/opencode-full/packages/opencode/src/tool/*.ts | xargs -n1 basename | sort

# 验证 Provider 对齐
ls src/cscode/providers/ | sort
ls github/opencode-full/packages/core/src/plugin/provider/*.ts | xargs -n1 basename | sort

# 验证 Schema 对齐
ls src/cscode/schema/ | sort
ls github/opencode-full/packages/schema/src/*.ts | xargs -n1 basename | sort
```

---

## 9. 总结

CScode 当前与 OpenCode 1:1 功能对齐的整体覆盖率约为 **25%–35%**：

- **核心功能（Session/Tool/Event/Database）** 已基本对齐，可用
- **高级功能（Revert/Compaction/Input-inbox/Plan/Task/LSP）** 完全缺失，影响 LLM 长会话和复杂任务能力
- **生态功能（Project/Workspace/Credential/PTY/Integration/Sync/Plugin Provider）** 完全缺失，影响多项目多设备场景
- **辅助功能（i18n/Storybook/Stats/Console/Slack）** 缺失，影响用户体验和运维

建议按 P0 → P1 → P2 → P3 四阶段逐步对齐，P0 阶段（12 项）应在近期优先完成，以补齐 LLM 长会话和工具能力的关键短板。
