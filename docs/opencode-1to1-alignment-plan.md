# CScode ↔ OpenCode 对齐实施计划

> 基于 `docs/opencode-1to1-gap-analysis.md` (2026-07-04)
> 当前覆盖率: 42-50%
> 目标覆盖率: 80%+

---

## 阶段概览

| 阶段 | 覆盖率目标 | 周期 | 核心任务 |
|------|-----------|------|----------|
| **Phase P0** | 55% | 2-3周 | 8项关键短板 |
| **Phase P1** | 65% | 4-6周 | 15项扩展性功能 |
| **Phase P2** | 75% | 8-12周 | 18项增强能力 |
| **Phase P3** | 80%+ | 长期 | 10项演进目标 |

---

## Phase P0: 核心功能补齐 (8项)

### 目标
解决影响 LLM 长会话和工具能力的关键短板。

### 任务清单

#### P0-1: LSP 工具封装
- [ ] **现状**: 有 `lsp/manager.py` (LSPManager) + `lsp/client.py` (LSPClient)，但未暴露给 LLM
- [ ] **目标**: 封装为 `tools2/lsp.py` 工具
- [ ] **实现**:
  - 创建 `LSPTool` 类，调用 LSPManager 做代码分析
  - 支持: 诊断、悬停、定义、引用
  - 创建 `prompts/lsp.txt` 给 LLM 的指令
- [ ] **验证**: `pytest tests/test_lsp_tool.py`

#### P0-2: Session Revert
- [ ] **现状**: 无 revert 功能
- [ ] **目标**: 会话回滚 + `/revert` API
- [ ] **实现**:
  - 创建 `core/session_revert.py`
  - 添加 `/api/sessions/{id}/revert` 端点
  - 支持: 撤销上 N 条消息/工具调用
- [ ] **验证**: `pytest tests/test_session_revert.py`

#### P0-3: Session Input Inbox
- [ ] **现状**: 单条输入，无法处理并发
- [ ] **目标**: event-sourced session input 队列
- [ ] **实现**:
  - 创建 `core/session_input.py`
  - 添加 input 队列机制
  - 用户输入与 LLM 流不冲突
- [ ] **验证**: `pytest tests/test_session_input.py`

#### P0-4: Config Attachments
- [ ] **现状**: 缺附件配置
- [ ] **目标**: 文件附件完整流程
- [ ] **实现**:
  - 扩展 `ConfigV2` 添加 `AttachmentConfig`
  - 支持文件上传/下载 API
  - 消息中支持附件引用
- [ ] **验证**: `pytest tests/test_config_attachments.py`

#### P0-5: Filesystem Ignore
- [ ] **现状**: 工具误读 node_modules/.git
- [ ] **目标**: .gitignore / .opencodeignore 规则
- [ ] **实现**:
  - 创建 `core/fs_ignore.py`
  - 支持: .gitignore, .opencodeignore, 内置规则
  - 所有文件工具集成
- [ ] **验证**: `pytest tests/test_fs_ignore.py`

#### P0-6: Filesystem Protected
- [ ] **现状**: 可能误改系统文件
- [ ] **目标**: 受保护路径机制
- [ ] **实现**:
  - 创建 `core/fs_protected.py`
  - 默认保护: /usr, /System, ~/, .ssh, .env
  - 可配置白名单
- [ ] **验证**: `pytest tests/test_fs_protected.py`

#### P0-7: Agent Prompt 模板库
- [ ] **现状**: 15+ prompt 散落 hardcode 在 agent.py
- [ ] **目标**: 抽离为独立模板文件
- [ ] **实现**:
  - 创建 `prompts/` 目录
  - 模板: system.txt, compaction.txt, summary.txt, title.txt, explore.txt 等
  - `AgentFactory` 加载模板而非 hardcode
- [ ] **验证**: `pytest tests/test_prompt_templates.py`

#### P0-8: Provider Model Status
- [ ] **现状**: 无法检测 provider 可用性
- [ ] **目标**: provider 状态检测
- [ ] **实现**:
  - 扩展 `providers/base.py` 添加 `health_check()` 方法
  - 创建 `providers/status.py` 统一状态管理
  - 前端显示 provider 在线/离线状态
- [ ] **验证**: `pytest tests/test_provider_status.py`

### Checkpoint P0
- [ ] 8项全部完成
- [ ] pytest 通过
- [ ] ruff / mypy 清洁

---

## Phase P1: 扩展性功能 (15项)

### 任务清单

#### P1-1: Credential 系统
- [x] 创建 `core/credential.py` + SQL 表
- [x] 添加 `/api/credentials` CRUD
- [x] 支持 API key 存储、轮换

#### P1-2: Plugin Provider 扩充
- [x] 添加: Bedrock, Cohere, Grok, Mistral, Nvidia, Perplexity, Vertex, XAI
- [x] 目标: 从 6 个 → 14 个 provider

#### P1-3: Skill Guidance
- [x] 扩展 `skills/loader.py` 添加 guidance 生成
- [x] 支持 context-aware skill 建议

#### P1-4: Catalog 系统
- [x] 创建 `core/catalog.py`
- [x] 支持 model/provider/agent 目录
- [ ] 可选: 集成 models.dev (deferred)

#### P1-5: Filesystem Watcher
- [x] 创建 `core/fs_watcher.py`
- [x] 使用 watchdog 库
- [x] 通知 LLM 文件变更

#### P1-6: Config 子模块补全
- [x] 添加: experimental, formatter, markdown, tool-output, lsp, reference 配置

#### P1-7: Session Message Updater
- [x] 创建消息更新机制
- [x] 支持消息编辑/删除

#### P1-8: Session Summary
- [x] 创建 `core/session_summary.py`
- [x] 添加 `/api/sessions/{id}/summary` API
- [x] LLM 生成摘要

#### P1-9: Sharing 持久化
- [x] 分享链接持久化到数据库
- [x] 添加 `/api/share` CRUD

#### P1-10: MCP OAuth
- [x] 添加 mcp oauth-callback 处理
- [x] 支持 MCP 服务器 OAuth

#### P1-11: Background Job
- [x] 创建 `core/background_job.py`
- [x] 异步任务调度

#### P1-12: i18n 多语言
- [x] 引入 i18n 框架 (dict-based, light替代i18next)
- [x] 添加英文/中文支持

#### P1-13: Permission Session 级
- [x] SavedRules 支持 session 级别
- [x] 细粒度权限控制

#### P1-14: LSP Diagnostic
- [x] 扩展 LSP 工具支持 diagnostic
- [x] 前端显示错误/警告

#### P1-15: Auth 回调流程
- [x] 完整 OAuth 回调处理
- [x] token 刷新机制

### Checkpoint P1
- [x] 15项全部完成
- [x] pytest 通过 (137 tests)
- [x] ruff 清洁

---

## Phase P2: 增强能力 (18项)

| # | 功能 | 说明 |
|---|------|------|
| P2-1 | PTY 系统 | 伪终端、长时会话 |
| P2-2 | Integration 系统 | IDE/WebSocket 集成 |
| P2-3 | Project/Workspace | 多项目管理 |
| P2-4 | Control-Plane | worktree、move-session |
| P2-5 | Sync 系统 | 多设备同步 |
| P2-6 | Account 系统 | 账户管理 |
| P2-7 | Reference 系统 | 上下文引用 |
| P2-8 | Policy 系统 | 策略管理 |
| P2-9 | Repository Cache | 仓库缓存 |
| P2-10 | Observability | OTLP/日志 |
| P2-11 | NPM 集成 | npm 包发现 |
| P2-12 | GitHub Copilot | 深度集成 |
| P2-13 | Event V2 Bridge | 事件桥接 |
| P2-14 | Public Event Manifest | 事件清单 |
| P2-15 | Event Bus | 全局事件总线 |
| P2-16 | Share Next | 分享新方案 |
| P2-17 | TUI 完整化 | routes/prompt/slots |
| P2-18 | Storybook | 组件文档 |

---

## Phase P3: 长期演进 (10项)

| # | 功能 |
|---|------|
| P3-1 | SDK 独立包 |
| P3-2 | Client 独立包 |
| P3-3 | Plugin 独立 npm 包 |
| P3-4 | Container 集成 |
| P3-5 | Function 集成 |
| P3-6 | Http Recorder |
| P3-7 | Installation/Version 管理 |
| P3-8 | Migration 全量对齐 (37个) |
| P3-9 | Stats App / Console |
| P3-10 | Slack 集成 |

---

## 架构决策

### 1. 分层保持
```
schema → llm → core → app+server+web
```
不照搬 OpenCode 的 5 层，保持 CScode 的扁平架构。

### 2. 数据库迁移策略
- 每个 Phase 添加 1-2 个 migration
- 使用现有 `MigrationRegistry` 框架

### 3. 测试驱动
- 每个功能先写测试
- 保持 70+ 测试文件的覆盖率

### 4. 向后兼容
- ConfigV2 已支持 `to_legacy()` / `from_legacy()`
- 新功能同样保持兼容

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| P0 任务过大 | 超出 2-3 周 | 拆分为周粒度子任务 |
| Provider 扩充需要 API key | 测试困难 | 使用 mock 或 Ollama 本地 |
| i18n 工作量大 | 延期 | 先做中英文，框架可扩展 |
| PTY 系统复杂 | P2 延期 | 放到最后阶段 |

---

## 启动方式

选择启动方式：

1. **立即开始 P0** - 直接执行 Phase P0 的 8 项任务
2. **先验证 P0 范围** - 让我详细展开 P0-1 (LSP 工具) 的具体实现
3. **自定义优先级** - 调整 P0-P3 的顺序或范围

---

## 当前已对齐 (无需重复实现)

- Session V2 事件溯源
- Compaction + ContextCompressor
- Permission V2 + SavedRules
- Config V2 (7子配置+6层)
- Question 系统
- 18个 Tool (17个已对齐)
- LSP Manager (8语言)
- MCP Client/Server
- Agent V2 + Factory
- TaskTracker
- 前端 20+ 组件
- Git/Auth/Enterprise 模块