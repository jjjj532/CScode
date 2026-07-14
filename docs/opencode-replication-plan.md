# OpenCode v1.17.18 复刻差距分析 & 任务计划

> 生成时间: 2026-07-13  
> 基于 CodeGraph 索引: CScode (.codegraph, 6305 nodes) + opencode-dev-4 (.codegraph, 55072 nodes)  
> 对比版本: CScode v0.3.4 → OpenCode v1.17.18

---

## 一、总体架构对比

| 维度 | CScode | OpenCode |
|------|--------|----------|
| **语言** | Python + TypeScript + Rust | TypeScript (Bun monorepo) |
| **运行时** | Python 3.11+ | Bun 1.3.14 |
| **包管理** | pip/uv | Bun workspaces (33 packages) |
| **核心框架** | Python async/await | Effect.ts (函数式效应系统) |
| **LLM SDK** | 自研 provider 层 | Vercel AI SDK (@ai-sdk/*) |
| **Schema/验证** | Pydantic v2 | Effect Schema + Zod |
| **数据库** | SQLite (EventStore) | SQLite + Drizzle ORM |
| **CLI** | Click | yargs |
| **TUI** | Textual (Python) | OpenTUI + SolidJS |
| **Web UI** | React 18 + Vite + Tailwind | SolidJS + Astro + Tailwind |
| **桌面** | Tauri v2 (Rust) | Electron (SolidJS renderer) |
| **云平台** | 无 | SST + Cloudflare Workers |
| **CI/CD** | GitHub Actions | GitHub Actions + SST |
| **SDK** | Python SDK | TypeScript SDK (hey-api codegen) |
| **插件系统** | 简单 skill 加载 | Effect-based v2 plugin SDK |
| **MCP** | 自研 MCP client/server | @modelcontextprotocol/sdk |
| **IDE 集成** | VSCode extension? | LSP client + 内置 |

---

## 二、核心功能差距矩阵

### ✅ CScode 已有（需增强）

| 功能 | CScode | OpenCode | 差距 |
|------|--------|----------|------|
| 多 provider LLM | 15+ providers，自研 | 20+ providers via Vercel AI SDK | OpenCode 用统一 AI SDK，CScode provider 层需重塑 |
| 会话管理 | Session v2 + EventStore | SessionV2 + Event + Projector | 类似架构，但 OpenCode 更成熟（durable prompt, coordinator） |
| 工具系统 | tools/ 下独立文件 | Tool.make() + ToolRegistry + ApplicationTools | 架构类似，OpenCode 有 Materialization/Settlement 概念 |
| 文件工具 | read/write/edit/bash/grep/glob | 同上 + LSP + apply_patch | CScode 缺 LSP 工具 |
| 权限系统 | PermissionV2 | PermissionV2 + Ruleset | 架构对等 |
| Web UI | React + Zustand | SolidJS + @solidjs/router | 功能对等，技术栈不同 |
| TUI | Textual (Python) | OpenTUI + SolidJS | 功能对等，技术栈不同 |
| 桌面 | Tauri v2 (Rust) | Electron | 功能对等，技术栈不同 |
| MCP | 自研 client/server | @modelcontextprotocol/sdk | 需迁移到标准 SDK |
| 共享/同步 | SyncEngine | sync module | 功能对等 |

### 🔴 OpenCode 有、CScode 无（关键缺失）

| 功能 | OpenCode 实现 | CScode 状态 | 优先级 |
|------|---------------|-------------|--------|
| **Agent 系统** | `packages/core/src/agent.ts` — build/plan/subagent 三种 mode，Tab 切换，可配置 system prompt，颜色编码 | 无 | **P0** |
| **插件系统** | `packages/plugin/src/v2/` — Effect-based 生命周期，TUI plugin API (50+ hooks)，tool/command/skill/provider 注册 | 只有简单 skill loader | **P0** |
| **Console/云平台** | `packages/console/` — SolidStart + SST，多租户 workspace，billing，team 管理，用量追踪 | 无 | **P1** |
| **Enterprise 门户** | `packages/enterprise/` — 自托管部署，SSO，审计日志，policy 管理 | 无 | **P1** |
| **SDK 生成** | `packages/sdk/` — hey-api codegen from OpenAPI schema，JS/TS SDK | Python SDK 需手动维护 | **P1** |
| **ACP (Agent Connect Protocol)** | `packages/opencode/src/acp/` — session/agent/tool/permission ACP 实现 | 无 | **P1** |
| **LSP 集成** | `packages/opencode/src/lsp/` — 完整 LSP client，diagnostics，hover，completion | 无 | **P1** |
| **快照/压缩** | `packages/core/src/session/compaction.ts` — 会话快照 + 历史压实 | 无 | **P2** |
| **后台任务** | `packages/opencode/src/background/job.ts` — 后台作业系统 | 无 | **P2** |
| **工作树管理** | `packages/opencode/src/worktree/` — git worktree 管理 | 无 | **P2** |
| **Git 高级操作** | `packages/opencode/src/git/` — blame, bisect, log -S 等 | 基本 git 工具 | **P2** |
| **telemetry/stats** | `packages/stats/` — 用量追踪与报表 | 无 | **P2** |
| **Slack 集成** | `packages/slack/` — Slack bot 集成 | 无 | **P3** |
| **MCP OAuth** | `packages/opencode/src/mcp/` — OAuth provider/flow | 无 | **P2** |
| **跨机器同步** | `packages/opencode/src/sync/` — session 跨设备同步 | 有 SyncEngine 但只限本地 | **P2** |

---

## 三、分层复刻计划

### Phase 0: 基础设施适配 (2-3 周)

目标：将 OpenCode 的 TypeScript 包结构适配到 Python 生态，保留核心架构

```
CScode 新架构（Python 复刻版）:

src/cscode/
  schema/        # → @opencode-ai/schema   (Pydantic models + contracts)
  protocol/      # → @opencode-ai/protocol (REST API protocol defs)
  core/          # → @opencode-ai/core     (引擎重构)
    agent/       #   新增: Agent 系统
    plugin/      #   新增: Plugin host
    session/     #   增强: 新 session execution
    tool/        #   增强: ToolRegistry + Materialization
  llm/           # → @opencode-ai/llm      (统一 LLM 层)
  server/        # → @opencode-ai/server   (FastAPI 增强)
  cli/           # → opencode CLI          (命令扩展)
  tui/           # → @opencode-ai/tui      (保留 Textual 或迁移)
  web/           # → @opencode-ai/web      (React → SolidJS 或保留)
  plugins/       # 新增: 插件市场
```

#### 任务清单:
1. **OpenCode 核心 schema 移植** — 将 Effect Schema 翻译为 Pydantic v2 models
2. **Unified LLM 层** — 用 Vercel AI SDK Python 版 (ai-sdk-py) 替代自研 provider
3. **Drizzle → SQLAlchemy/Alembic** — 数据库迁移框架适配
4. **CLI 命令扩展** — 增加 agent/plugin/mcp/session 子命令

### Phase 1: 核心功能补齐 (4-6 周)

#### P0 任务：

1. **Agent 系统** (1-2 周)
   - `src/cscode/core/agent/` — AgentV2 架构移植
   - build/plan/subagent 三种 mode
   - Tab 切换支持 + 颜色编码
   - 可配置 system prompt 和 tool 白名单

2. **插件系统 v2** (2 周)
   - `src/cscode/core/plugin/` — Plugin host/service 架构
   - 基于 Effect 的插件生命周期（Python asyncio 等价）
   - TUI/CLI/Web 三层 plugin API
   - Tool/Command/Skill/Provider 注册 hooks
   - npm 包发现和安装

3. **Session 执行引擎增强** (1-2 周)
   - 引入 SessionExecution + Coordinator 模式
   - Durable prompt admission（prompt 先落盘再执行）
   - 多 session 并发执行支持
   - RunState 管理 (idle/running/error)

#### P1 任务：

4. **ACP (Agent Connect Protocol)** (1 周)
   - 实现 ACP session/agent/tool/permission
   - 兼容 @agentclientprotocol/sdk

5. **LSP 集成** (1 周)
   - 将现有 LSP 概念扩展为完整 client
   - diagnostics, hover, completion, references
   - TUI/Web 中显示 diagnostics

6. **SDK 自动生成** (1 周)
   - 从 FastAPI OpenAPI schema 自动生成 Python SDK
   - 可选: 多语言 SDK (JS/TS 等)

7. **快照/压缩系统** (3-5 天)
   - EventStore compaction
   - Session 快照创建和恢复

### Phase 2: 云平台 & 高级功能 (6-8 周)

8. **Console 云平台** (3-4 周)
   - SST 基础设施 (AWS CDK/Terraform 等价)
   - 多租户 workspace 管理
   - User/team/role 管理
   - Billing/用量追踪
   - Cloudflare Workers API (可换 FastAPI 部署)

9. **Enterprise 门户** (2-3 周)
   - SSO 集成 (OAuth/OpenID)
   - 审计日志
   - Policy 管理
   - 自托管部署脚本

10. **后台任务系统** (1 周)
    - BackgroundJob service
    - 异步任务队列
    - 进度追踪

### Phase 3: 生态集成 (4-6 周)

11. **MCP 标准 SDK 迁移** (1 周)
    - 切换到 @modelcontextprotocol/sdk
    - MCP OAuth 支持

12. **Slack 集成** (1 周)
    - Slack bot
    - 通知推送

13. **Git 增强** (1 周)
    - blame/bisect/log -S/git worktree

14. **跨机器同步** (1-2 周)
    - 增强 SyncEngine
    - 云端同步后端

15. **Telemetry/Stats** (1 周)
    - 用量统计
    - 报表仪表盘

---

## 四、架构决策要点

### 决策 1: 技术栈保留还是迁移？

| 组件 | 建议 | 理由 |
|------|------|------|
| Python 后端 | ✅ **保留** | 现有代码量大，Bun 迁移成本高 |
| React Web UI | ⚠️ **可选迁移** SolidJS | 功能对等，但 React 生态更成熟 |
| Textual TUI | ⚠️ **建议保留** | Textual 功能对标 OpenTUI |
| Tauri 桌面 | ✅ **保留** | Electron 更重，Tauri 更现代 |
| Vercel AI SDK | ✅ **引入 Python 版** | 统一 provider 接口 |

### 决策 2: Effect.ts 怎么处理？

Python 没有 Effect.ts 的直接等价物。建议：
- 使用 `structlog` + `anyio` + `result` 库组合模拟 Effect 模式
- 核心用 `asyncio` 原生 async/await
- 错误处理用 `Result[T, E]` 模式 (returns 库)

### 决策 3: Drizzle ORM 适配

Drizzle → `SQLAlchemy 2.0` + `Alembic` migrations
- 保持 snake_case 表/列命名
- 用 SQLAlchemy 的 `select()` 风格模拟 Drizzle query API

---

## 五、复刻优先级建议

```
Week 1-2:   Schema 移植 + CLI 扩展 + Agent 系统
Week 3-4:   插件系统 v2 + Session 引擎增强
Week 5-6:   ACP + LSP + SDK 生成
Week 7-8:   快照系统 + 后台任务
Week 9-12:  Console 云平台
Week 13-14: Enterprise 门户
Week 15-16: MCP 标准 + Slack + Git 增强
Week 17-18: 同步 + Telemetry
```

**Total: ~18 周 (4.5 个月)**，假设 1-2 人全职。

---

## 六、快速启动（MVP 1 个月）

如果只想快速缩短差距，建议聚焦 3 个最大价值：

1. **Agent 系统**（多 mode + Tab 切换）— 用户体验最明显
2. **插件系统 v2** — 生态扩展基础
3. **Session 执行引擎增强** — 稳定性和并发基础

这三个完成后，CScode 在核心能力上能达到 OpenCode ~70% 的功能覆盖率。
