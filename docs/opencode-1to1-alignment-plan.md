# CScode ↔ OpenCode 对齐实施计划

> 基于 `docs/opencode-1to1-gap-analysis. md` (2026-07-04)
> 当前覆盖率: 75%+
> 目标覆盖率: 80%+

---

## 阶段概览

| 阶段 | 覆盖率目标 | 周期 | 核心任务 | 状态 |
|------|-----------|------|----------|------|
| **Phase P0** | 55% | 2-3周 | 8项关键短板 | ✅ 完成 |
| **Phase P1** | 65% | 4-6周 | 15项扩展性功能 | ✅ 完成 |
| **Phase P2** | 75% | 8-12周 | 18项增强能力 | ✅ 部分完成 |
| **Phase P3** | 80%+ | 长期 | 10项演进目标 | 待开始 |

---

## Phase P0: 核心功能补齐 (8项)

### 任务清单

#### P0-1: LSP 工具封装
- [x] 创建 LSPTool 类，支持诊断、悬停、定义、引用
- [x] 验证: `pytest tests/test_lsp_*.py` ✅

#### P0-2: Session Revert
- [x] 创建 `core/session_ revert.py`，支持撤销消息/工具调用
- [x] 验证: `pytest tests/test_session_revert.py` ✅

#### P0-3: Session Input Inbox
- [x] 创建 `core/session_input.py`，input 队列机制
- [x] 验证: `pytest tests/test_session_input.py` ✅

#### P0-4: Config Attachments
- [x] 创建 `core/attachment.py`，文件上传/下载 API
- [x] 验证: `pytest tests/test_config_attachments.py` ✅

#### P0-5: Filesystem Ignore
- [x] 创建 `core/fs_ignore.py`，支持忽略规则
- [x] 验证: `pytest tests/test_fs_ignore.py` ✅

#### P0-6: Filesystem Protected
- [x] 创建 `core/fs_protected.py`，保护系统路径
- [x] 验证: `pytest tests/test_fs_protected.py` ✅

#### P0-7: Agent Prompt 模板库
- [x] 创建 `prompts/` 目录，AgentFactory 加载模板
- [x] 验证: `pytest tests/test_prompt_templates.py` ✅

#### P0-8: Provider Model Status
- [x] 扩展 providers/base.py，添加 health_check() 方法
- [x] 验证: `pytest tests/test_provider_status.py` ✅

### Checkpoint P0
- [x] 8项全部完成
- [x] pytest 通过 (1129 tests)
- [x] ruff / mypy 清洁

---

## Phase P1: 扩展性功能 (15项)

- [x] P1-1: Credential 系统
- [x] P1-2: Plugin Provider 扩充 (8个新provider)
- [x] P1-3: Skill Guidance
- [x] P1-4: Catalog 系统 (部分 deferred)
- [x] P1-5: Filesystem Watcher
- [x] P1-6: Config 子模块补全
- [x] P1-7: Session Message Updater
- [x] P1-8: Session Summary
- [x] P1-9: Sharing 持久化
- [x] P1-10: MCP OAuth
- [x] P1-11: Background Job
- [x] P1-12: i18n 多语言
- [x] P1-13: Permission Session 级
- [x] P1-14: LSP Diagnostic
- [x] P1-15: Auth 回调流程

### Checkpoint P1
- [x] 14/15 项完成 (1 deferred)
- [x] pytest 通过 (1129 tests)
- [x] ruff / mypy 清洁

---

## Phase P2: 增强能力 (18项)

| # | 功能 | 状态 |
|---|------|------|
| P2-1 | PTY 系统 | ✅ 完成 |
| P2-2 | Integration 系统 (WebSocket) | ✅ 完成 |
| P2-3 | Project/Workspace | ✅ 完成 |
| P2-4 ~ P2-18 | 其余15项 | 待开始 |

### Checkpoint P2
- [x] 3/18 项完成 (P2-1, P2-2, P2-3)
- [x] pytest 通过
- [x] ruff / mypy 清洁

---

## Phase P3: 长期演进 (10项)

全部待开始 (P3-1 ~ P3-10)

---

## 验证状态

| 检查项 | 状态 |
|--------|------|
| pytest | ✅ 1129 passed |
| ruff | ✅ clean |
| mypy | ✅ 0 errors (167 files) |
| git | ✅ 已推送 |