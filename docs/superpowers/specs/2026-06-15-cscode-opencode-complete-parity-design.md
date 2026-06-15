# CScode: OpenCode 完整功能复刻技术方案

## 1. 概述

### 1.1 目标
在现有 CScode (Python) 基础上，以"地基加固 + 系统性补齐"策略，1:1 还原 OpenCode v1.17+ 的全部核心能力，覆盖：
- 代理系统（子代理、Plan/Build 双模式、上下文压缩）
- 工具系统（权限控制、结构化输出）
- LLM 提供商（10+ 提供者，OAuth 认证）
- 插件系统（事件钩子体系）
- 协作（会话分享、链接、Git 审查）
- 企业级（远程配置、策略管理）

### 1.2 技术栈不变
- Python >= 3.11 + asyncio
- FastAPI + Uvicorn（后端 API）
- Textual（TUI）
- React + Vite（Web UI）
- Tauri v2（桌面）
- SQLite + aiosqlite（存储）

## 2. 架构升级

### 2.1 事件总线 (EventBus)
```
┌──────────────────────────────────────────────────┐
│                   EventBus                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Plugin A  │  │ Plugin B  │  │ Internal  │ ...  │
│  │ listener  │  │ listener  │  │ listeners │       │
│  └──────────┘  └──────────┘  └──────────┘       │
│  subscribe("tool.execute.before", fn)              │
│  subscribe("message.created", fn)                  │
│  emit("tool.execute.before", payload)              │
└──────────────────────────────────────────────────┘
```

事件类型（与 OpenCode 插件事件对齐）：
- `tool.execute.before` / `tool.execute.after`
- `session.created` / `session.deleted`
- `message.created` / `message.updated`
- `command.executed`
- `file.edited`
- `lsp.client.diagnostics`
- `permission.asked` / `permission.replied`

### 2.2 服务容器 (ServiceContainer)
管理所有服务的生命周期和依赖注入：
```
ServiceContainer
├── ConfigService
├── ProviderFactory
├── ToolRegistry
├── PermissionService
├── SessionManager
├── EventBus
├── PluginManager
├── LSPManager
├── MCPManager
└── StorageService
```

### 2.3 Agent 重构
单体 Agent → Mode-based Agent + SubAgentOrchestrator：

```
AgentOrchestrator
├── PlanAgent (read-only mode, no file writes)
├── BuildAgent (full access)
├── SubAgent (on @mention: explore, general, scout)
└── ContextCompressor (transparent msg compression)
```

### 2.4 权限系统
```
PermissionService
├── rules: {tool_name → allow|ask|deny}
├── bash_globs: {"git *": "ask", ...}
├── on_permission_asked → user prompt (CLI/TUI/Web/Desktop)
└── policy_overrides → enterprise IAM-style
```

## 3. 阶段计划

### Phase 0: 地基加固 (Week 1-2)

**任务 0.1: Bug 修复**
- 审查并修复现有 CLI/TUI/Server 中的已知问题
- 修复 engine.py 中 file_guard 的 edge cases
- 修复 session_manager.py 中异步回调的 event loop 问题
- 修复 provider 层的错误处理和重试逻辑

**任务 0.2: 测试覆盖**
- 为每个现有模块补充集成测试
- 添加端到端测试（CLI → Engine → Provider mock）
- 修复现有的 flaky tests

**任务 0.3: 代码质量**
- mypy strict mode 全面通过
- ruff 全部告警清理
- 统一错误处理模式
- 添加结构化日志

### Phase 1: 核心架构升级 (Week 3-5)

**任务 1.1: EventBus**
- `src/cscode/core/events.py` — 类型化事件系统
- 支持 sync/async listeners
- 支持一次性/持久订阅
- 支持事件优先级和过滤

**任务 1.2: PermissionService**
- `src/cscode/core/permissions.py`
- 规则引擎（allow/ask/deny + bash glob 匹配）
- 用户审批流（通过 question tool 或 UI 弹窗）
- Policy 覆盖（enterprise）

**任务 1.3: ServiceContainer**
- `src/cscode/core/container.py`
- 延迟初始化 + 生命周期管理
- 服务依赖自动解析
- 测试时可 mock 替换

**任务 1.4: Agent 重构**
- `src/cscode/core/agent.py` — AgentOrchestrator
- `src/cscode/core/modes/plan.py` — Plan mode（只读工具白名单）
- `src/cscode/core/modes/build.py` — Build mode（全部工具）
- `src/cscode/core/sub_agent.py` — SubAgentOrchestrator

**任务 1.5: Context Compression**
- `src/cscode/core/compression.py`
- 自动摘要（超过阈值触发）
- 可选择启用/禁用
- 可配置压缩策略

### Phase 2: 功能补齐 I (Week 6-8)

**任务 2.1: 工具系统增强**
- 添加 `webfetch`、`websearch`、`skill`、`todowrite`、`question` 工具
- `apply_patch` 工具（类 OpenCode 的 patch apply）
- 工具权限元数据

**任务 2.2: Provider 扩展**
- Google Gemini (`providers/gemini.py`)
- Azure OpenAI (`providers/azure.py`)
- OpenRouter (`providers/openrouter.py`)
- 本地模型 (Ollama 增强, llama.cpp)
- Models.dev 桥接 (聚合 75+ 提供者)

**任务 2.3: Git 集成**
- `src/cscode/git/` — 快照、diff、commit-aware review
- 每个会话操作自动 git snapshot
- TUI 中的 diff 可视化
- 文件变更追踪和回滚

**任务 2.4: 图片附件**
- 图片 auto-resize (Pillow)
- Base64 嵌入消息
- 支持多图片

**任务 2.5: 结构化输出**
- JSON Schema → LLM 响应验证
- 自动重试策略
- Type-safe result 解析

### Phase 3: 功能补齐 II (Week 9-11)

**任务 3.1: 插件系统增强**
- `src/cscode/plugins/` — 完整重构
- 事件钩子注册 (20+ event types)
- npm → Python 映射（插件来源：本地目录 + pip 包 + git repo）
- 插件 SDK 辅助类

**任务 3.2: 主题系统**
- `src/cscode/tui/themes.py`
- `web/src/themes/`
- 预设主题 + 自定义
- 配置持久化

**任务 3.3: SDK 包**
- `packages/sdk/` — `cscode-sdk` PyPI 包
- `create_cscode()` 编程式启动
- `CScodeClient()` 远程连接
- 类型安全 API（会话、文件、配置、事件流）

### Phase 4: 高级特性 (Week 12-14)

**任务 4.1: Auth/OAuth**
- `src/cscode/auth/` — GitHub OAuth, OpenAI OAuth
- Token 管理（加密存储、刷新）
- GitHub Copilot 认证流
- ChatGPT Plus/Pro 认证流

**任务 4.2: 会话分享**
- 会话序列化/反序列化
- 唯一链接生成
- 分享管理（公开/私密）

**任务 4.3: ACP 协议**
- Agent Communication Protocol
- 跨 agent 消息路由
- 分布式 agent 协作

**任务 4.4: 企业特性**
- 远程配置 (`.well-known/opencode` | `well-known/cscode`)
- MDM 配置 (`.mobileconfig`)
- IAM-style Policies
- 审计日志

## 4. 模块依赖图

```
Phase 0 ────────────────────────┐
                                ▼
Phase 1: EventBus ──→ PermissionService ──→ ServiceContainer
           │                                        │
           └────────── Agent Refactor ◄──────────────┘
                          │
                          ▼
                     Context Compression
                          │
                    ┌─────┴──────┐
Phase 2:            ▼            ▼
              Tool Enhancement   Git Integration
              Provider Expansion Image/Structured
                    │
                    ▼
Phase 3:    Plugin System + Theme + SDK
                    │
                    ▼
Phase 4:    Auth/OAuth + Sharing + ACP + Enterprise
```

## 5. 验收标准

每个 Phase 完成后需通过：
1. 所有现有测试通过
2. 新功能测试覆盖率 > 80%
3. mypy strict 无错误
4. ruff 无告警
5. CLI/TUI/Web/Desktop 四种交互方式均可正常使用新功能
6. 兼容 OpenCode 的配置/插件/SDK 接口语义
