# OpenCode Python 重写项目实施方案

## 项目概述

用 Python 1:1 还原 OpenCode（TypeScript AI 编程助手），在现有 CScode 项目基础上，**利用 OpenCode 自身的增强能力**进行开发。

**核心策略：用 OpenCode 开发 OpenCode 自己**

**目标：** 完整功能（CLI + TUI + Desktop + Web + Agent 系统 + Plugin 系统）

**开发周期：** 长期（6个月+）

**开发方式：** 用 OpenCode 开发自己

---

## 开发模式：OpenCode 增强能力应用

```
┌─────────────────────────────────────────────────────────────────┐
│                    用 OpenCode 开发自己                          │
├─────────────────────────────────────────────────────────────────┤
│   规划 → 执行 → 验证 (循环迭代)                                   │
│    │       │       │                                            │
│    ▼       ▼       ▼                                            │
│ /ulw-Plan /loop:dev /review-work                                │
│ skills   skills   skills                                        │
│ - idea-refine    - TDD         - code-review                    │
│ - planning       - incremental - security                       │
│ - spec-driven    - worktree    - visual-qa                      │
└─────────────────────────────────────────────────────────────────┘
```

### 命令与技能清单

| 开发环节 | 使用命令 | 加载 Skills |
|---------|---------|------------|
| 需求分析 | `skill(idea-refine)` | brainstorming |
| 任务规划 | `/ulw-Plan` | planning-and-task-breakdown |
| 核心开发 | `/loop:dev` | test-driven, incremental-implementation |
| 代码审查 | `/review-work` | code-review-and-quality |
| 安全审计 | `/security-review` | security-research |
| UI 验证 | `/visual-qa` | visual-qa |
| 调试排错 | `/debugging` | debugging-and-error-recovery |

---

## 架构决策

### 技术栈映射

| OpenCode (TypeScript) | CScode (Python) 现状 | 目标实现 |
|-----------------------|---------------------|----------|
| `packages/core` | `src/cscode/core/` | 已有基础，需增强 |
| `packages/llm` | `src/cscode/providers/` | 已有 OpenAI/Anthropic，需补全 |
| `packages/agent` | `src/cscode/core/agent.py` | 已有基础 agent |
| `packages/tool` | `src/cscode/tools/` | 已有基础工具集 |
| `packages/plugin` | `src/cscode/plugins/` | 已有 plugin 系统 |
| `packages/tui` | `src/cscode/tui/` | 已有 Textual TUI |
| `packages/desktop` | `desktop/` | 已有 Tauri 桌面端 |
| `packages/server` | `src/cscode/server/` | 已有 FastAPI 后端 |
| `packages/session-ui` | 新增 | Web 会话界面 |
| `packages/docs` | `docs/` | 已有文档 |

### 架构模式

采用 **核心翻译 + 界面复用** 模式：
- Agent/LLM/Session 逻辑用 Python 重写
- Desktop/Web UI 复用现有 Tauri 桌面端
- Plugin 系统保持兼容

---

## 任务列表

### Phase 0: 准备工作
**OpenCode 能力:** `skill(idea-refine)` + `skill(ulw-Plan)`

#### Task 0.1: 搭建开发环境
- [ ] 克隆 OpenCode 仓库到本地 `opencode-ref/`
- [ ] 配置开发环境
- [ ] 验证源码完整性

**验证：** `ls opencode-ref/packages/` 可见所有模块

**使用能力:** 技能加载 `git-workflow-and-versioning`

#### Task 0.2: 架构分析
- [ ] 分析 `packages/core` - Agent 核心
- [ ] 分析 `packages/llm` - LLM 接口
- [ ] 分析 `packages/protocol` - 协议定义
- [ ] 绘制模块依赖图

**验证：** 产出 `docs/opencode-architecture-analysis.md`

**使用能力:** `skill(planning-and-task-breakdown)` 规划任务

---

### Phase 1: 核心引擎
**OpenCode 能力:** `/loop:dev` + `skill(test-driven-development)` + `skill(debugging-and-error-recovery)` + `skill(verification-before-completion)`

> **Loop Engineering 全周期应用**：每个 Task 都是一个完整的 Loop：Plan → Implement → Test → Review → (迭代 or Stop)

#### Task 1.1: Agent System 重写
- [ ] 分析 OpenCode `build` agent 实现
- [ ] 分析 `plan` agent 实现
- [ ] 重写 CScode agent 架构
- [ ] 实现多 agent 切换机制

**验收标准：**
- [ ] 支持 `Tab` 键切换 build/plan agent
- [ ] Agent 决策逻辑与 OpenCode 一致

**文件：** `src/cscode/core/agent.py`, `src/cscode/core/modes/`

#### Task 1.2: LLM Provider 补全
- [ ] 对标 OpenCode `packages/llm` 实现
- [ ] 补全 Claude/Opus 模型支持
- [ ] 实现流式响应处理
- [ ] 实现 Function Calling

**验收标准：**
- [ ] 支持所有主流模型
- [ ] Function Calling 测试通过

**文件：** `src/cscode/providers/`

#### Task 1.3: Session 管理增强
- [ ] 对标 OpenCode session 模型
- [ ] 实现 Event Sourcing 持久化
- [ ] 实现状态压缩/恢复

**验收标准：**
- [ ] Session 可完整恢复
- [ ] 支持上下文压缩

**文件：** `src/cscode/storage/session.py`

---

### Phase 2: Tool System
**OpenCode 能力:** `skill(incremental-implementation)` + `skill(code-review-and-quality)`

#### Task 2.1: Tool 基础设施
- [ ] 对标 OpenCode tool 定义
- [ ] 重写 tool 基类
- [ ] 实现 tool 注册机制

**文件：** `src/cscode/tools/base.py`

#### Task 2.2: 核心工具迁移
- [ ] Read/Edit/Write 工具优化
- [ ] Bash 工具增强
- [ ] Grep/Glob 工具优化
- [ ] WebFetch/WebSearch 工具

**验收标准：**
- [ ] 工具行为与 OpenCode 一致
- [ ] 性能达标

#### Task 2.3: 高级工具集
- [ ] Task 工具（子 agent 调度）
- [ ] Skill 工具（技能加载）
- [ ] MCP 工具集成

**文件：** `src/cscode/tools/task.py`, `src/cscode/tools/skill.py`

---

### Phase 3: Plugin 系统
**OpenCode 能力:** `skill(spec-driven-development)` + `skill(security-and-hardening)`

#### Task 3.1: Plugin Core 重写
- [ ] 分析 OpenCode `packages/plugin`
- [ ] 重写 plugin 加载器
- [ ] 实现 manifest 解析

**文件：** `src/cscode/plugins/loader.py`

#### Task 3.2: 内置插件
- [ ] Git 插件增强
- [ ] LSP 插件增强
- [ ] MCP 插件

**文件：** `src/cscode/plugins/`

---

### Phase 4: TUI/CLI
**OpenCode 能力:** `skill(visual-qa)` + `skill(frontend-ui-architecture)`

#### Task 4.1: Console UI 重写
- [ ] 对标 OpenCode `packages/console`
- [ ] 优化 TUI 布局
- [ ] 实现消息渲染增强

**文件：** `src/cscode/tui/app.py`

#### Task 4.2: CLI 增强
- [ ] 实现交互式模式
- [ ] 实现 agent 切换
- [ ] 实现配置管理

**文件：** `src/cscode/cli.py`

---

### Phase 5: Desktop/Web
**OpenCode 能力:** `skill(visual-qa)` + `skill(frontend-ui-architecture)`

#### Task 5.1: Desktop App 增强
- [ ] 集成新 Agent 核心
- [ ] 优化渲染性能
- [ ] 添加新功能

**文件：** `desktop/`

#### Task 5.2: Web UI（可选）
- [ ] 对标 OpenCode `packages/web`
- [ ] 实现 Web 会话界面
- [ ] 实现实时协作

---

### Phase 6: Server & Cloud
**OpenCode 能力:** `skill(security-review)` + `skill(api-and-interface-design)`

#### Task 6.1: API 扩展
- [ ] 扩展 OpenAPI 端点
- [ ] 实现认证/鉴权
- [ ] 实现用量统计

**文件：** `src/cscode/server/`

#### Task 6.2: Enterprise 功能
- [ ] 实现团队管理
- [ ] 实现策略控制
- [ ] 实现审计日志

**文件：** `src/cscode/enterprise/`

---

## 依赖图

```
OpenCode 源码分析
    │
    ├── Phase 1: 核心引擎
    │       ├── 1.1 Agent System ← 依赖 0.2
    │       ├── 1.2 LLM Provider ← 独立
    │       └── 1.3 Session 管理 ← 依赖 1.1
    │
    ├── Phase 2: Tool System
    │       ├── 2.1 Tool Core ← 依赖 1.1
    │       ├── 2.2 核心工具 ← 依赖 2.1
    │       └── 2.3 高级工具 ← 依赖 2.2
    │
    ├── Phase 3: Plugin
    │       └── 3.1-3.2 ← 依赖 2.1
    │
    ├── Phase 4: TUI/CLI ← 依赖 1,2,3
    │
    ├── Phase 5: Desktop ← 依赖 4
    │
    └── Phase 6: Server ← 依赖 1,2,3
```

---

## 风险与缓解

| 风险 | 影响 | 缓解策略 |
|------|------|----------|
| OpenCode 代码量大，14k+ commits | 高 | 分阶段，先核心后扩展 |
| TypeScript 特性难还原 | 中 | 用 Python 等效实现 |
| 同步维护两套代码 | 高 | 利用 OpenCode 自身开发 |
| 性能可能不如 TS | 低 | 优化热点路径 |

---

## Open Questions

- [ ] OpenCode 的 MCP 协议是否需要完全兼容？
- [ ] 是否需要支持 OpenCode 的云端同步功能？
- [ ] 企业版的定价/授权模式如何处理？

---

## 开发工作流

### 启动命令

```bash
# 启动开发循环（推荐）
/loop:dev "实现 Agent 核心模块"

# 复杂任务规划
/ulw-Plan "重构 Tool System"

# 代码审查
/review-work

# 安全审计
/security-review

# 视觉 QA（UI 完成后）
/visual-qa
```

### 强制 Skills 加载

每个阶段开始前，必须加载对应 skills：

```python
# 规划阶段
skill(name="planning-and-task-breakdown")
skill(name="idea-refine")

# 开发阶段  
skill(name="test-driven-development")
skill(name="incremental-implementation")

# 审查阶段
skill(name="code-review-and-quality")
skill(name="security-and-hardening")

# UI 阶段
skill(name="visual-qa")
skill(name="frontend-ui-architecture")

# 调试阶段
skill(name="debugging-and-error-recovery")
```

---

## 验收标准

每个 Phase 结束时：
- [ ] 功能对标 OpenCode 相应模块
- [ ] 测试覆盖核心逻辑
- [ ] 类型检查通过
- [ ] 性能达标

**最终目标：** CScode 能提供与 OpenCode 相当的功能体验，同时保持 Python 生态优势。