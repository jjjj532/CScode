# 系统复刻开发方法论 — Loop Engineering 版

> 使用 OpenCode/Loop Engineering 进行跨语言系统复刻的完整指南
> 基于 CScode (Python) 复刻 OpenCode (TypeScript/Effect) 的实战经验总结
> 目标: 在任何编程语言中构建健壮、功能一致、无知识产权纠纷的等价系统
> 
> **核心差异:** 本文档不是 waterfall 方法论。6 个 Phase 是每个循环迭代内部的步骤。
> 你不在"完成 Phase 0"，你在"完成 Phase 0 的当前迭代"——然后根据结果决定下一轮迭代做什么。

---

> **⚡ AGENT 执行入口（智能体必读）**
> 
> 你是执行本方法论的智能体。按以下流程操作：
> 
> **第一步:** 读取状态文件，确认当前进度
> ```bash
> cat .opencode/loop-state/current.json
> # 如果文件不存在 → 初始化 state，从 Phase 0 开始
> ```
> 
> **第二步:** 根据 `phase` 字段跳转到对应章节：
> 
> | 状态文件 `phase` 值 | 跳转到 | 做什么 |
> |---------------------|--------|--------|
> | `Phase 0: ANALYSIS` | → [§3 Phase 0](#3-phase-0-被复刻系统的全维度分析) | 分析当前模块 |
> | `Phase 1: DEFINE` | → [§4 Phase 1](#4-phase-1-接口驱动的规格定义-define) | 定义接口 |
> | `Phase 2: PLAN` | → [§5 Phase 2](#5-phase-2-可执行的实施计划-plan) | 分解任务 |
> | `Phase 3: BUILD` | → [§6 Phase 3](#6-phase-3-分层实现-build) | 实现代码 |
> | `Phase 4: VERIFY` | → [§7 Phase 4](#7-phase-4-契约驱动的验证-verify) | 运行验证 |
> | `Phase 5: REVIEW` | → [§8 Phase 5](#8-phase-5-架构合规审查-review) | 审查 + Ratchet |
> | `Phase 6: SHIP` | → [§9 Phase 6](#9-phase-6-切换上线-ship) | 切换上线 |
> | `COMPLETED` | 结束 | 归档状态 |
> 
> **第三步:** 读 §1 核心原则（仅首次执行时读一次，后续跳过）
> 
> **第四步:** 执行目标章节的所有指令
> - 每个 Phase 顶部有 `🔄 循环上下文`——读它确认当前上下文
> - 每个 Phase 有 `🛠 本 Phase OpenCode 工具指引`——用对应的 OpenCode 工具
> - 每个 Phase 底部有 `🔄 循环出口`——按指示更新状态文件并跳转
> - 在 **Phase 4** 结束时检查停止条件（§2.3）
> - 在 **Phase 5** 结束时执行 Ratchet（§2.6）
> 
> **速查:** 最常用的命令和参数在 [§14 Loop 循环控制速查表](#14-loop-循环控制速查表)
> 
> ---

1. [核心原则](#1-核心原则)
2. [Loop Engineering 执行框架](#2-loop-engineering-执行框架)
3. [Phase 0: 被复刻系统的全维度分析](#3-phase-0-被复刻系统的全维度分析)
4. [Phase 1: 接口驱动的规格定义 (DEFINE)](#4-phase-1-接口驱动的规格定义-define)
5. [Phase 2: 可执行的实施计划 (PLAN)](#5-phase-2-可执行的实施计划-plan)
6. [Phase 3: 分层实现 (BUILD)](#6-phase-3-分层实现-build)
7. [Phase 4: 契约驱动的验证 (VERIFY)](#7-phase-4-契约驱动的验证-verify)
8. [Phase 5: 架构合规审查 (REVIEW)](#8-phase-5-架构合规审查-review)
9. [Phase 6: 切换上线 (SHIP)](#9-phase-6-切换上线-ship)
10. [知识产权保护指南](#10-知识产权保护指南)
11. [OpenCode 增强能力清单](#11-opencode-增强能力清单)
12. [反模式清单](#12-反模式清单)
13. [检查表](#13-检查表)
14. [Loop 循环控制速查表](#14-loop-循环控制速查表)

---

## 1. 核心原则（固定规则，首次执行时读一次）

### 1.1 接口契约优先

```
规则（必须遵守）:
1. 在任何实现代码之前，先定义完整的数据流接口
2. 禁止先写实现再调试集成——那会导致模块间数据格式无法对齐
3. 接口必须精确到参数类型和返回值，模糊的定义会导致实现时猜错
```

### 1.2 分层独立

```
规则（必须遵守）:
1. 依赖方向: schema → llm → core → app（每层只依赖下层）
2. Schema 层: 零依赖的纯类型定义（dataclass/enum/ABC）
3. LLM 层: 依赖 Schema，负责 Provider 通信抽象
4. Core 层: 依赖 Schema + LLM，负责业务编排
5. App 层: 依赖 Core，负责用户界面
6. 禁止跨层 import（如 Core 层直接 import App 层的代码）
```

### 1.3 现有实现复用

```
规则（必须遵守）:
1. 被复刻系统的架构和接口需要重写
2. 但单个功能的实现逻辑（工具实现、HTTP 调用、SQL 查询）保留不动
3. 保留的实现通过适配器模式包装进新接口，不修改旧代码
```

### 1.4 双轨并行过渡

```
规则（必须遵守）:
1. 新系统和旧系统通过功能开关（feature flag）在同一代码库中并行存在
2. 旧代码一行不改——新代码通过适配器调用旧功能
3. 只有新路径通过所有验证后，才删除旧代码
4. 不存在"重构途中改旧代码"的情况
```

### 1.5 迭代循环而非线性推进

```text
"完成"不是一次性事件，而是循环收敛的结果。
```

**规则:** 每个 Phase 内部运行多个循环迭代。每次迭代结束时：
1. 记录状态到 `.opencode/loop-state/`（状态文件）
2. 检查停止条件（是否该停？还是再跑一轮？）
3. 根据结果决定下一轮做什么

**不是:**
```
分析完毕 → 定义完毕 → 计划完毕 → 实现完毕 → 验证完毕
```

**而是:**
```
迭代 1: 分析模块 A → 定义接口 → 实现 → 验证 → 发现缺失 → 
迭代 2: 补充分析 → 修正接口 → 重写实现 → 重新验证 → 通过 → 
迭代 3: 进入下一个模块...
```

每个迭代是一个完整的"定义→计划→实现→验证"迷你循环。大 Phase 是这些循环的收敛方向，不是检查点列表。

### 1.6 Ratchet 原则（棘轮机制）

```text
每个错误都成为未来的规则。系统只进不退。
```

**规则:** 每次循环迭代中发现的问题，必须转化为永久性防护：

| 发现的问题 | 转化为 | 示例 |
|-----------|--------|------|
| Agent 忽略了某个边界条件 | 添加到 AGENTS.md 的约束规则 | `# 规则: 禁止使用 as any` |
| 测试遗漏了某个场景 | 新增契约测试 | `test_empty_input_returns_error` |
| 模块接口不清晰 | 更新接口定义 + 添加文档注释 | `"""契约: 返回 16 种 LLMEvent 之一"""` |
| Agent 反复犯同类错误 | 创建 Skill 固化工作流 | `skill: error-handling` |

**效果:** 每轮迭代后，系统（代码 + 规则 + 测试 + 文档）都变得更健壮。同样的错误不会出现两次。这个棘轮机制是 Loop Engineering 区别于普通"修复 bug"的核心特征。

---

## 2. Loop Engineering 执行框架

### 2.1 循环结构总览

6 个 Phase 不是瀑布阶段，而是每个循环迭代内部的步骤。执行模式如下：

```
┌─────────────────────────────────────────────────────────┐
│                     Loop Engineering                     │
│                                                          │
│  ┌──────┐    ┌──────┐    ┌──────┐    ┌──────┐           │
│  │DEFINE│ →  │ PLAN │ →  │BUILD │ →  │VERIFY│ →  ──┐   │
│  │      │    │      │    │      │    │      │    ←   │   │
│  └──────┘    └──────┘    └──────┘    └──────┘       │   │
│      ↑                                            │   │
│      └──────────── 不通过则回退 ──────────────────┘   │
│                                                      │
│  停止条件检查:                                        │
│    ├── 功能完整? → 进入下一模块/SHIP                   │
│    ├── 资源耗尽? → 压缩/回退/报告                      │
│    ├── 需要人工? → 中断等待                            │
│    └── 超过迭代上限? → 标记风险、上报、结束            │
└───────────────────────────────────────────────────────┘
```

**每个循环迭代走完 DEFINE → PLAN → BUILD → VERIFY。**
通过则进入下一个模块或升级阶段；不通过则回退到前一步修正。

### 2.2 循环状态机

每次循环迭代由一个状态文件驱动。这个文件是跨会话的"记忆"：

```json
// .opencode/loop-state/current.json
{
  "phase": "Phase 3: BUILD",
  "iteration": 4,
  "module": "SessionRunner",
  "status": "verifying",
  "cost_estimate": 2.50,
  "started_at": "2026-06-25T10:00:00Z",
  "findings": [
    "Test test_empty_input 被发现未覆盖 → 已添加契约测试",
    "Agent 多次使用 as any → 已添加 AGENTS.md 约束规则"
  ],
  "next_action": "修复 TestSessionRunner.test_empty_prompt 失败",
  "stop_conditions": {
    "max_iterations": 10,
    "max_cost_usd": 15.00,
    "must_have": ["契约测试全通过", "mypy strict 通过", "ruff clean"]
  }
}
```

**规则:**
- 每次 Agent 会话开始时，先读状态文件确定从哪里继续
- 每次迭代结束时，更新状态文件再退出
- Agent 会遗忘，但代码仓库不会

### 2.3 停止条件（Stop Conditions）

循环必须知道什么时候停下来。停止条件在每次迭代结束时检查：

| 条件 | 判断 | 行动 |
|------|------|------|
| ✅ **任务完成** | 所有验收标准通过 + 验证全绿 | 进入 SHIP 或下一模块 |
| 🔴 **达到迭代上限** | 迭代次数 > 10（可配置） | 标记风险、记录未完成项、停止 |
| 💰 **成本超限** | 累计成本 > $15 USD | 停止、压缩状态、报告消耗 |
| 👤 **需人工介入** | 需要决策、设计选择、权限 | 中断循环、等待人工输入 |
| 💥 **不可恢复错误** | 架构缺陷、依赖缺失 | 记录完整失败上下文、停止 |

**在每次循环迭代的 VERIFY 步骤结束时检查停止条件。** 不满足任何停止条件则继续下一轮迭代。

### 2.4 状态持久化（State Persistence）

Agent 会话会被压缩、超时、或开启新窗口。状态文件是跨会话的唯一"记忆"。

```
.opencode/
└── loop-state/
    ├── current.json          ← 当前迭代状态
    ├── iteration-001.json    ← 历史迭代归档
    ├── iteration-002.json
    └── ...
```

每个迭代归档包含：
```
{
  "iteration": 1,
  "phase": "Phase 1: DEFINE",
  "module": "LLMError 模型",
  "what_was_tried": "定义了 10 种 LLMErrorReason",
  "what_passed": "类型检查通过，5 个契约测试通过",
  "what_failed": "ToolFailure 的 message 字段应为必填",
  "whats_next": "修复 ToolFailure 构造器 → 重新验证",
  "cost": 0.85,
  "ratchet_added": ["AGENTS.md: ToolFailure.message 禁止为空"]
}
```

### 2.5 Worktree 隔离（并行安全）

当并行运行多个 Agent 时，使用 git worktree 隔离文件变更：

```bash
# 为每个并行任务创建独立 worktree
git worktree add ../loop-session-runner -b loop/session-runner
git worktree add ../loop-tool-registry -b loop/tool-registry

# 在每个 worktree 中运行独立的 Agent 会话
# worktree 之间不会相互覆盖文件

# 任务完成后合并
cd ../loop-session-runner
git add -A && git commit -m "feat: SessionRunner 实现"
cd /main/repo
git merge loop/session-runner

# 清理
git worktree remove ../loop-session-runner
git branch -d loop/session-runner
```

**什么时候必须用 worktree:**
- 2 个以上的 Agent 同时修改不同文件
- 修改涉及共享依赖（如 schema 层）
- 需要独立验证变更不被其他 Agent 干扰

**什么时候不需要:**
- 单 Agent 顺序工作
- 只读操作（explore、分析）

### 2.6 Ratchet 机制执行流程

每次循环迭代结束时，强制执行 Ratchet 检查：

```
1. 本轮发现了什么错误/遗漏？
   ├── 测试没覆盖的边界条件 → 新增测试
   ├── Agent 犯了重复错误 → 更新 AGENTS.md
   ├── 文档不够清晰 → 更新接口注释
   └── 流程有盲点 → 更新 Skill

2. 这些补强是否已落地？
   ├── 测试文件已更新
   ├── AGENTS.md 有新增规则
   ├── 接口注释已更新
   └── Skill 文件已更新

3. 确认: 同样的错误不会再发生？
```

**Ratchet 是必选步骤，不是可选。** 没有 Ratchet 的循环只是"修 bug"——同样的 bug 会反复出现。

### 2.7 成本管理（Cost Gates）

每次循环迭代前估算成本，超限则停止：

```bash
# 成本等级
XS ($0-1)    → 直接做，不检查
S  ($1-3)    → 开始前确认预算
M  ($3-8)    → 拆分为多个 S 任务
L  ($8-15)   → 需要人工审批
XL ($15+)    → 禁止，必须重新计划
```

**追踪工具:**
```json
// .opencode/loop-state/cost-log.json
{
  "total_cost": 12.40,
  "iterations": [
    {"iteration": 1, "cost": 2.10, "tokens_in": 45000, "tokens_out": 12000},
    {"iteration": 2, "cost": 1.80, "tokens_in": 32000, "tokens_out": 9800},
    ...
  ],
  "budget_remaining": 2.60
}
```

---

## 3. Phase 0: 被复刻系统的全维度分析

> **🔄 循环上下文**
> 
> 你正在执行一个循环迭代中的 **Phase 0 (分析)**。这是每次循环中首先执行的步骤。
> 
> **读取状态文件确认当前轮次:**
> ```bash
> # 会话开始时执行
> cat .opencode/loop-state/current.json
> # 确认: iteration, module, 上一轮 findings
> ```
> 
> **执行规则:**
> 1. 一次只分析一个模块（或一个子系统）。不要试图在一个迭代中分析所有模块。
> 2. 分析完成后，将产出物（文件树、依赖图、接口签名）记录到状态文件。
> 3. 不追求完美——遇到不确定的依赖关系，标记后继续。
> 
> **本 Phase 输出 → Phase 1 (DEFINE)**
> 

---

### 🛠 本 Phase OpenCode 工具指引

| 用途 | 工具/命令 | 说明 |
|------|----------|------|
| **广度搜索** — 找文件、找模块结构 | `task(subagent_type="explore", run_in_background=true, prompt="Find all module files in packages/core/src/")` | 让 explore agent 找出文件路径，**不要让它读文件内容** |
| **深度阅读** — 理解具体类做了什么 | `read("packages/core/src/session/Session.ts")` | 你自己读，不要委托给 Agent |
| **外部参考** — 查不确定的库用法 | `task(subagent_type="librarian", run_in_background=true, prompt="How does Effect's Schema.decode work?")` | 只在遇到不熟悉的外部依赖时使用 |

### 3.1 分析流程

```
获取源码
  ├── 克隆/下载目标系统的完整代码仓库
  ├── 理解项目结构 (packages, modules)
  │
  ├── [选择分析方法]
  │
  ├── 方案 A: 直接源码阅读 (推荐)
  │   ├── 适合: 中小型项目 (< 50 个核心文件)
  │   ├── 优点: 完全可控, 无超时风险
  │   └── 步骤: 按依赖顺序逐文件阅读
  │
  └── 方案 B: Agent 辅助分析 (LLM 工具)
      ├── 适合: 大型项目 (50+ 文件, 需要广度覆盖)
      ├── 注意: 
      │   ├── 每 30 分钟超时限制 → 任务要足够小
      │   ├── 上下文压缩可能导致任务丢失 → 重要任务用同步模式
      │   └── 不能替代直接阅读 → Agent 只用来找文件，读文件自己来
      └── 命令: task(subagent_type="explore", run_in_background=true, prompt="...")
```

### 3.2 五维分析框架

每个模块都从 5 个维度分析：

```
1. STRUCTURE (结构)
   问: 这个模块有哪些文件？依赖哪些外部包？接口签名是什么？
   产: 模块文件树 + 依赖关系图

2. BEHAVIOR (行为)
   问: 核心函数做什么？生命周期是什么？错误条件有哪些？
   产: 关键函数的调用序列 + 状态机

3. FLOW (路径)
   问: 用户请求的完整数据流经过哪些模块？
   产: 请求处理链的 ASCII 流程图

4. EDGE (边界)
   问: 超时、重试、溢出、并发冲突怎么处理？
   产: 所有错误处理路径 + 恢复策略

5. DIFF (差异)
   问: 现有实现和目标语言实现有什么差距？
   产: 逐行对比表
```

### 3.3 分析产出物

| 产物 | 格式 | 用途 |
|------|------|------|
| 模块文件树 | 文本 | 理解组织方式 |
| 依赖关系图 | 文本/ASCII | 分层基础 |
| 关键数据流 | ASCII 流程图 | 指导接口设计 |
| 错误处理清单 | 表格 | 指导错误模型 |
| 差距分析表 | 表格 | 指导实现优先级 |
| 核心接口签名 | 伪代码 | 接口定义的起点 |

### 3.4 实战经验: 直接阅读优于 Agent 委托

在 CScode 分析中尝试了两种方式：

| 方式 | 结果 | 原因 |
|------|------|------|
| `deep` agent 委托 | ❌ 22 次全部失败 | 30 分钟超时 + 上下文压缩导致 task 丢失 |
| 直接 `read` | ✅ 50+ 文件全部成功 | 完全可控，无中间层开销 |

**结论：** Agent 只用来做**广度搜索**（"帮我找到所有工具文件"），**深度阅读**（"这个类具体做了什么"）自己做。把读文件看作自己的核心工作，不要外包。

> **🔄 循环出口**
> 
> 分析完成后，执行以下步骤：
> 
> **1. ✅ 成功 — 更新状态文件，进入 DEFINE:**
> ```json
> // .opencode/loop-state/current.json 更新为:
> {
>   "phase": "Phase 1: DEFINE",
>   "module": "<当前分析的模块名>",
>   "status": "ready",
>   "findings": ["<本轮发现的问题>"],
>   "next_action": "进入 Phase 1 DEFINE，定义模块接口"
> }
> ```
> 
> **2. ❌ 分析不充分 — 下一轮迭代补充:**
> - 更新 `next_action` 为"需要补充分析：<具体缺失>"
> - `phase` 保持 "Phase 0: ANALYSIS"
> - iteration +1，进入下一循环
> 
> **3. ⏹ 停止条件检查（参见 §2.3）:**
> - 所有模块已分析完成 → 进入 SHIP 规划
> - 迭代次数达到上限 → 标记未分析模块为风险项，继续下一 Phase
> - 成本超限 → 压缩状态、报告消耗、中断

---

## 4. Phase 1: 接口驱动的规格定义 (DEFINE)

> **🔄 循环上下文**
> 
> 你正在执行一个循环迭代中的 **Phase 1 (DEFINE)**。Phase 0 对当前模块的分析已完成，现在基于分析产出物定义接口。
> 
> **读取状态文件:**
> ```bash
> cat .opencode/loop-state/current.json
> # 确认: 当前模块是哪个？上一步分析发现了什么？
> ```
> 
> **执行规则:**
> 1. 基于 Phase 0 的分析产出物，定义当前模块的完整接口
> 2. 不要定义不属于当前模块的接口——每个迭代只关注一个模块
> 3. 接口必须精确到参数类型和返回值——模糊的定义会导致 Agent 实现时猜错
> 4. 定义即契约——测试人员要根据这个写测试
> 
> **本 Phase 输出 → Phase 2 (PLAN)**

### 🛠 本 Phase OpenCode 工具指引

| 用途 | 工具/命令 | 说明 |
|------|----------|------|
| **接口设计咨询** — 复杂接口拿不准时 | `task(subagent_type="oracle", prompt="Review this interface design: [paste]. Is the abstraction right? Any missing methods?")` | oracle 是只读的，不修改代码，适合做设计评审 |
| **跨模块接口一致性** — 确认新接口与已定义接口不冲突 | `task(subagent_type="explore", prompt="Find all ABC class definitions in src/cscode/ to check naming conventions")` | 确保接口风格一致 |
| **规格文档记录** | 写在 `openspec/specs/` 目录下 | 标记引用已实现的接口文件路径 |

### 4.1 定义什么

在写任何一行实现代码前，先定义：

```
1. 数据模型 (Data Models)
   └── 所有跨模块传递的数据结构
   └── 例: LLMRequest, LLMEvent, LLMError, Message, ToolCall

2. 模块接口 (Module Interfaces)
   └── 每个模块的 ABC/Protocol
   └── 例: class LLMProvider(ABC): async def stream()...

3. 错误模型 (Error Model)
   └── 所有可能错误的分类和可重试性
   └── 例: RateLimit(retryable=True), InvalidRequest(retryable=False)

4. 生命周期契约 (Lifecycle Contracts)
   └── 模块创建→使用→销毁的协议
   └── 例: Session.create() → Session.run() → Session.close()
```

### 4.2 接口定义规范

```
必须包含以下文件，每个文件一个独立模块：

1. 数据模型文件 (schema/messages.py)
   └── 所有跨模块传递的 @dataclass，使用 Union 类型组合

2. 错误模型文件 (schema/errors.py)
   └── 所有错误的 enum 分类 + 统一 LLMError(Exception) 基类
   └── 每个错误标注 retryable: bool 和 retry_after_ms: int | None

3. 模块接口文件 (core/interfaces/provider.py)
   └── 使用 ABC + @abstractmethod，参数和返回值用 1-2 中定义的类型

规则:
- 接口必须精确到参数类型和返回值
- 接口注释必须包含契约（什么情况下返回什么）
- 所有类型必须可 JSON 序列化（不包含复杂对象引用）
```

### 4.3 接口文档结构

```
openspec/specs/
├── 01-data-models.md       # 所有数据模型定义
├── 02-module-interfaces.md # 所有模块接口定义
├── 03-error-model.md       # 错误分类和处理策略
├── 04-contracts.md         # 跨模块集成契约
└── README.md               # 规格索引
```

### 4.4 规格验证标准

一份好的 DEFINE 文档应该能回答：

- 开发者读完后能独立实现一个模块，不需要问"这个参数是什么格式"
- 两个开发者分别实现 Provider A 和 SessionRunner，然后能直接集成
- 测试人员能根据规格写出契约测试

> **🔄 循环出口**
> 
> 接口定义完成后，执行以下步骤：
> 
> **1. ✅ 成功 — 更新状态文件，进入 PLAN:**
> ```json
> {
>   "phase": "Phase 2: PLAN",
>   "module": "<当前模块>",
>   "interfaces_defined": ["Provider", "Error", ...],
>   "spec_path": "openspec/specs/",
>   "next_action": "进入 Phase 2 PLAN，分解实现任务"
> }
> ```
> 
> **2. ❌ 接口定义有缺陷 — 回退到上一 Phase:**
> - 如果在定义中发现分析遗漏（不清楚某个参数的作用）→ `phase` 回到 "Phase 0: ANALYSIS"，补充分析后重来
> - 如果接口本身不合理（太复杂、不内聚）→ 更新 `findings`，重新分析同模块
> 
> **3. ⏹ 停止条件检查:**
> - 当前模块接口定义完整 → 进入 PLAN
> - 发现大量不确定点需要人工决策 → 标记为 NEEDS_HUMAN，中断

---

## 5. Phase 2: 可执行的实施计划 (PLAN)

> **🔄 循环上下文**
> 
> 你正在执行一个循环迭代中的 **Phase 2 (PLAN)**。当前模块的接口已定义，现在将实现分解为原子任务。
> 
> **读取状态文件:**
> ```bash
> cat .opencode/loop-state/current.json
> # 确认: 当前模块、已定义的接口列表
> ```
> 
> **执行规则:**
> 1. 每个原子任务必须在 1-3 天内能独立完成——粒度太大则 Agent 执行时会超时/丢失上下文
> 2. 标注每个任务的依赖关系——不能并行实现的任务必须标记先后顺序
> 3. **标注成本等级**——每个任务估算 Token/美元成本，按以下等级:
>    - XS ($0-1) → 直接做
>    - S ($1-3) → 开始前确认预算
>    - M ($3-8) → 拆分为多个 S 任务
>    - L ($8-15) → 需要人工审批
>    - XL ($15+) → 禁止，必须重新计划
> 4. **标注是否需要 worktree 隔离**——如果 2 个以上并行任务，必须用 worktree:
>    - 需要 worktree 的情况: 2+ Agent 同时改不同文件、涉及共享依赖、需要独立验证
>    - 不需要 worktree 的情况: 单 Agent 顺序工作、只读操作
> 5. 每个任务必须有明确的验收标准——Agent 执行后能自行判断是否完成
> 
> **本 Phase 输出 → Phase 3 (BUILD)**

### 🛠 本 Phase OpenCode 工具指引

| 用途 | 工具/命令 | 说明 |
|------|----------|------|
| **规划前分析** — 实现前先让 metis 找出盲点 | `task(subagent_type="metis", prompt="I'm planning to implement [module]. Here are the interfaces: [paste]. What am I missing? What could go wrong?")` | metis 是规划咨询师，擅长发现隐藏假设和遗漏 |
| **计划审查** — 计划写完后让 momus 批评 | `task(subagent_type="momus", prompt="Review this implementation plan: [paste plan]. Is every task verifiable? Any missing dependencies?")` | momus 是计划评论家，只批评不修改 |
| **成本估算** — 不确定成本等级时 | 用成本等级表估: XS=$0-1, S=$1-3, M=$3-8, L=$8-15, XL=$15+ | 如果 >= L 级，必须走完 metis + momus 才能进入 BUILD |

### 5.1 任务分解原则

```
按依赖顺序分解成原子任务:

Schema (零依赖)            ← Phase 0
  └── LLM (依赖 Schema)    ← Phase 1
      └── Core (依赖 LLM)  ← Phase 2
          └── App (依赖 Core) ← Phase 3
```

每个原子任务的粒度：**一个人 1-3 天内能完成**。

### 5.2 任务模板

```markdown
## Task: 定义 LLMError 模型

**文件:** src/cscode/schema/errors.py
**依赖:** 无
**预估:** 1 小时
**验收标准:**
- 所有 10 种 reason 已枚举
- LLMError 包含 module/method/reason/retryable 字段
- ToolFailure 定义为独立异常类
- 通过类型检查: mypy --strict
```

### 5.3 并行机会识别

```text
Phase 0 内部可并行的任务:
  ├── Schema: 消息模型      ← A 负责
  ├── Schema: 错误模型      ← B 负责
  ├── Schema: 事件模型      ← C 负责
  └── Schema: 工具定义      ← D 负责

Phase 1:
  └── 依赖 Phase 0 完成，不可并行
```

### 5.4 实施顺序

```text
每个 Phase 内部的执行顺序:
  1. Aggressive 分析当前层的旧代码（哪些可复用，哪些需重写）
  2. 定义该层的接口（ABC + dataclass）
  3. 写该层的契约测试
  4. 实现该层的一个模块
  5. 验证契约测试
  6. 实现下一个模块
```

> **🔄 循环出口**
> 
> 计划完成后，执行以下步骤：
> 
> **1. ✅ 成功 — 更新状态文件，进入 BUILD:**
> ```json
> {
>   "phase": "Phase 3: BUILD",
>   "module": "<当前模块>",
>   "tasks": [
>     {"name": "实现 Provider 接口", "cost_estimate": "S ($1-3)", "worktree": "loop-provider"},
>     {"name": "实现 Error 模型", "cost_estimate": "XS ($0-1)", "worktree": null}
>   ],
>   "next_action": "进入 Phase 3 BUILD，执行任务列表"
> }
> ```
> 
> **2. ❌ 计划不合理 — 回退:**
> - 如果某个任务粒度太大（预估 > 3 天）→ 继续分解，不进入 BUILD
> - 如果有任务依赖不明确 → 回到 Phase 1 补充接口定义
> 
> **3. ⏹ 停止条件检查:**
> - 当前模块所有任务已分解完成 → 进入 BUILD
> - 总成本等级达到 L ($8-15) 或 XL ($15+) → 需要人工审批后才能进入 BUILD

## 6. Phase 3: 分层实现 (BUILD)

> **🔄 循环上下文**
> 
> 你正在执行一个循环迭代中的 **Phase 3 (BUILD)**。当前模块的实现计划已制定，现在执行代码。
> 
> **读取状态文件:**
> ```bash
> cat .opencode/loop-state/current.json
> # 确认: 当前模块、任务列表、成本估算
> ```
> 
> **执行规则:**
> 1. 先写契约测试，再写实现（TDD）——第 §6.4 节详细说明
> 2. 旧代码不动，用适配器模式包装（第 §6.2 节）
> 3. **如果计划中有 2+ 并行任务，必须使用 worktree 隔离（见下方 §6.3 操作命令）**
> 4. 每个模块实现完成后，立即更新状态文件
> 5. 不要在一个迭代中实现两个模块——一个迭代只做一个模块
> 
> **本 Phase 输出 → Phase 4 (VERIFY)**

### 🛠 本 Phase OpenCode 工具指引

| 用途 | 工具/命令 | 说明 |
|------|----------|------|
| **委托独立模块实现** — 将无依赖的子任务交给子 Agent | `task(category="unspecified-high", load_skills=["source-driven-development"], prompt="Implement the Provider interface. File: src/cscode/llm/provider.py. Interface: [paste]. Must pass mypy strict.")` | 使用 `load_skills` 加载相关技能 |
| **小修小改** — 适配器、类型修复 | `task(category="quick", prompt="Fix the type annotation in provider.py line 42")` | 简单任务不需要 skills |
| **并行实现隔离** — 2+ 任务并行时 | 用 `git worktree add` 创建独立 worktree（具体命令见 §6.3） | 必须隔离，不能在同一目录跑两个 Agent |
| **实现中遇到设计问题** | `git commit -m "wip: [current state]"` 后咨询 oracle | 不要卡住，先提交当前状态再问 |

### 6.1 实现方式选择

每个模块都有两种实现方式：

| 方式 | 适合场景 | 方法 |
|------|----------|------|
| **全新实现** | 现有代码无法复用 | 按接口写新代码 |
| **适配器包装** | 现有代码实现正确但接口不匹配 | Adapter Pattern: 旧类包装成新接口 |

### 6.2 适配器模式

```
命令: 旧代码不动，实现一个新的 Adapter 类，实现新接口，内部调用旧实现。

步骤:
1. 创建一个新类，实现当前迭代定义的 ABC 接口
2. 构造函数接收或创建旧实现的实例
3. 每个接口方法内调用旧实现的对应方法，转换参数/返回值类型
4. 不修改旧代码的任何一行

规则:
- 旧代码一行不改。改了就不是适配器，是重构。
- 如果有 bug，定位到适配器层——旧实现已经被测试验证过。
```

### 6.3 并行实现：Worktree 隔离操作命令

当计划中有 2 个以上的并行任务，必须用 git worktree 隔离。不要在同一工作目录中并行运行多个 Agent。

```bash
# ⚡ 步骤 1: 为每个并行任务创建独立 worktree
# 命名规范: loop-<模块名>-<小任务名>
git worktree add ../loop-provider -b loop/provider
git worktree add ../loop-errors -b loop/errors

# ⚡ 步骤 2: 在每个 worktree 中启动独立的 Agent 会话
# Agent A (在 ../loop-provider 中):
#   task(category="unspecified-high", prompt="实现 Provider 接口 ...")
# Agent B (在 ../loop-errors 中):
#   task(category="unspecified-high", prompt="实现 Error 模型 ...")
#
# 两个 worktree 之间不会相互覆盖文件——安全并行

# ⚡ 步骤 3: 每个 worktree 完成后提交合并
cd ../loop-provider
git add -A && git commit -m "feat: 实现 Provider 接口 [loop iteration N]"
cd /main/repo
git merge loop/provider --no-ff -m "merge: Provider 接口实现 [iteration N]"

cd ../loop-errors
git add -A && git commit -m "feat: 实现 Error 模型 [loop iteration N]"
cd /main/repo
git merge loop/errors --no-ff -m "merge: Error 模型实现 [iteration N]"

# ⚡ 步骤 4: 清理
git worktree remove ../loop-provider
git branch -d loop/provider
git worktree remove ../loop-errors
git branch -d loop/errors
```

**一次性实现（无并行）** ——不需要 worktree，直接在主工作目录实现即可。完成一个模块后再做下一个。

### 6.4 TDD 强制

每个模块必须先通过测试才能合入：

```python
# 1. 先写测试
async def test_read_tool_contract():
    tool = ReadToolAdapter()
    result = await tool.execute(ReadInput(file_path="/tmp/test.txt"))
    assert isinstance(result, ReadOutput)
    assert len(result.content) > 0

# 2. 再写实现 — 只写能让测试通过的代码
# 3. 重构 — 在测试保护下优化
```

> **🔄 循环出口**
> 
> 实现完成后，执行以下步骤：
> 
> **1. ✅ 成功 — 更新状态文件，进入 VERIFY:**
> ```json
> {
>   "phase": "Phase 4: VERIFY",
>   "module": "<当前模块>",
>   "implemented_files": ["src/cscode/llm/provider.py", ...],
>   "used_worktrees": ["loop-provider", "loop-errors"],
>   "cost_actual": 2.50,
>   "next_action": "进入 Phase 4 VERIFY，运行所有验证"
> }
> ```
> 
> **2. ❌ 实现失败 — 回退:**
> - 编译/类型错误 → 修复后重试，不退出 Phase 3
> - 发现接口定义有缺陷（实现中才发现参数不足）→ `phase` 回到 "Phase 1: DEFINE"，修正接口
> - 发现任务分解不合理 → `phase` 回到 "Phase 2: PLAN"，重新分解
> 
> **3. ⏹ 停止条件检查:**
> - 当前模块实现完成 → 进入 VERIFY
> - 实现在 3 次迭代内未收敛 → 标记为 BLOCKED，需要人工介入

## 7. Phase 4: 契约驱动的验证 (VERIFY)

> **🔄 循环上下文**
> 
> 你正在执行一个循环迭代中的 **Phase 4 (VERIFY)**。当前模块已实现，现在验证它是否正确。
> 
> **读取状态文件:**
> ```bash
> cat .opencode/loop-state/current.json
> # 确认: 当前模块、实现文件列表、实际成本
> ```
> 
> **执行规则:**
> 1. 运行所有三级验证（§7.1）——契约测试 → 集成测试 → E2E 测试
> 2. 验证结果必须全部自动化为脚本——不接受"手动检查"
> 3. 验证失败时，根据失败类型回退到正确的 Phase（§7.3）
> 4. **本 Phase 结束时必须执行停止条件检查（§2.3）**——这是决定继续还是停止的关键点
> 5. 验证通过后，执行 ratchet 检查（§2.6）——本轮发现的问题必须固化
> 
> **验证通过 → 进入 Phase 5 (REVIEW)。验证不通过 → 根据失败类型回退。**

### 🛠 本 Phase OpenCode 工具指引

| 用途 | 工具/命令 | 说明 |
|------|----------|------|
| **测试失败调试** — 2 次修复失败后 | `task(subagent_type="oracle", prompt="Test [name] is failing with [error]. The implementation is in [file]. I've tried [what]. What's the root cause?")` | oracle 擅长找根因，不擅长度量，给足上下文 |
| **批量运行验证** | `pytest tests/contract/ -x && mypy src/ && ruff check src/` | 合约测试必须全通过才能继续 |
| **新旧路径一致性** — 对比新旧系统输出 | 用脚本跑同一组测试输入，对比两边输出 | 不一致时用 oracle 分析差异原因 |

### 7.1 三级验证

```
Level 1: 契约测试 (每个模块)
  ├── 输入验证: 非法输入是否返回正确错误
  ├── 输出验证: 输出是否符合接口定义
  ├── 边界验证: 空值/超大值/并发
  └── 错误验证: 所有错误路径是否覆盖

Level 2: 集成测试 (跨模块)
  ├── Provider → SessionRunner 集成
  ├── ToolRegistry → Tool 集成
  └── Session → EventStore 集成

Level 3: E2E 测试 (全链路)
  ├── CLI: cs chat "hello" 返回正确响应
  ├── Server: HTTP API 调用成功
  └── Session: 创建 → 运行 → 恢复 → 数据一致
```

### 7.2 自动验证脚本

```bash
# 每次提交前必须运行
pytest tests/contract/     # 契约测试（必须全通过）
pytest tests/integration/  # 集成测试（必须全通过）
mypy src/                  # 类型检查（严格模式）
ruff check src/            # 代码风格
```

### 7.3 验证不通过的处置

```text
契约测试失败 → 接口定义有问题，回退到 DEFINE 修复
集成测试失败 → 某个模块实现不符合接口，回退到 BUILD 修复
E2E 测试失败 → 整体流程问题，回退到 PLAN 检查
```

> **🔄 循环出口**
> 
> 验证完成后，**必须执行停止条件检查**。这是循环迭代中最关键的决策点。
> 
> **1. 🛑 停止条件检查（参见 §2.3）——按顺序检查:**
> 
> ```bash
> # 检查 1: 任务完成？
> pytest tests/contract/ --exitfirst && pytest tests/integration/ --exitfirst && mypy src/ && ruff check src/
> if [ $? -eq 0 ]; then
>   echo "✅ 验证全通过"
> else
>   echo "❌ 验证未通过 → 按 §7.3 回退"
>   exit 1
> fi
> 
> # 检查 2: 迭代次数超限？
> ITER=$(cat .opencode/loop-state/current.json | python3 -c "import sys,json; print(json.load(sys.stdin)['iteration'])")
> if [ "$ITER" -gt 10 ]; then
>   echo "⚠️ 迭代次数超限 ($ITER > 10) → 标记风险，上报"
> fi
> 
> # 检查 3: 成本超限？
> COST=$(cat .opencode/loop-state/cost-log.json | python3 -c "import sys,json; print(json.load(sys.stdin)['total_cost'])")
> if (( $(echo "$COST > 15.0" | bc -l) )); then
>   echo "💰 成本超限 ($COST > $15) → 停止，压缩状态"
> fi
> ```
> 
> **2. ✅ 验证通过 + 停止条件未触发 — 进入 REVIEW:**
> ```json
> {
>   "phase": "Phase 5: REVIEW",
>   "module": "<当前模块>",
>   "verification_passed": true,
>   "test_count": 42,
>   "cost_total": 4.50,
>   "next_action": "进入 Phase 5 REVIEW，架构合规审查"
> }
> ```
> 
> **3. ❌ 验证未通过 — 按 §7.3 回退:**
> - 契约测试失败 → Phase 1 (DEFINE) 修正接口
> - 集成测试失败 → Phase 3 (BUILD) 修正实现
> - E2E 测试失败 → Phase 2 (PLAN) 重新规划
> 
> **4. ⏹ 停止条件触发 — 中断循环:**
> - 迭代超限 → 记录未完成项，标记风险，进入 REVIEW 做最终评估
> - 成本超限 → 压缩状态文件，报告消耗，等待人工决策
> - 需要人工介入 → `status: "NEEDS_HUMAN"`，中断等待

## 8. Phase 5: 架构合规审查 (REVIEW)

> **🔄 循环上下文**
> 
> 你正在执行一个循环迭代中的 **Phase 5 (REVIEW)**。当前模块已验证通过，现在进行架构合规审查并执行 Ratchet 机制。
> 
> **读取状态文件:**
> ```bash
> cat .opencode/loop-state/current.json
> # 确认: 当前模块、验证结果、已产生成本
> ```
> 
> **执行规则:**
> 1. 检查分层合规、接口合规、错误处理合规、测试覆盖（§8.1-8.2）
> 2. **本 Phase 结束时必须执行 Ratchet 检查（§2.6）**——本轮发现的问题必须转化为永久防护
> 3. Ratchet 产出物（新增测试、AGENTS.md 规则、Skill 更新）必须提交到代码库
> 4. 审查通过后，决定是进入下一模块的迭代还是进入 SHIP
> 
> **审查通过 → 决定：下一模块迭代 / 进入 SHIP。审查不通过 → 回退到相关 Phase。**

### 🛠 本 Phase OpenCode 工具指引

| 用途 | 工具/命令 | 说明 |
|------|----------|------|
| **全面审查** — 实现完成后启动 5 路并行审查 | `task(load_skills=["review-work"], prompt="Review all changes in this iteration. Module: [name]. Files: [list]. Spec: openspec/specs/.")` | 自动启动 5 个并行审查子 Agent |
| **架构咨询** — 对架构决策有疑虑时 | `task(subagent_type="oracle", prompt="I'm concerned about [arch decision]. Here's the current structure: [paste]. Is this the right abstraction?")` | oracle 只读不写，适合做架构评估 |
| **Ratchet 执行确认** | 检查 §8.3 的 Ratchet 步骤是否全部完成 | 确认本轮发现的错误已转化为防护 |

### 8.1 审查维度

```
1. 分层合规
   └── Core 层是否直接 import 了 app 层的代码？
   └── ✓ 应当: LLM 层不 import Core 层
   
2. 接口合规
   └── 模块的所有公开方法是否在接口中定义？
   └── ✓ 应当: 所有跨模块调用走接口，不直接调实现类

3. 错误处理合规
   └── 是否所有 LLM 错误都用了 LLMError？
   └── ✓ 应当: 没有裸露的 try/except Exception

4. 测试覆盖
   └── 契约测试是否覆盖了所有接口方法？
   └── ✓ 应当: 每个接口方法至少有一个测试
```

### 8.2 审查工具

```bash
# 检查分层违规
grep -r "from cscode.core" src/cscode/llm/  # 不应有
grep -r "from cscode.app" src/cscode/core/  # 不应有

# 检查接口一致性
grep -r "class \w+(ABC)" src/cscode/  # 列出所有接口
grep -r "class \w+(\w+):" src/cscode/ # 找出可能绕过接口的实现
```

> **🔄 循环出口**
> 
> 审查完成后，**必须执行 Ratchet 检查（§2.6）**：
> 
> **1. 🔧 Ratchet 执行步骤（强制）:**
> 
> ```bash
> # 步骤 A: 审查本轮发现了什么问题？
> # - 测试没覆盖的边界条件？ → 新增契约测试
> # - Agent 犯了重复错误？ → 更新 AGENTS.md 添加约束
> # - 接口注释不够清晰？ → 更新文档注释
> # - 流程有盲点？ → 更新 Skill 或本文档
> 
> # 步骤 B: 所有补强已落地？
> grep -r "新增规则" AGENTS.md  # 确认规则已添加
> pytest tests/contract/ -x     # 确认新增测试通过
> 
> # 步骤 C: 确认同样的错误不会再发生
> echo "Ratchet 检查完成 ✅"
> ```
> 
> **2. ✅ 审查通过 + Ratchet 完成 — 决定下一轮方向:**
> 
> ```json
> {
>   "phase": "Phase 0: ANALYSIS",   // 回到 Phase 0 开始下一个模块
>   "module": "<下一个模块>",
>   "iteration": "<当前 iteration + 1>",
>   "ratchet_items": ["新增契约测试: test_xxx", "更新 AGENTS.md: 规则 Y"],
>   "cost_total": 5.20,
>   "next_action": "进入下一轮循环，分析下一个模块"
> }
> ```
> 
> **或者 — 如果所有模块已完成:**
> ```json
> {
>   "phase": "Phase 6: SHIP",
>   "module": null,
>   "all_modules_complete": true,
>   "next_action": "所有模块完成，进入 Phase 6 SHIP"
> }
> ```
> 
> **3. ❌ 审查不通过 — 回退:**
> - 发现分层违规 → 回到 Phase 3 (BUILD) 修复
> - 发现接口不一致 → 回到 Phase 1 (DEFINE) 修正
> - 发现测试遗漏 → 回到 Phase 4 (VERIFY) 补充

## 9. Phase 6: 切换上线 (SHIP)

> **🔄 循环上下文**
> 
> 这是 Loop Engineering 的**收敛终止阶段**。所有模块已通过循环迭代完成，现在进行系统级切换。
> 
> **到达本 Phase 的条件（来自 Phase 5 REVIEW 的判定）:**
> - 所有模块已通过至少一轮完整的 0→1→2→3→4→5 循环迭代
> - 所有契约测试通过
> - 新旧系统在测试用例上结果一致
> - Ratchet 机制已执行
> 
> **读取最终状态:**
> ```bash
> cat .opencode/loop-state/current.json
> # 确认: all_modules_complete = true
> ```
> 
> **执行规则:**
> 1. SHIP 是**单一方向**的——不循环回退到前面的 Phase（如果上线发现问题，创建新的 bugfix 循环）
> 2. 使用功能开关逐个切换（§9.1）——每个开关打开后有观察窗口
> 3. 每个开关打开后验证新旧路径一致性
> 4. 所有开关打开后，清理旧代码

### 9.1 渐进切换策略

```python
# config.py
class FeatureFlag:
    use_new_session = False  # 先关
    use_new_provider = False
    use_new_runner = False

# 逐个打开
# Week 1: use_new_provider = True (旧 engine 通过新 provider 调用)
# Week 2: use_new_session = True (新 Session 存储)
# Week 3: use_new_runner = True (替换旧 engine)
```

### 9.2 切换顺序

```
1. Schema 层上线 ─── 零影响，纯类型
2. LLM 层上线 ───── 旧 engine 通过新 provider 调用（适配器模式）
3. Core 层上线 ──── 新 SessionRunner 与旧 engine 并存，A/B 测试
4. App 层上线 ───── 切换默认入口到新系统
5. 清理旧代码 ───── 删除 engine.py, session_manager.py
```

### 9.3 切换标准

```
Schema 层:  所有类型定义经过 mypy 检查 ✅
LLM 层:     所有 provider 通过契约测试 + 新旧 provider 输出一致 ✅
Core 层:    新 SessionRunner 与旧 engine 在 100 个测试用例上结果一致 ✅
App 层:     CLI/TUI/Server 三个入口都工作正常 ✅
旧代码清理: 所有 import 已迁移到新路径，旧文件已删除 ✅
```

> **🔄 循环出口 — 循环终止**
> 
> 切换上线完成后，Loop Engineering 循环正式终止。执行以下收尾步骤：
> 
> **1. 📦 最终状态归档:**
> ```json
> {
>   "phase": "COMPLETED",
>   "total_iterations": 18,
>   "total_cost": 45.20,
>   "modules_completed": ["Schema", "LLM", "Core", "App"],
>   "ratchet_total_items": 12,
>   "completed_at": "2026-07-01T00:00:00Z",
>   "summary": "所有模块完成。最终架构合规。旧代码已清理。"
> }
> 
> // 将最终状态复制为归档
> // cp .opencode/loop-state/current.json .opencode/loop-state/final.json
> ```
> 
> **2. 🧹 清理:**
> - 删除所有功能开关的旧代码路径（保留开关框架）
> - 删除临时 worktree
> - 归档 `.opencode/loop-state/` 目录
> 
> **3. ✅ 后续工作 — 不在本方法论范围内:**
> - 线上 bug → 创建新的 bugfix 循环（独立小循环，不经过完整的 0→6）
> - 新功能 → 启动新的方法论流程（新的 Loop Engineering 循环）

## 10. 知识产权保护指南（行为边界，必须遵守）

### 10.1 允许的操作

```
1. 可以读源码理解架构设计——思想/架构不受版权保护
2. 可以复用餐具结构作为参考——目录结构是事实表达
3. 可以重写接口签名（调整参数名用目标语言风格）——API 兼容需要
4. 可以复用算法思路——算法不受版权保护
5. 可以根据架构文档重新设计——公开文档中的设计理念
```

### 10.2 禁止的操作

```
1. 禁止直接翻译源代码（逐行转写）——构成派生作品
2. 禁止复制注释和文档字符串——文字作品受版权保护
3. 禁止复制测试用例的输入输出——测试数据受版权保护
4. 禁止保留原系统的变量命名习惯——可能被认定为复制
5. 禁止保留原系统的代码组织结构——编译单元组织方式受版权保护
6. 禁止复制错误消息文本——文字作品
```

### 10.3 安全操作步骤

```
1. 读源码时只记架构思想和接口设计，不记实现细节
2. 实现时合上源码，凭理解的架构思想写
3. 接口签名参数名用目标语言风格，不做逐字对应
4. 注释全部用自己的话写，不翻译
5. 测试用例用自己的数据和场景
6. 错误消息用自己的措辞
7. 用目标语言特色（Python: context manager, async for；Rust: trait, enum）替代源语言特色
```

---

## 11. OpenCode 增强能力清单

### 11.1 可用的工具

| 能力 | 工具 | 适用场景 | 注意事项 |
|------|------|----------|----------|
| 代码搜索 | `explore` agent | 找文件、找模式、了解模块结构 | 只做广度，不做深度 |
| 外部搜索 | `librarian` agent | 查官方文档、找最佳实践 | 不要用于分析自己的代码库 |
| 架构咨询 | `oracle` agent | 复杂设计决策、2+ 次修复失败后 | 贵，只用在关键决策点 |
| 计划审查 | `momus` agent | 评估计划的完整性和可执行性 | 把计划丢给它批评 |
| 并行实现 | `task(category="quick")` | 单一文件修改、适配器实现 | 不适合核心架构决策 |
| 流程持久化 | Loop Engineering | 多轮迭代开发 | 写状态文件 `.opencode/loop-state/` |
| 代码审查 | `review-work` skill | 实现完成后的全面审查 | 启动 5 个并行审查代理 |
| 契约测试 | pytest | 验证接口契约 | 在每个 Phase 开始时写 |
| 类型检查 | mypy strict | 确保接口一致性 | 在每次提交前运行 |

### 11.2 实战有用的模式

```python
# 模式 1: 批量文件阅读（并行 read）
# 核心文件用自己的 read 工具，不做代理委托
async def read_core_files():
    files = ["file1.py", "file2.py", "file3.py"]
    # 并行读取
    contents = await asyncio.gather(*[read(f) for f in files])
    
# 模式 2: Agent 辅助找文件（explore 适合）
# 让 Agent 找出所有相关文件路径，然后自己读
task(subagent_type="explore", prompt="Find all tool implementation files in src/tools/")
# 收到结果后，用 read 读每个文件

# 模式 3: 契约测试优先
# 在实现之前写测试，确保接口设计是可测试的
def test_llm_stream_contract():
    """任何 LLMProvider 实现都必须通过此测试"""
    ...
```

### 11.3 实战无用的模式

```python
# ❌ 不要用 deep agent 做多文件分析
# 30 分钟超时 + 上下文压缩 → 22/22 全部失败
task(category="deep", prompt="Analyze all files in packages/core/src/session/")
# → 超时，结果丢失

# ✅ 应该: 自己读
for f in ["file1.py", "file2.py", ...]:
    content = read(f)
    analyze(content)
```

---

## 12. 反模式清单

### 12.1 分析的错误模式

```
❌ "一次性部署所有 Agent 分析所有模块"
   → 22 个任务超时，白白浪费 4 小时
   ✅ 应该: 核心文件自己读，Agent 只做文件发现

❌ "相信 Agent 能理解架构并给出设计方案"
   → Agent 无法理解跨 30+ package 的复杂依赖
   ✅ 应该: 用自己的脑子理解架构，Agent 只执行具体任务

❌ "在范围明确的探索中启动过多背景任务"
   → 背景任务开销大，超时风险高
   ✅ 应该: 启动一个 `explore` 就够了, 不要同时开 14 个
```

### 12.2 实现的错误模式

```
❌ "先写实现，再补接口"
   → 模块之间数据格式无法对齐，集成时全是 bug
   ✅ 应该: 接口定义→契约测试→实现

❌ "大量修改旧代码来适配新架构"
   → 旧逻辑+新改动耦合，bug 难以定位
   ✅ 应该: 旧代码不动，新代码适配器包装

❌ "一次性切换所有模块到新架构"
   → 出问题不知道是哪个模块的锅
   ✅ 应该: 逐个模块切换，每个模块先 A/B 测试
```

### 12.3 验证的错误模式

```
❌ "只跑单元测试"
   → 单元测试覆盖不了集成问题
   ✅ 应该: 契约测试 + 集成测试 + E2E 三级验证

❌ "跳过类型检查"
   → 接口参数错误上线才能发现
   ✅ 应该: mypy strict 在 CI 中阻塞合并

❌ "手动验证 == 不验证"
    → 人眼看不出的类型错误就是运行时 bug
    ✅ 应该: 所有验证自动化
```

### 12.4 Loop Engineering 的错误模式

```
❌ "一次循环迭代做所有模块"
    → 上下文爆炸、30 分钟超时、Agent 丢任务
    ✅ 应该: 一个迭代只做一个模块（或一个子系统）

❌ "不使用状态文件，靠 Agent 记忆"
    → 会话压缩/超时后，Agent 不记得上次做了什么
    ✅ 应该: 每次迭代开始读 `.opencode/loop-state/current.json`，结束写它

❌ "同一个 Agent 既写代码又验证"
    → Agent 对自己的代码天然 bias，遗漏 67% 的缺陷（Addy Osmani 数据）
    ✅ 应该: Maker/Checker 分离——不同的 Agent 或不同的 task 做验证

❌ "并行实现不隔离 worktree"
    → 两个 Agent 同时修改同一文件，互相覆盖
    ✅ 应该: 2+ 并行任务必须使用 `git worktree add` 隔离

❌ "发现问题只修不记录"
    → 同样的 bug 在下一轮迭代或下一个模块中再次出现
    ✅ 应该: 每次发现问题后执行 Ratchet——追加测试 + 更新 AGENTS.md

❌ "不停迭代，没有停止条件"
    → 成本无限增长，资源耗尽
    ✅ 应该: 每个迭代前估算成本，每个迭代结束时检查停止条件

❌ "SHIP 之后不归档状态"
    → 后续的 bugfix 新循环失去了前面的上下文
    ✅ 应该: 循环终止时将 `.opencode/loop-state/` 归档
```

---

## 13. 检查表

### Phase 0: 分析完成时

- [ ] 项目文件树已绘制
- [ ] 包依赖关系已理解
- [ ] 核心数据流（请求→响应）已绘制 ASCII 流程图
- [ ] 所有模块按五维分析完成
- [ ] 差距分析表已创建
- [ ] 错误处理策略已记录
- [x] 🔄 状态文件已更新: `.opencode/loop-state/current.json`
- [x] 🔄 当前迭代编号已确认
- [x] 🔄 停止条件检查已执行

### Phase 1: DEFINE 完成时

- [ ] 所有跨模块数据模型已定义（dataclass）
- [ ] 所有模块接口已定义（ABC）
- [ ] 错误模型已定义（10 种 reason）
- [ ] 生命周期契约已记录
- [ ] 接口文档已归档到 `openspec/specs/`
- [ ] 契约测试已编写
- [x] 🔄 接口定义路径已记录到状态文件
- [x] 🔄 成本估算已更新（§2.7）
- [x] 🔄 本迭代周期确认：只定义了一个模块的接口

### Phase 2: PLAN 完成时

- [ ] 所有原子任务已列出
- [ ] 依赖关系已标注
- [ ] 并行机会已识别
- [ ] 每个任务有预估工时
- [ ] 每个任务有验收标准
- [x] 🔄 每个任务标注了成本等级（XS/S/M/L/XL）
- [x] 🔄 并行任务已标注是否需要 worktree 隔离
- [x] 🔄 状态文件已更新任务列表和总成本估算

### Phase 3: BUILD 完成时

- [ ] 模块实现遵循接口定义
- [ ] 旧代码通过适配器复用
- [ ] 所有契约测试通过
- [ ] 类型检查通过
- [ ] 没有违反分层依赖
- [x] 🔄 并行实现使用了 worktree 隔离（§2.5）
- [x] 🔄 实际成本已记录到状态文件
- [x] 🔄 实现文件列表已更新到状态文件

### Phase 4: VERIFY 完成时

- [ ] 契约测试全部通过
- [ ] 集成测试全部通过
- [ ] E2E 测试全部通过
- [ ] 新旧路径结果在测试用例上一致
- [x] 🔄 停止条件检查已执行（§2.3）
- [x] 🔄 验证结果已记录到状态文件
- [x] 🔄 如果验证失败，已按 §7.3 回退到正确 Phase

### Phase 5: REVIEW 完成时

- [ ] 架构合规检查通过
- [ ] 接口一致性检查通过
- [ ] 错误处理全覆盖检查
- [ ] 测试覆盖所有接口方法
- [x] 🔄 Ratchet 检查已执行（§2.6）——问题已转化为测试/规则/Skill
- [x] 🔄 已决定下一方向：下一个模块迭代（→ Phase 0）或 SHIP（→ Phase 6）
- [x] 🔄 状态文件已更新，指向下一 Phase

### Phase 6: SHIP 完成时

- [ ] 功能开关逐个打开
- [ ] 每个开关打开后有回滚能力
- [ ] 旧代码引用已全部迁移
- [ ] 旧文件已删除
- [ ] 最终清理提交完成
- [x] 🔄 最终状态已归档为 `.opencode/loop-state/final.json`
- [x] 🔄 临时 worktree 已清理
- [x] 🔄 所有功能开关的旧路径已删除

---

## 14. Loop 循环控制速查表

### 14.1 状态文件操作

```bash
# 读取当前状态
cat .opencode/loop-state/current.json

# 写入状态（每次迭代结束时）
cat > .opencode/loop-state/current.json << 'EOF'
{
  "phase": "Phase N: NAME",
  "iteration": 3,
  "module": "ModuleName",
  "status": "ready",
  "cost_estimate": 2.50,
  "findings": [],
  "next_action": "下一步描述"
}
EOF

# 归档历史迭代
cp .opencode/loop-state/current.json ".opencode/loop-state/iteration-003.json"
```

### 14.2 停止条件检查速查

| 检查项 | 命令 | 触发行动 |
|--------|------|----------|
| 验证全通过 | `pytest && mypy && ruff` → 0 | 进入下一 Phase |
| 迭代超限 (>10) | `cat current.json | jq .iteration` | 标记风险，上报 |
| 成本超限 (>$15) | `cat cost-log.json | jq .total_cost` | 停止，报告消耗 |
| 需人工介入 | `cat current.json | jq .status` == NEEDS_HUMAN | 中断，等待输入 |
| 不可恢复错误 | 架构缺陷/依赖缺失 | 记录上下文，终止 |

### 14.3 成本等级速查

| 等级 | 范围 | 行动 |
|------|------|------|
| XS | $0-1 | 直接做 |
| S | $1-3 | 开始前确认预算 |
| M | $3-8 | 拆分为多个 S 任务 |
| L | $8-15 | 需要人工审批 |
| XL | $15+ | 禁止，必须重新计划 |

### 14.4 Worktree 隔离速查

```bash
# 创建
git worktree add ../loop-<name> -b loop/<name>

# 工作
# (在 ../loop-<name> 中运行 Agent)

# 合并
cd ../loop-<name>
git add -A && git commit -m "feat: 实现 [module] [iteration N]"
cd /main/repo
git merge loop/<name> --no-ff -m "merge: [module] [iteration N]"

# 清理
git worktree remove ../loop-<name>
git branch -d loop/<name>
```

### 14.5 常见循环模式

| 场景 | 循环结构 | 典型迭代次数 |
|------|----------|-------------|
| 新模块实现 | 0→1→2→3→4→5(→0→...) | 1-3 轮 |
| Bugfix | 1→3→4→5 | 1-2 轮 |
| 接口变更 | 1→2→3→4→5 | 2-3 轮 |
| 重构（行为不变） | 3→4→5 | 1-2 轮 |
| 全系统上线 | ...→5→6 | 最终一次 |

---

> 本文档基于 CScode (Python) 复刻 OpenCode (TypeScript/Effect) 的实战经验总结。
> 方法论适用于任何目标编程语言和任何被复刻系统。
> 核心信条: **接口契约决定集成质量，不是实现质量。**

---

## 15. 智能体系统分析及画像文档

> 本章节定义了系统在完成开发后应生成的完整画像文档规范。智能体维护者、开发者用于维护、调试、优化迭代的核心参考文档。

### 15.2 文档版本与更新记录

| 版本 | 更新时间 | 更新人 | 变更内容 |
|------|----------|--------|----------|
| 1.0 | 2025-06-28 | AI Agent | 初始版本，完整系统画像 |

### 15.3 项目归属与干系人

| 角色 | 职责 |
|------|------|
| 项目负责人 | 整体规划、决策 |
| 核心开发者 | 核心模块开发 |
| 维护团队 | 日常维护、Bug修复 |

### 15.4 环境说明

```
开发环境: http://localhost:5173 (前端) / http://localhost:8000 (后端)
测试环境: https://test.cscode.xxx.com
生产环境: https://cscode.xxx.com
```

### 15.5 术语定义

| 术语 | 定义 |
|------|------|
| MCP | Model Context Protocol，模型上下文协议 |
| Plugin | 可动态加载的扩展模块 |
| Skill | 预定义的 Agent 行为模式 |
| Event Sourcing | 以事件为中心的架构模式 |
| Session | 用户与 AI 的交互上下文 |

---

### 二、项目概述

### 15.6 项目定位

- **核心问题**: 为开发者提供 AI 编程辅助
- **目标用户**: 个人开发者、软件开发团队
- **差异**: 开源可自部署、支持多 LLM Provider

### 15.7 核心特性

| 特性 | 优先级 |
|------|--------|
| 多 LLM Provider 支持 | P0 |
| 完整工具系统 | P0 |
| 多会话管理 | P0 |
| Plugin 扩展 | P1 |
| Skill 扩展 | P1 |
| MCP 支持 | P1 |

### 15.8 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 前端 | React | 18.x |
| 状态管理 | Zustand | 4.x |
| 构建 | Vite | 5.x |
| 后端 | FastAPI | 0.11x |
| 桌面 | Tauri | 2.x |
| 存储 | SQLite | 3.x |

---

### 三、架构设计

### 15.9 分层架构

```
UI Layer → App Layer → Core Layer → LLM Layer → Provider Layer → Schema Layer → Storage Layer
```

### 15.10 依赖规则

- **允许**: Schema → LLM → Core → App → Server → UI
- **禁止**: 跨层调用、循环依赖

### 15.11 部署架构

**单机部署**: Tauri/App + FastAPI + SQLite
**集群部署**: Load Balancer + 3x CScode Node + PostgreSQL

### 15.12 容错与高可用

| 场景 | 降级策略 |
|------|----------|
| LLM 不可用 | 返回友好错误提示 |
| 数据库失败 | 内存缓存 |
| 网络超时 | 重试3次 |

---

### 四、模块详解

### 15.13 Schema 模块

- **职责**: 定义所有数据类型，零运行时依赖
- **核心逻辑**: User Input → Message → LLMRequest → LLMEvent → SessionState

### 15.14 LLM 模块

- **职责**: LLM 协议适配和调用抽象
- **核心逻辑**: create_request() → route() → provider.chat() → parse_response()

### 15.15 Providers 模块

| Provider | 文件 |
|----------|------|
| OpenAI | openai.py |
| Anthropic | anthropic.py |
| Ollama | ollama.py |

### 15.16 Core 模块

| 子模块 | 职责 |
|--------|------|
| session.py | Event Sourcing 会话管理 |
| coordinator.py | 会话串行化 |
| engine.py | Agent 执行引擎 |

### 15.17 Tools 模块

read, write, edit, bash, grep, glob, ls, webfetch, websearch, browser, question, skill, todowrite

### 15.18 MCP 模块

- 协议版本: 2025-03-26
- 连接方式: stdio (子进程)

### 15.19 Plugins 模块

加载流程: discover() → load_plugin() → importlib → __tools__

### 15.20 Skills 模块

Skill 结构: name, slug, content, path, description

---

### 五、API 接口

### 15.21 后端端点

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/health | 健康检查 |
| POST | /api/chat | 发送消息 |
| POST | /api/chat/stream | 流式聊天 |
| GET | /api/events | 获取事件 |
| GET | /api/sessions | 会话列表 |
| POST | /api/sessions | 创建会话 |
| DELETE | /api/sessions/{id} | 删除会话 |
| POST | /api/sessions/{id}/stop | 停止会话 |
| PATCH | /api/sessions/{id} | 更新会话 |
| POST | /api/sessions/{id}/export | 导出 |
| POST | /api/sessions/import | 导入 |
| GET | /api/files/search | 文件搜索 |
| GET | /api/config | 获取配置 |
| POST | /api/config | 保存配置 |

### 15.22 前端调用

```typescript
api.chat.send(message, sessionId);
api.sessions.list();
api.config.get();
```

### 15.23 接口版本管理

当前版本: v1，URL 路径: /api/v1/*

---

### 六、数据模型

### 15.24 核心模型

**SessionState**: session_id, title, provider, model, messages, status, created_at, updated_at, seq

**Message**: role, parts, id, created_at

**LLMEvent**: TextDelta, TextEnded, ToolCallStarted, ToolCallEnded, ToolResult, Finish

### 15.25 数据生命周期

| 数据类型 | 过期策略 |
|----------|----------|
| Session | 90天无活动 |
| Event | 压缩后归档 |
| Config | 永不过期 |

---

### 七、调用链路

### 15.26 完整流程

1. 用户输入 → 2. 前端调用 API → 3. FastAPI 创建 Session → 4. create_agent_v2() → 5. AgentEngine 执行 → 6. LLM Service 路由 → 7. Provider 调用外部 API → 8. SSE 流式响应 → 9. EventStore 持久化 → 10. 前端更新

### 15.27 异常处理

| 场景 | 策略 |
|------|------|
| 网络超时 | 重试3次，指数退避 |
| 401错误 | 提示检查API Key |
| 500错误 | 返回友好错误 |

---

### 八、扩展机制

### 15.28 Plugin 开发

```python
class MyTool(BaseTool):
    name = "my_tool"
    async def execute(self, **kwargs):
        return "result"

__tools__ = [MyTool()]
```

### 15.29 Skill 开发

放置 .md 文件到 skills/ 目录，SkillLoader 自动发现

---

### 九、存储架构

### 15.30 Event Store

- 存储介质: SQLite
- 性能优化: 批量写入，定期压缩

### 15.31 Database

- 开发: SQLite
- 生产: PostgreSQL

---

### 十、目录结构

### 15.32 完整文件树

```
src/cscode/
├── schema/      # 数据模型
├── llm/         # LLM协议层
├── providers/   # LLM提供商
├── core/        # 核心逻辑
├── tools/       # 工具实现
├── app/         # 应用层
├── server/      # FastAPI服务
├── mcp/         # MCP协议
├── plugins/     # 插件系统
├── skills/      # 技能系统
├── storage/     # 存储层
├── web/         # React前端
├── tui/         # 终端UI
└── utils/       # 工具函数
```

---

### 十一、维护与调试

### 15.33 常见故障排查

**LLM调用失败**: 检查API Key → 检查网络 → 查看日志 → 确认Provider状态

**Plugin加载异常**: 检查目录结构 → 验证__init__.py → 检查__tools__列表

### 15.34 日志说明

| 日志 | 位置 |
|------|------|
| Server | /tmp/cscode-server.log |
| LLM | cscode.llm |
| Tools | cscode.tools |

---

### 十二、优化迭代

### 15.35 当前瓶颈

- LLM响应速度 (P0)
- 大文件处理 (P1)
- 并发能力 (P1)

### 15.36 优化方向

- 流式响应优化 (P0)
- 缓存层 (P1)
- 分布式 (P2)

> 本画像文档由智能体在系统开发完成后自动生成，用于后续维护、调试和迭代参考。

