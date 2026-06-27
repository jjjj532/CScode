# OpenCode 深度分析报告 - 五维分析法

> 基于 Context7 文档分析产出
> 分析时间: 2025-06-26

---

## 核心发现：为什么"看着像但用起来差很远"？

### 根因分析

| CScode 过去做法 | OpenCode 实际做法 | 差距根源 |
|----------------|-------------------|---------|
| 简单函数调用 LLM | Effect.ts 纯函数式流处理 | **调用模型** |
| 复制 tool 定义 | Tool.definition + Tool.make 分离 | **类型安全** |
| 错误直接抛异常 | LLMError 分类 + formatError 处理 | **错误模型** |
| 简单状态存储 | Event Sourcing + Session 持久化 | **状态管理** |
| 固定超时 | timeout + turnTimeout 分离配置 | **超时控制** |
| 粗粒度权限 | 精确的 permission 规则匹配 | **安全模型** |

---

## 维度1: 结构分析 (Structure)

### 核心模块

```
OpenCode Architecture:
├── packages/llm       # LLM 接口层 (Effect.ts)
├── packages/function  # Tool 定义 + 执行
├── packages/core      # Agent 核心逻辑
├── packages/protocol  # 消息格式定义
├── packages/opencode  # 主应用
├── packages/console   # TUI
├── packages/desktop   # 桌面端
└── packages/web       # Web UI
```

### 关键接口

**Tool 定义 (packages/function):**
```typescript
interface Tool.Def<Parameters, M> {
  id: string
  description: string
  parameters: Parameters  // Effect Schema
  jsonSchema?: JSONSchema7
  execute(args, ctx) -> Effect<ExecuteResult<M>>
  formatValidationError?(error): string
}
```

**LLM Error 模型:**
```typescript
type LLMError =
  | AuthenticationError
  | InvalidRequestError
  | UnsupportedCapabilityError
  | ToolBindingError
  | TransportError
  | ProviderResponseError
  | InvalidProviderOutputError
  | HookError
```

---

## 维度2: 行为分析 (Behavior)

### Agent 决策流程

```
User Input
    ↓
Agent 接收 + 解析意图
    ↓
LLM.generate() ← 注入 tools + prompt
    ↓
流式响应处理 (Stream)
    ↓
检测 ToolCall 事件
    ↓
ToolRuntime.dispatch(tools, call)
    ↓
执行 Tool + 处理结果
    ↓
将结果注入下一轮 LLM 请求
    ↓
循环直到无 ToolCall
    ↓
生成最终响应
```

### Tool 自动循环机制

```typescript
// OpenCode 的关键设计：Tool 调用自动循环
const result = yield* LLM.generate({
  model,
  prompt,
  tools,  // 传入 tools 定义 + execute handlers
})

// 运行时自动：
// 1. 提取 tool definitions 发送给 LLM
// 2. 检测 tool_call 事件
// 3. dispatch 执行
// 4. 将结果注入下一轮请求
// 5. 继续直到 LLM 不再调用 tool
console.log(result.toolExecutions)  // 记录所有执行
```

---

## 维度3: 路径分析 (Flow) - 关键调用链

### Session 创建和恢复

```typescript
// Session 创建
sessions.create({ id?, location, ... })
  → 生成 Session ID
  → 存储位置映射
  → 返回 Session 引用

// Session 恢复
SessionExecution.resume(sessionID)
  → SessionStore.get(sessionID)           // 获取 session 状态
  → LocationServiceMap.get(location)      // 获取位置服务
  → SessionRunner.run({ sessionID })      // 执行
```

### Tool 执行流程

```typescript
// 1. LLM 返回 tool_call
const call = events.find(LLMEvent.is.toolCall)

// 2. 权限检查 (关键!)
ctx.ask({                           // 请求用户批准
  action: "bash", 
  resource: "git status"
})

// 3. 执行
const dispatched = yield* ToolRuntime.dispatch(tools, call)

// 4. 结果处理
// - 成功: 返回 ExecuteResult
// - 失败: formatError 格式化为用户消息
```

---

## 维度4: 边界分析 (Edge Cases)

### 超时控制

```typescript
yield* LLM.generate({
  model,
  prompt,
  timeout: "2 minutes",      // 整个运行超时 (包括 tool 执行)
  turnTimeout: "30 seconds", // 每轮 provider 超时
  tools,
})
```

### 错误处理模型

```typescript
// 每个 Tool 可定义 formatError
const getWeather = Tool.make({
  description: "Get weather",
  parameters: WeatherInput,
  success: WeatherOutput,
  execute: getWeather,
  formatError: (error) => ({
    type: "text",
    text: `Weather lookup failed: ${error.message}`,
  }),
})

// LLMError 分类处理
if (error.name === "StructuredOutputError") {
  console.log("Retries:", error.retries)
}
```

### 权限模型 (关键差异!)

```typescript
// CScode: 简单 allow/deny
permissions: ["bash", "edit"]

// OpenCode: 精确规则匹配
permission: {
  "bash": {
    "*": "ask",           // 默认询问
    "git *": "allow",    // 允许 git 命令
    "rm *": "deny",      // 禁止 rm
    "npm *": "allow",    // 允许 npm
  },
  "edit": {
    "*": "deny",
    "packages/web/src/**/*.mdx": "allow"
  }
}

// 规则按顺序匹配，最后一个匹配的规则生效
```

### 上下文压缩

```typescript
// 配置
{
  "compaction": {
    "auto": true,
    "prune": true,
    "keep": { "tokens": 20000 },  // 保留最近 20k tokens
    "buffer": 10000               // 缓冲区域
  }
}
```

---

## 维度5: 差异分析 (Diff) - CScode 对比

### 1. Tool 定义方式

| CScode (现状) | OpenCode (目标) |
|--------------|-----------------|
| 简单函数定义 | Tool.definition + Tool.make 分离 |
| 无类型验证 | Effect Schema 编译时验证 |
| 错误直接抛 | formatError 格式化错误消息 |
| 无 success schema | success schema 定义返回类型 |

### 2. LLM 调用方式

| CScode (现状) | OpenCode (目标) |
|--------------|-----------------|
| 手动调用 API | LLM.generate() 包装 |
| 手动处理 tool loop | 自动 tool 循环 |
| 简单流处理 | Stream 事件驱动 |
| 固定超时 | timeout + turnTimeout 可配置 |

### 3. 状态管理

| CScode (现状) | OpenCode (目标) |
|--------------|-----------------|
| 简单 SQLite | Event Sourcing |
| 无 Session 恢复 | 完整的 Session.resume() |
| 无消息持久化 | 消息 + parts 分层存储 |

### 4. 权限控制

| CScode (现状) | OpenCode (目标) |
|--------------|-----------------|
| 粗粒度 allow/deny | 精确规则匹配 |
| 无用户确认 | ask/allow/deny 三级 |
| 无资源匹配 | glob 模式匹配 |

### 5. 错误处理

| CScode (现状) | OpenCode (目标) |
|--------------|-----------------|
| 异常直接抛 | LLMError 分类 |
| 无重试机制 | 自动重试 (StructuredOutput) |
| 无边界提示 | 明确的错误消息格式化 |

---

## 核心差异总结

### OpenCode 关键技术选型

1. **Effect.ts** - 纯函数式编程，类型安全，副作用管理
2. **Event Sourcing** - 完整的 Session 状态持久化和恢复
3. **Schema 验证** - 编译时类型检查 + 运行时验证
4. **精确权限模型** - 基于规则的安全控制
5. **自动 Tool 循环** - LLM.generate 内置工具调用处理

### CScode 需要改进的点

1. **Tool 系统**: 分离 definition 和 implementation，添加 success schema
2. **LLM 层**: 使用 Effect.ts 重构，添加自动 tool 循环
3. **错误模型**: 实现 LLMError 分类和 formatError 机制
4. **Session**: 完善 Event Sourcing 和恢复机制
5. **权限**: 实现精确规则匹配和用户确认流程

---

## 后续开发指导

基于此分析，开发优先级：

### P0 (必须对齐)
1. Tool.definition + Tool.make 分离
2. LLM.generate 自动 tool 循环
3. 精确权限规则匹配
4. Session 恢复机制

### P1 (重要改进)
1. Effect.ts 重构 (或等效方案)
2. LLMError 分类
3. 上下文压缩

### P2 (优化)
1. 超时精细控制
2. 流式响应优化
3. 消息 parts 分层存储