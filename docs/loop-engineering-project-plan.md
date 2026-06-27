# OpenCode Python 重写 - 全周期 Loop Engineering 方案

## 核心洞察

**当前问题：** CScode 有架构但不可用，存在大量 bug — 原因是 "快速实现，缺乏验证闭环"。

**解决方案：** 全周期 Loop Engineering — 每一个开发环节都使用带状态的、可验证的迭代循环。

---

## Loop Engineering 核心原则

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Loop Engineering 全周期模型                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐                 │
│   │  Plan   │───▶│Implement│───▶│  Test   │───▶│ Review  │                 │
│   └─────────┘    └─────────┘    └─────────┘    └─────────┘                 │
│       │                                                │                    │
│       │                  迭代 (迭代 until 满足 Stop 条件)                    │
│       │                        │                      │                     │
│       │◀───────────────────────┘                      │                     │
│       │                                                 ▼                    │
│       │                  ┌──────────────────────────────────┐              │
│       │                  │       STOP (满足条件)            │              │
│       │                  │  - 任务完成                       │              │
│       │                  │  - 成本超限                       │              │
│       │                  │  - 人力介入                       │              │
│       │                  │  - 最大迭代数                     │              │
│       │                  └──────────────────────────────────┘              │
│       │                                                 │                    │
│       │◀────────────────────────────────────────────────┘                    │
│       │                                                                   │
│       ▼                                                                   │
│   State Persistence (每次迭代记录状态)                                       │
│   Worktree Isolation (并行任务隔离)                                         │
│   Maker/Checker 分离 (写代码 ≠ 验证代码)                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Stop Conditions (每个 Loop 必须定义)

| 条件 | 说明 |
|------|------|
| **任务完成** | 验收标准全部满足 |
| **成本超限** | 超过 $15 USD 预算 |
| **人力介入** | 需要人工决策 |
| **最大迭代** | 10 次迭代上限 |

---

## 项目架构：两层 Loop

### 第一层：阶段 Loop (Phase Loop)

每个 Phase 是一个独立的 Loop：

```
Phase 0: 准备工作     → Loop("搭建开发环境")
Phase 1: 核心引擎     → Loop("实现 Agent 核心")
Phase 2: 工具系统     → Loop("重构 Tool 系统")
Phase 3: 插件系统     → Loop("实现 Plugin 系统")
Phase 4: 终端界面     → Loop("优化 TUI/CLI")
Phase 5: 桌面端       → Loop("增强 Desktop")
Phase 6: 服务端       → Loop("完善 Server")
```

### 第二层：任务 Loop (Task Loop)

每个 Task 内部也是一个完整的 Loop：

```
Task 1.1: Agent System
  ├── Plan: 定义验收标准
  ├── Implement: 写代码 (Maker)
  ├── Test: 验证功能 (Checker)  
  ├── Review: 代码审查
  └── (迭代 until Stop)
```

---

## 详细任务规划

### Phase 0: 准备工作
**Loop 名称：** "搭建开发环境 + 架构分析"

#### Task 0.1: 开发环境搭建
**验收标准：**
- [ ] OpenCode 源码克隆到 `opencode-ref/`
- [ ] 目录结构完整 `ls opencode-ref/packages/` 可见所有模块
- [ ] 本地 Python/Node/Rust 环境就绪

**Skills 加载：** `git-workflow-and-versioning`, `planning-and-task-breakdown`

**State 存储：** `.opencode/loop-state/phase-0-env.json`

---

#### Task 0.2: OpenCode 核心架构分析
**验收标准：**
- [ ] `packages/core` 分析完成 → 产出 `docs/refs/opencode-core-analysis.md`
- [ ] `packages/llm` 分析完成 → 产出 `docs/refs/opencode-llm-analysis.md`
- [ ] `packages/protocol` 分析完成 → 产出 `docs/refs/opencode-protocol-analysis.md`
- [ ] 模块依赖图绘制完成 → 产出 `docs/refs/opencode-dependency-graph.png`

**Skills 加载：** `planning-and-task-breakdown`, `source-driven-development`

**State 存储：** `.opencode/loop-state/phase-0-analysis.json`

---

### Phase 1: 核心引擎
**Loop 名称：** "重构 Agent 核心系统"

#### Task 1.1: Agent 架构重构
**验收标准：**
- [ ] 支持 Tab 键切换 build/plan agent
- [ ] Agent 决策逻辑与 OpenCode 一致
- [ ] 单元测试覆盖 > 80%
- [ ] 类型检查通过 (mypy)

**Skills 加载：** `test-driven-development`, `debugging-and-error-recovery`, `verification-before-completion`

**Loop 迭代示例：**
```
Iteration 1: 实现基础架构 → Test: 单元测试失败 (缺少实现)
Iteration 2: 实现 build agent → Test: 部分测试通过
Iteration 3: 实现 plan agent → Test: 测试通过
Iteration 4: Review: 代码审查 → 发现问题 → 修复
Iteration 5: 最终验证 → Stop (任务完成)
```

**State 存储：** `.opencode/loop-state/phase-1-agent.json`

---

#### Task 1.2: LLM Provider 补全
**验收标准：**
- [ ] 支持所有主流模型 (OpenAI, Anthropic, Gemini, Ollama, Azure, OpenRouter)
- [ ] Function Calling 测试通过
- [ ] 流式响应正确处理
- [ ] 错误处理完善

**Skills 加载：** `test-driven-development`, `code-review-and-quality`

**State 存储：** `.opencode/loop-state/phase-1-llm.json`

---

#### Task 1.3: Session 管理增强
**验收标准：**
- [ ] Session 可完整恢复
- [ ] 上下文压缩功能正常
- [ ] Event Sourcing 持久化正确

**Skills 加载：** `test-driven-development`, `incremental-implementation`

**State 存储：** `.opencode/loop-state/phase-1-session.json`

---

### Phase 2: Tool System
**Loop 名称：** "重构工具系统"

#### Task 2.1: Tool Core 重写
**验收标准：**
- [ ] Tool 基类重构完成
- [ ] Tool 注册机制工作正常
- [ ] 与 OpenCode tool 定义兼容

**Skills 加载：** `test-driven-development`, `code-review-and-quality`

---

#### Task 2.2: 核心工具优化
**验收标准：**
- [ ] Read/Edit/Write 工具行为与 OpenCode 一致
- [ ] Bash 工具正确执行和返回
- [ ] Grep/Glob 工具性能达标
- [ ] WebFetch/WebSearch 工具正常工作

**Skills 加载：** `debugging-and-error-recovery`, `verification-before-completion`

---

#### Task 2.3: 高级工具集
**验收标准：**
- [ ] Task 工具 (子 agent 调度) 工作正常
- [ ] Skill 工具 (技能加载) 工作正常
- [ ] MCP 工具集成正常

---

### Phase 3: Plugin 系统
**Loop 名称：** "重构插件系统"

#### Task 3.1: Plugin Core
**验收标准：**
- [ ] Plugin manifest 解析正确
- [ ] 动态加载机制工作正常
- [ ] 与 OpenCode plugin 格式兼容

**Skills 加载：** `spec-driven-development`, `security-and-hardening`

---

#### Task 3.2: 内置插件
**验收标准：**
- [ ] Git 插件增强功能正常
- [ ] LSP 插件正常工作
- [ ] MCP 插件集成正常

---

### Phase 4: TUI/CLI
**Loop 名称：** "优化终端界面"

#### Task 4.1: Console UI 优化
**验收标准：**
- [ ] TUI 布局与 OpenCode 一致
- [ ] 消息渲染正确
- [ ] 响应式布局正常
- [ ] Visual QA 通过

**Skills 加载：** `visual-qa`, `frontend-ui-architecture`

---

#### Task 4.2: CLI 增强
**验收标准：**
- [ ] 交互式模式工作正常
- [ ] Agent 切换功能正常
- [ ] 配置管理功能正常

---

### Phase 5: Desktop/Web
**Loop 名称：** "增强桌面端"

#### Task 5.1: Desktop App
**验收标准：**
- [ ] 集成新 Agent 核心
- [ ] 性能优化达标
- [ ] 无阻塞 bug

**Skills 加载：** `visual-qa`, `frontend-ui-architecture`, `performance-optimization`

---

#### Task 5.2: Web UI (可选)
**验收标准：**
- [ ] Web 会话界面功能完整
- [ ] 实时协作正常 (可选)

---

### Phase 6: Server & Cloud
**Loop 名称：** "完善服务端"

#### Task 6.1: API 扩展
**验收标准：**
- [ ] OpenAPI 端点完整
- [ ] 认证/鉴权正常工作
- [ ] 用量统计准确

**Skills 加载：** `security-review`, `api-and-interface-design`

---

#### Task 6.2: Enterprise 功能
**验收标准：**
- [ ] 团队管理功能正常
- [ ] 策略控制生效
- [ ] 审计日志完整

---

## 依赖执行图

```yaml
Phase 0: 准备工作
    │
    ├── Task 0.1 (环境搭建)
    └── Task 0.2 (架构分析) ────┐
                                 │
Phase 1: 核心引擎 ◀──────────────┤
    │                             │
    ├── Task 1.1 (Agent) ◀───────┤
    ├── Task 1.2 (LLM)           │
    └── Task 1.3 (Session)       │
            │                    │
Phase 2: Tool System ◀───────────┤
    │                             │
    ├── Task 2.1 (Core) ◀────────┤
    ├── Task 2.2 (基础工具)       │
    └── Task 2.3 (高级工具)       │
            │                    │
Phase 3: Plugin ◀────────────────┤
    │                             │
    ├── Task 3.1 (Core) ◀────────┤
    └── Task 3.2 (内置插件)       │
            │                    │
Phase 4: TUI/CLI ◀───────────────┤
    │                             │
    ├── Task 4.1 (TUI) ◀─────────┤
    └── Task 4.2 (CLI)           │
            │                    │
Phase 5: Desktop ◀───────────────┤
    │                             │
    ├── Task 5.1 (Desktop) ◀─────┤
    └── Task 5.2 (Web UI)        │
            │                    │
Phase 6: Server ◀────────────────┘
    │
    ├── Task 6.1 (API) ◀─────────┐
    └── Task 6.2 (Enterprise) ───┘
```

---

## 关键命令速查

### 启动 Loop

```bash
/loop:dev "Phase 1: 实现 Agent 核心"
/loop:bug "修复 Session 恢复问题"
/loop:status
/loop:resume <loop-id>
/loop:stop <loop-id>
```

### 任务规划

```bash
/ulw-Plan "重构 Tool System"
```

### 代码审查

```bash
/review-work
/security-review
```

### 视觉验证

```bash
/visual-qa
```

### 调试

```bash
/debugging
```

---

## Skills 强制加载清单

| Phase | 必须加载的 Skills |
|-------|------------------|
| Phase 0 | `planning-and-task-breakdown`, `git-workflow-and-versioning` |
| Phase 1 | `test-driven-development`, `debugging-and-error-recovery`, `verification-before-completion` |
| Phase 2 | `test-driven-development`, `code-review-and-quality`, `incremental-implementation` |
| Phase 3 | `spec-driven-development`, `security-and-hardening`, `code-review-and-quality` |
| Phase 4 | `visual-qa`, `frontend-ui-architecture` |
| Phase 5 | `visual-qa`, `performance-optimization` |
| Phase 6 | `security-review`, `api-and-interface-design` |

---

## 验收检查表 (每个 Task 结束)

- [ ] 所有测试通过 `pytest tests/`
- [ ] 类型检查通过 `mypy src/`
- [ ] 代码检查通过 `ruff check src/`
- [ ] 手动功能验证完成
- [ ] State 文件已保存
- [ ] Review 通过

---

## 风险管理

| 风险 | 影响 | 缓解 |
|------|------|------|
| 迭代成本超限 | 高 | 设置 $15/Task 成本上限 |
| 功能蔓延 | 高 | 明确 Stop Conditions |
| 验证遗漏 | 高 | Maker/Checker 必须分离 |
| 并行冲突 | 中 | Worktree Isolation |

---

## 文档结构

```
docs/
├── opencode-architecture-*.md      # Phase 0 分析产出
├── loop-engineering-project-plan.md # 本方案
└── loop-state/                      # 每次迭代状态
    ├── phase-0-env.json
    ├── phase-0-analysis.json
    ├── phase-1-agent.json
    └── ...
```