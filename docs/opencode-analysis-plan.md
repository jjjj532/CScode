# OpenCode 深度分析方案
## 问题：为什么"看着像但用起来差很远"？

### 根因分析

| CScode 过去做法 | 真正需要什么 | 差距根源 |
|----------------|--------------|---------|
| 分析有什么模块 | 理解模块间如何**协作** | 集成逻辑 |
| 复制函数签名 | 复制**边界条件**处理 | 错误处理 |
| 实现功能点 | 实现**交互细节** | 用户体验 |
| 简单测试 | 测试**边界条件** | 质量验证 |

---

## 分析原则：五维分析法

```
不只分析"有什么"，而是分析：
├── 维度1: 结构 (Structure)    - 有什么模块/类/函数
├── 维度2: 行为 (Behavior)     - 具体场景下如何响应
├── 维度3: 路径 (Flow)         - 关键操作的完整调用链
├── 维度4: 边界 (Edge)         - 错误/超时/异常如何处理
└── 维度5: 差异 (Diff)         - 与 CScode 的核心差异点
```

---

## 分析策略：目标驱动 + 垂直切片

### 不是横向扫描所有代码，而是纵向理解关键功能路径

```
一个用户请求的处理路径：
User: "修复这个bug" 
  → Agent 接收 (如何解析意图?)
  → 规划 (如何决定用哪些 tool?)
  → Tool 执行 (如何处理超时/失败?)
  → 结果整合 (如何生成响应?)
  → UI 展示 (如何渲染消息?)
```

**分析方法：** 追踪这整个路径，理解每个环节的实现细节。

---

## 执行计划：三层分析

### Layer 1: 核心层 (必须深入理解)

| 模块 | 分析重点 | 产出 |
|-----|---------|------|
| `packages/core` | Agent 决策流程、状态机、tool 调用机制 | `core-behavior-flow.md` |
| `packages/llm` | 模型调用、流式响应、function calling、错误处理 | `llm-interface-analysis.md` |
| `packages/protocol` | 消息格式、session 结构、event 定义 | `protocol-schema.md` |

### Layer 2: 能力层 (需要理解实现)

| 模块 | 分析重点 | 产出 |
|-----|---------|------|
| `packages/function` | Tool 定义格式、参数解析、执行模型 | `tool-model.md` |
| `packages/agent` | Agent 实现、多 agent 切换机制 | `agent-impl.md` |

### Layer 3: 交互层 (参考实现)

| 模块 | 分析重点 | 产出 |
|-----|---------|------|
| `packages/console` | TUI 渲染、用户交互 | (参考) |
| `packages/desktop` | 桌面端集成 | (参考) |

---

## 具体执行：并行探针 + 深度分析

### Step 1: 克隆源码 + 生成结构图

```bash
# 克隆 OpenCode 到参考目录
git clone https://github.com/anomalyco/opencode.git opencode-ref/

# 生成整体结构 (使用 codemap skill)
skill(name="codemap")
```

### Step 2: 并行探针分析核心模块

启动 3 个 explore agent 同时分析（20 分钟内完成）：

```python
# 探针 1: Agent 核心 - 决策流程
task(subagent_type="explore", 
     prompt="深入分析 packages/core 的 agent 决策流程：
     1. Agent 如何接收用户输入
     2. 如何决定使用哪些 tools
     3. 如何处理 tool 返回结果
     4. 状态机如何转换
     5. 完整的请求-响应循环是什么
     产出: 详细的调用流程图和关键代码位置",
     run_in_background=true)

# 探针 2: LLM 接口 - 边界处理
task(subagent_type="explore",
     prompt="深入分析 packages/llm 的接口实现：
     1. 如何处理 API 超时
     2. 如何处理 rate limit
     3. 流式响应如何处理中断
     4. Function calling 的完整流程
     5. 错误如何转化为你用户消息
     产出: 错误处理流程图和关键代码位置",
     run_in_background=true)

# 探针 3: Tool 执行 - 安全边界
task(subagent_type="explore",
     prompt="深入分析 packages/function 的 tool 执行：
     1. Tool 参数如何验证
     2. 如何防止命令注入
     3. 执行超时如何处理
     4. 执行结果如何返回给 agent
     5. 危险 tool (bash/write) 的安全限制
     产出: 安全边界处理文档和关键代码位置",
     run_in_background=true)
```

### Step 3: 对比差异点 (关键!)

不是泛泛比较，而是**针对具体问题**搜索：

```python
# 对比 CScode 和 OpenCode 的具体差异
task(subagent_type="explore",
     prompt="对比 CScode (src/cscode/) 和 OpenCode (opencode-ref/packages/core) 
     在以下方面的具体实现差异：
     1. agent 决策逻辑
     2. session 状态管理
     3. tool 调用机制
     4. 错误处理方式
     找出具体差异点，说明 OpenCode 为什么会这样设计",
     run_in_background=true)
```

### Step 4: 边界条件分析

```python
# 分析 OpenCode 的边界处理
task(subagent_type="explore",
     prompt="在 OpenCode 源码中搜索以下边界条件的处理：
     1. 用户输入为空时的处理
     2. API 返回超长内容时的处理
     3. 并发请求的处理
     4. 网络中断后的恢复
     5. session 过期处理
     产出: 边界条件处理文档",
     run_in_background=true)
```

### Step 5: 产出对齐文档

每次分析完成后，产出结构化文档：

```
docs/
├── opencode-analysis/
│   ├── 01-core-agent-flow.md        # Agent 决策流程
│   ├── 02-llm-error-handling.md     # LLM 错误处理
│   ├── 03-tool-security.md          # Tool 安全边界
│   ├── 04-cscode-diff.md            # 与 CScode 差异点
│   ├── 05-edge-cases.md             # 边界条件处理
│   └── summary.md                   # 汇总报告
```

---

## 质量保证：验证分析是否正确

### 检查清单

- [ ] 每个核心模块至少有 3 个具体代码示例
- [ ] 每个行为流程都有调用链说明
- [ ] 每个边界条件都有处理方式说明
- [ ] 每个差异点都说明了"为什么"
- [ ] 文档可以回答"OpenCode 如何处理 X 问题"

### 验证方法

用分析结果**回答具体问题**，例如：
- "OpenCode 如何处理 bash tool 执行超时？" → 能从文档中找到答案
- "OpenCode agent 如何决定下一个 tool？" → 能从文档中找到答案

---

## 时间预算

| 阶段 | 时间 | 产出 |
|-----|------|------|
| 环境搭建 | 10 min | 源码就绪 |
| 核心分析 (3 并行) | 30 min | 3 个深度文档 |
| 差异对比 | 20 min | 差异分析报告 |
| 边界分析 | 20 min | 边界处理文档 |
| 汇总整理 | 10 min | 完整对齐文档 |
| **总计** | **~90 min** | **可直接指导开发** |

---

## 启动命令

```bash
# 方式1: 使用已克隆的源码 (如果网络允许)
git clone https://github.com/anomalyco/opencode.git ../opencode-ref/

# 方式2: 使用 Context7 在线分析 (当前使用的方式)
# 核心文档已通过 Context7 获取并分析
```

---

## 预期产出

分析完成后，你将得到：

1. **Core Behavior Flow**: Agent 如何做决策的完整路径
2. **LLM Interface Analysis**: LLM 调用的边界处理细节
3. **Tool Security Model**: Tool 执行的安全边界
4. **CScode Gap Analysis**: 与 CScode 的具体差异点和原因
5. **Edge Case Handling**: 边界条件处理方式

**这些文档将直接指导后续开发，确保不是"看着像"而是"行为一致"。**