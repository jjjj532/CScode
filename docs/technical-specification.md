# CScode Technical Specification

> 最后更新: 2026-06-27
>
> 本文档是 CScode 系统的**唯一权威技术规格**。所有架构决策、模块边界、接口契约在此记录。
> 开发新功能或修改架构前，先读本文档确认设计意图。

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Dependency Order](#2-dependency-order)
3. [Schema Layer](#3-schema-layer)
4. [Tool System v2](#4-tool-system-v2)
5. [LLM Layer](#5-llm-layer)
6. [Core Layer](#6-core-layer)
7. [App Layer](#7-app-layer)
8. [Development Conventions](#8-development-conventions)
9. [Architecture Decision Records](#9-architecture-decision-records)
10. [Appendices](#10-appendices)

---

## 1. Architecture Overview

CScode follows a strict **three-layer architecture** with unidirectional dependencies:

```
┌──────────────────────────────────────────────────────────┐
│                    App Layer                              │
│  CLI (cli.py) | TUI (tui/) | Web (web/) | Desktop (app)   │
│  Server (server/app.py)                                    │
├──────────────────────────────────────────────────────────┤
│                    Core Layer                              │
│  SessionRunner | ToolRegistry | PermissionV2              │
│  Config | Events | Compression | SubAgent                │
├──────────────────────────────────────────────────────────┤
│                    LLM Layer                               │
│  LLMService.generate/stream | Route | Provider Adapters   │
├──────────────────────────────────────────────────────────┤
│                    Schema Layer (zero deps)                │
│  Messages | Errors | Events | IDs | Options | Tool Defs  │
└──────────────────────────────────────────────────────────┘

        schema → llm → core → app
        (每层只依赖下层，禁止跨层 import)
```

### 1.1 Design Principles

| Principle | Description |
|-----------|-------------|
| **接口契约优先** | 先定义接口（ABC + dataclass），再写实现，再写测试 |
| **分层独立** | 每层只依赖正下层，禁止跨层 import |
| **旧代码不动** | 新代码适配器模式调用旧实现，旧代码一行不删不改 |
| **双轨并行** | 新旧系统通过 feature flag 共存，全验证通过后才删除旧代码 |
| **TDD 强制** | 每个模块先写契约测试，再写实现 |
| **类型安全** | 使用 Pydantic v2 + mypy strict，禁止 `Any`/`as any` |

### 1.2 Design Origin

本文档源于对 OpenCode (TypeScript/Effect) 的架构分析（[五维分析](opencode-analysis/five-dimension-analysis.md)、[源码分析](opencode-analysis/source-analysis.md)）。
CScode **不是** 1:1 翻译 OpenCode，而是**全新构建 + 接口驱动**——吸收 OpenCode 的架构思想，
用 Python 语言特性（Pydantic v2、async/await、dataclass、match/case）等效实现。

**知识产权保护：** 本文档记录的是架构思想和接口设计（不受版权保护），不包含 OpenCode 的实现逻辑、
注释文本或测试数据。详细边界见[复刻方法论](reimplementation-methodology.md) §10。

---

## 2. Dependency Order

### 2.1 Module Dependencies (Current & Planned)

```
Module              Depends On              Status
────────────────────────────────────────────────────────────
schema/             (none, zero deps)       ✅ 完成
tools2/             schema/tool.py          ✅ 完成
llm/                schema/*               ✅ 完成
core/ (new)         schema/* + llm/* + tools2/*  ✅ 基础完成 (待测试)
engine.py (legacy)  (existing)             🟡 旧代码不动
app/ (CLI/TUI/etc)  core/* + llm/*         ⏳ 未来
```

### 2.2 Import Rules

```python
# ✅ 允许
from cscode.schema import Message     # LLM 层可引入 Schema
from cscode.llm import LLMService     # Core 层可引入 LLM
from cscode.core import SessionRunner # App 层可引入 Core

# ❌ 禁止 — 跨层 import
from cscode.core import ...   # 在 LLM 层中（LLM 层不知道 Core 层的存在）
from cscode.app import ...    # 在 Core 层中（Core 层不知道 App 层的存在）
```

### 2.3 Module Loading Sequence (Build Order)

```
Phase 0: Schema 层        ← 已完成
Phase 1: Tool 系统 v2     ← 已完成  
Phase 2: LLM 层           ← 当前迭代
Phase 3: Core 层 (重构)   ← 下一轮迭代
Phase 4: App 层迁移       ← 最后
Phase 5: 清理旧代码       ← 最终
```

---

## 3. Schema Layer

**位置:** `src/cscode/schema/`
**状态:** ✅ 已完成 (零依赖，纯类型定义)

### 3.1 文件清单

| File | Purpose | Key Types |
|------|---------|-----------|
| `messages.py` | 消息 + Content Part 系统 | `Part` union (6 types), `Message`, `MessageRole` |
| `errors.py` | LLM 错误分类 | `LLMErrorReason` (10-class enum), `LLMError`, `ToolFailure` |
| `events.py` | LLM 流事件系统 | `LLMEvent` union (15 types including Pending) |
| `ids.py` | Branded ID 类型 | `SessionID`, `ToolCallID`, `MessageID`, `ModelID`, `ProviderID` |
| `options.py` | 生成参数 | `GenerationOptions`, `ProviderOptions`, `CachePolicy` |
| `tool.py` | Tool 定义 + ToolChoice | `ToolDefinition`, `ToolChoice` |

### 3.1 Message Part System

```
┌──────────────────────────────────────────┐
│  Message                                  │
│  ├── role: str                            │
│  ├── parts: tuple[Part, ...]              │
│  └── id: MessageID | None                 │
│                                           │
│  Part = SystemPart                        │
│       | TextPart                          │
│       | MediaPart                         │
│       | ToolCallPart                      │
│       | ToolResultPart                    │
│       | ReasoningPart                     │
└──────────────────────────────────────────┘
```

所有 Part 都是 frozen dataclass，使用 `type` 字段做判别器，消费方用 `match/case` 做穷尽匹配。

### 3.2 Error Model

```python
LLMErrorReason (StrEnum, 10 flavors):
  INVALID_REQUEST      # 不可重试 — 修复请求
  NO_ROUTE             # 不可重试 — 修复配置
  AUTHENTICATION       # 不可重试 — 检查凭证
  RATE_LIMIT           # ✅ 可重试 — 背压重试
  QUOTA_EXCEEDED       # 不可重试 — 等待配额重置
  CONTENT_POLICY       # 不可重试 — 内容被拒
  PROVIDER_INTERNAL    # ✅ 可重试 — 服务端 5xx
  TRANSPORT            # 不可重试 — 网络层失败
  INVALID_PROVIDER_OUTPUT  # 不可重试 — 适配器 bug
  UNKNOWN_PROVIDER     # 不可重试 — 配置错误
```

只有 `RATE_LIMIT` 和 `PROVIDER_INTERNAL` 是可重试的（通过模块级 `_RETRYABLE` set 静态检查）。

### 3.3 LLM Event Stream

```
Pending
→ ReasoningStarted → ReasoningDelta* → ReasoningEnded
→ TextStarted → TextDelta* → TextEnded
→ ToolCallStarted → ToolCallDelta* → ToolCallEnded
→ ToolResult | ToolFailure
→ Finish | Error
```

(*) 可能产生 0 个或多个 delta 事件。共 15 种事件类型 + `assert_never()` 穷尽检查。

---

## 4. Tool System v2

**位置:** `src/cscode/tools2/`
**状态:** ✅ 已完成 (14 个工具 + 契约测试覆盖)

### 4.1 Core Interface

```python
class Tool(ABC, Generic[InputT, OutputT]):
    """Type-safe Tool with Pydantic-validated input/output."""
    name: str = ""
    description: str = ""
    input_schema: type[InputT]     # Pydantic BaseModel subclass
    output_schema: type[OutputT]   # Pydantic BaseModel subclass

    @abstractmethod
    async def execute(self, input: InputT) -> ToolResult[OutputT]: ...

    def to_definition(self) -> ToolDefinition: ...
    def format_error(self, error: Exception) -> str: ...

class ToolResult(Generic[OutputT]):
    success: bool
    data: OutputT | None = None
    error: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, str]
```

### 4.2 Registry & Materialize

```python
class ToolRegistry:
    def register(self, tool: Tool[Any, Any]) -> None: ...
    def get(self, name: str) -> Tool[Any, Any] | None: ...
    def list_tools(self) -> list[str]: ...
    def to_definitions(self) -> list[ToolDefinition]: ...

    # OpenCode 兼容的 materialize 模式:
    def materialize(self, tool_names: list[str] | None = None)
        -> tuple[list[ToolDefinition], settle]:
        """返回 (definitions_for_llm, settle_function).
        settle(name, args_dict) → ToolResult[Any]
        流程: decode(validate via Pydantic) → execute → encode
        """

    @staticmethod
    def parse_tool_call(raw: str | dict[str, object])
        -> tuple[str, dict[str, object] | None, str | None]:
        """解析 LLM tool call 返回格式 → (name, args, error)"""
```

### 4.3 Tool 清单

| Tool | Input | Output | 
|------|-------|--------|
| ReadTool | ReadInput(path) | ReadOutput(content, size, path) |
| WriteTool | WriteInput(path, content) | WriteOutput(path, size, message) |
| EditTool | EditInput(path, old_string, new_string) | EditOutput(path, replacement_count) |
| BashTool | BashInput(command, timeout) | BashOutput(output, exit_code) |
| GrepTool | GrepInput(pattern, path, include) | GrepOutput(matches, files_scanned) |
| GlobTool | GlobInput(pattern, path) | GlobOutput(matches) |
| LsTool | LsInput(path) | LsOutput(entries) |
| WebFetchTool | WebFetchInput(url, format, timeout) | WebFetchOutput(content, url, size) |
| WebSearchTool | WebSearchInput(query, num_results) | WebSearchOutput(results) [stub] |
| TodoWriteTool | TodoWriteInput(todos) | TodoWriteOutput(formatted, count) |
| QuestionTool | QuestionInput(question, options) | QuestionOutput(formatted) |
| SkillTool | SkillInput(name) | SkillOutput(message) [stub] |
| ApplyPatchTool | ApplyPatchInput(path, patch_content, strip) | ApplyPatchOutput(stdout) |
| BrowserTool | BrowserInput(action, url, selector, text, key, seconds) | BrowserOutput(result) |

### 4.4 与旧 `tools/` 的关系

```
src/cscode/
├── tools/        ← 旧系统（不动，一行不改）
├── tools2/       ← 新系统（类型安全，契约测试覆盖）
└── tools2/registry.py → 通过 materialize/settle 供 LLM 层使用
```

新代码引用 `tools2`，不引用 `tools`。旧代码通过适配器或直接切换方式迁移。

---

## 5. LLM Layer

**位置:** `src/cscode/llm/` (待创建)
**状态:** 🔜 **当前构建迭代**
**依赖:** `schema/*`

### 5.1 Responsibility

LLM 层负责所有与 LLM Provider 的通信。职责包括：

1. **`LLMService`** — 封装自动 tool 循环（`generate()` 方法级循环）
2. **Provider Adapters** — 将 schema 类型转为各 provider 的 API 格式
3. **Route 系统** — Protocol + Endpoint + Auth + Framing 四轴抽象
4. **Stream 处理** — 将 provider 原始响应转为 `LLMEvent` 事件流

### 5.2 LLMService interface (设计)

```python
class LLMService:
    """LLM 服务 — 封装自动 tool 循环。"""

    async def generate(
        self,
        model: ModelID,
        messages: list[Message],
        tools: list[Tool[Any, Any]] | None = None,
        system: str | None = None,
        options: GenerationOptions | None = None,
    ) -> LLMResponse:
        """完整的一轮或多轮 tool 循环。
        
        自动处理:
        1. 将 Tool list → ToolDefinition list 发给 LLM
        2. 检测 tool_call → settle 执行 → 结果回传
        3. 循环直到 LLM 不再调用 tool
        4. 返回最终文本 + 所有 tool 执行记录
        """
        ...

    async def stream(
        self,
        model: ModelID,
        messages: list[Message],
        tools: list[Tool[Any, Any]] | None = None,
        system: str | None = None,
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[LLMEvent]:
        """流式版本 — 逐事件产出 LLM 流事件。
        
        事件顺序 (见 §3.3):
        Pending → ReasoningStarted→Delta→Ended → TextStarted→Delta→Ended
        → ToolCallStarted→Delta→Ended → ToolResult|ToolFailure
        → Finish|Error
        """
        ...
```

### 5.3 Route 系统 (计划)

```python
# 四轴 Route 抽象:
class Protocol:     # 协议适配 (OpenAI Chat, Anthropic Messages, Gemini)
class Endpoint:     # URL 构造 (api.openai.com, /v1/chat/completions)
class Auth:         # 认证管理 (API Key, Bearer, OAuth)
class Framing:      # 响应格式 (SSE, JSON)

class Route:
    protocol: Protocol
    endpoint: Endpoint
    auth: Auth
    framing: Framing

class RouteClient:
    async def generate(self, request: LLMRequest) -> LLMResponse: ...
    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]: ...
```

### 5.4 Provider Adapter Scope (迭代 1)

首次实现范围（不替换现有 `providers/`，而是包装复用）：

1. `LLMService` 用适配器调用现有 `LLMProvider.complete()`
2. 将旧 `LLMResult.tool_calls` (list[dict]) 转为 `ToolCallPart`
3. 将旧 `LLMResult.content` (str) 转为 `TextPart`
4. 事件流从旧 `stream()` (AsyncIterator[str]) 适配为 `LLMEvent` 序列

### 5.5 文件清单 (计划)

```
llm/
├── __init__.py         # Public exports
├── service.py          # LLMService (generate + stream + tool loop)
├── route.py            # Route ABC, RouteClient
├── adapters/
│   ├── __init__.py
│   ├── legacy.py       # 适配旧 LLMProvider → LLMService
│   └── registry.py     # Provider 注册 + 选择
└── errors.py           # LLM 层特定的错误转换
```

---

## 6. Core Layer

**位置:** `src/cscode/core/`
**状态:** ✅ 基础完成 (待补充契约测试)
**依赖:** `schema/*`, `llm/*`, `tools2/*`

### 6.1 模块清单

Core 层已经构建完成，包含以下模块：

| Module | File | Status | Tests | Purpose |
|--------|------|--------|-------|---------|
| `SessionV2` | `session.py` | ✅ 完成 | `test_core_session.py` (13 tests) | Event Sourcing 会话 |
| `SessionProjector` | `session.py` | ✅ 完成 | `test_core_session.py` (6 tests) | Events → SessionState 重建 |
| `SessionCoordinator` | `coordinator.py` | ✅ 完成 | `test_core_session.py` (4 tests) | 每会话状态机 |
| `SessionRunner` | `runner.py` | ✅ 完成 | 待补充 | 标准化 Agent 循环 (使用 LLM 层) |
| `EventBus` | `events.py` | ✅ 完成 | `test_events.py` (6 tests) | 发布/订阅事件系统 |
| `PermissionService` | `permissions.py` | ✅ 完成 | `test_permissions.py` | 工具权限检查 |
| `Config` | `config.py` | ✅ 完成 | `test_config.py` | 分层配置 (YAML + ENV + CLI) |
| `ConfigStore` | `config.py` | ✅ 完成 | `test_config.py` | SQLite 配置持久化 |
| `ContextCompressor` | `compression.py` | ✅ 完成 | `test_compression.py` | 上下文压缩 (truncate) |
| `Agent` (legacy) | `engine.py` | 🟡 旧代码 | 无新测试 | 旧 Agent 循环 (一行不改) |

### 6.2 SessionRunner 接口

`SessionRunner` 是 Core 层的主入口，封装了完整的 Agent 循环：

```python
class SessionRunner:
    """标准化 Agent 循环，使用 LLMClient + ToolRuntime + SessionV2。"""

    async def run(
        self,
        session: SessionV2,
        user_input: str,
        on_event: Callable[[LLMEvent], Any] | None = None,
        generation_options: GenerationOptions | None = None,
    ) -> str:
        """处理用户输入。自动循环: LLM 调用 → 工具分发 → 结果回传。"""

    async def run_stream(
        self,
        session: SessionV2,
        user_input: str,
        generation_options: GenerationOptions | None = None,
    ) -> AsyncIterator[LLMEvent]:
        """流式版本，直接产出 LLMEvent。"""
```

循环流程:
1. `session.prompt(user_input)` — 追加用户消息事件
2. `session.state.messages` → `LLMRequest` — 构建 LLM 上下文
3. `LLMClient.stream(request)` → LLMEvents — 调用 LLM
4. 检测 `ToolCallEnded` → `ToolRuntime.dispatch()` — 执行工具
5. 工具结果追加到 `messages` — 循环回到步骤 2
6. 直到 `Finish` 事件或 `max_tool_rounds` 上限
7. 返回最终文本

### 6.3 旧代码处理原则

```
                     新旧系统共存
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
     旧代码 (tools/, engine.py)    新代码 (tools2/, llm/, core/)
     一行不改                       适配器调用旧功能
            │                           │
            └─────────────┬─────────────┘
                          ▼
                  Feature flag 切换
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
     全验证通过 → 删除旧代码       不通过 → 修复后重试
```

### 6.4 下一步

| 任务 | 优先级 | 说明 |
|------|--------|------|
| SessionRunner 契约测试 | 🔴 高 | 核心循环必须有测试覆盖 |
| SessionRunner 集成测试 | 🔴 高 | mock LLM + mock ToolRuntime |
| PermissionV2 glob 匹配 | 🟡 中 | 通配符路径匹配 |
| ConfigV2 Agent 级配置 | 🟢 低 | 按 agent 覆盖全局配置 |
| engine.py → SessionRunner 桥接 | 🟢 低 | 旧入口调用新循环 |

---

## 7. App Layer

**位置:** `src/cscode/app/` (新建), `src/cscode/cli.py`, `src/cscode/server/app.py`
**状态:** 🔜 **当前构建迭代**
**依赖:** `core/*`, `llm/*`, `schema/*`, `tools2/*`

### 7.1 目标

将入口从旧 `Agent` (engine.py) 迁移到新 `SessionRunner` + `SessionV2` + `ToolRuntime`，
实现 **零旧代码依赖** 的顶层接口。

### 7.2 迁移策略

```
阶段                  入口                   后端
────────────────────────────────────────────────────────
迁移前                cli.py/server.py      → Agent (engine.py)
第1步 (当前迭代)       cli.py (feature flag) → AgentV2 (app/.py)
第2步 (未来)           cli.py 默认新后端      → AgentV2
第3步 (未来)           server.py 部分切换     → AgentV2  
第4步 (最终)           全部切到新后端          → 删除旧 Agent (engine.py)
```

### 7.3 AgentV2 接口 (新建)

```python
class AgentV2:
    """App-level Agent 封装 SessionRunner + SessionV2 + ToolRuntime。
    
    提供与旧 Agent.run() 兼容的接口，但内部使用全新架构。
    """

    async def run(
        self,
        user_input: str,
        session: SessionV2 | None = None,
        on_event: Callable[[LLMEvent], Any] | None = None,
    ) -> str:
        """处理用户输入，返回最终回复。"""
```

### 7.4 文件清单 (计划)

```
app/
├── __init__.py          # Public exports (AgentV2)
├── agent.py             # AgentV2 — SessionRunner + SessionV2 封装
└── factory.py           # 创建 AgentV2 实例 (读取配置、注册 tools2)
```

### 7.5 迁移步骤

| 步骤 | 文件 | 说明 |
|------|------|------|
| 1 | `app/__init__.py` | 导出 AgentV2 |
| 2 | `app/agent.py` | AgentV2 实现 |
| 3 | `app/factory.py` | 工厂函数 (配置 → Route → LLMClient → ToolRuntime → AgentV2) |
| 4 | `tests/test_app_agent.py` | AgentV2 契约测试 |
| 5 | `cli.py` | 新增 `--new/--v2` flag 切换到 AgentV2 |
| 6 | 验证 | mypy + ruff + pytest 全通过 |

---

## 8. Development Conventions

### 8.1 Required Checks (每次提交前)

```bash
# 契约 + 集成测试
pytest tests/ -x --tb=short

# 类型检查 (strict mode)
mypy src/cscode/tools2/ src/cscode/schema/

# 代码风格
ruff check src/
ruff format src/ --check
```

### 8.2 TDD Workflow

```
1. 写契约测试 (test_tools2_contract.py 风格)
   └── 验证接口契约: 输入/输出类型、错误条件、边界值
2. 写实现 (只写能让测试通过的代码)
3. 运行所有测试 → 绿色
4. 重构 (在测试保护下优化)
5. 提交
```

### 8.3 Coding Standards

| Rule | Detail |
|------|--------|
| **类型标注** | 所有函数必须有完整类型标注 |
| **禁止 Any** | 禁止 `Any`、`as any`、`@ts-ignore` 等价物（`# type: ignore` 需注释原因） |
| **错误处理** | 禁止 `except Exception: pass` — 至少 `logger.exception()` |
| **Frozen dataclass** | 所有跨模块数据用 `@dataclass(frozen=True, slots=True)` |
| **Pydantic 校验** | 所有外部输入先通过 Pydantic model 校验 |
| **match/case** | Union 类型消费用 `match/case` + `assert_never()` |
| **250 行上限** | 单个源文件不超过 250 行实质性代码 |

---

## 9. Architecture Decision Records

### ADR-001: 采用三层架构 (Schema → LLM → Core → App)

**Status:** Accepted
**Date:** 2026-06-26

**Context:** OpenCode 使用 Effect.ts 做依赖注入，packages 之间有清晰的单向依赖链。
CScode 初始版本没有架构分层，类型定义散落，`engine.py` 单文件 474 行承载了所有逻辑。

**Decision:** 采用严格的四模块单向依赖：`schema(零依赖) → llm → core → app`。
每层只依赖正下层，禁止跨层 import。使用 Python 的 `import` 机制做编译时检查。

**Alternatives Considered:**
- 直接重构旧代码 → 风险高，无法渐进切换
- 用依赖注入框架 → Python DI 框架没有 Effect 的类型安全级
- 复制 OpenCode 包结构 → TypeScript 和 Python 模块化特性不同

**Consequences:**
- 模块可以独立测试，不依赖 app 层的 UI 代码
- 禁止跨层 import 约束需要在 code review 中落实
- 新代码可以通过适配器调用旧代码，实现渐进迁移

### ADR-002: Tool 系统 v2 使用 Pydantic v2 实现类型安全

**Status:** Accepted
**Date:** 2026-06-26

**Context:** 旧 `tools/` 的 `BaseTool` 使用 `parameters: dict` 和 `execute(args: dict)`，
输入输出的类型安全完全靠运行时检查。OpenCode 使用 Effect Schema 做编译时 + 运行时双验证。

**Decision:** `Tools2` 使用 `Generic[InputT, OutputT : BaseModel]`，输入输出由 Pydantic model 定义。
`Tool[I,O]` 的 `execute(input: I) → ToolResult[O]` 保证了编译时类型安全，
`input_schema.model_validate()` 保证了运行时正确性。

**Alternatives Considered:**
- `dataclass` + 手动校验 → 没 Pydantic 的 JSON Schema 生成能力
- `msgspec` → 性能更好但生态不如 Pydantic
- 保持旧 `dict` 格式 → 无法获得类型检查收益

**Consequences:**
- 每个工具需要定义 Input/Output 两个 Pydantic model
- Pydantic 的 `model_json_schema()` 自动生成 `ToolDefinition.input_schema`
- 旧 `tools/` 代码不动，`tools2/` 是新实现

### ADR-003: 不是 1:1 翻译 OpenCode

**Status:** Accepted (Supersedes `docs/opencode-python-porting-plan.md`)
**Date:** 2026-06-26

**Context:** 最初的计划是"1:1 还原 OpenCode 的 TypeScript 功能到 Python"。
五维分析发现 OpenCode 大量依赖 Effect.ts 的纯函数式特性（Fiber、Schema、Context），
这些在 Python 中没有直接等价物。

**Decision:** CScode 是**全新构建 + 接口驱动**的系统。吸收 OpenCode 的架构思想和接口模式，
但用 Python 语言特性（Pydantic v2、async/await、match/case）独立实现。
旧 `docs/opencode-python-porting-plan.md` 作废。

**Consequences:**
- 接口签名参考 OpenCode 但参数名用 Python 风格
- 实现逻辑完全独立编写，不引用 OpenCode 源码
- 注释全部用中文/英文重新撰写
- 测试用例使用独立数据

### ADR-004: 旧代码不动，适配器过渡

**Status:** Accepted
**Date:** 2026-06-26

**Context:** 系统重构中最大的风险是改旧代码引入 regression。

**Decision:** 旧代码（`tools/`、`providers/`、`engine.py`、`session_manager.py`）一行不改。
新代码通过适配器模式调用旧实现。例如 `LLMService` 通过适配器调用旧 `LLMProvider`。
等新路径全部验证通过后，通过 feature flag 切换，然后删除旧代码。

**Consequences:**
- 任何阶段都可以回退到旧系统（仅需关闭 feature flag）
- 重构不阻塞业务功能开发
- 代码库短期内双轨并行，文件数量增加

### ADR-005: Event Sourcing 延期，优先 LLM 层

**Status:** Accepted
**Date:** 2026-06-26

**Context:** 五维分析识别出的 P0 优先级:
1. Tool.definition + Tool.make 分离 → ✅ tools2 已完成
2. **LLM.generate 自动 tool 循环 → 🔜 当前迭代**
3. 精确权限规则匹配 → ⏳
4. Session 恢复机制 → ⏳

Event Sourcing 虽然重要，但不是 LLM 层的前置依赖。当前的开发顺序是：
先迭代 LLM 层（tools2 集成 + tool 循环），再迭代 Core 层（权限 + session）。

**Consequences:**
- Event Sourcing 表结构已存在但未集成到 session 生命周期
- 当前 session 使用内存 dict + SQLite 直接读写
- Event Sourcing 集成是 Core 层迭代的重点

---

## 10. Appendices

### 10.1 Superseded Documents

| Document | Status | Reason |
|----------|--------|--------|
| `docs/opencode-python-porting-plan.md` | ❌ Deprecated | 原计划"1:1 翻译"已被否决，见 ADR-003 |
| `docs/opencode-analysis/five-dimension-analysis.md` | ✅ Analysis Output | 分析阶段产出，引用为设计参考 |
| `docs/opencode-analysis/source-analysis.md` | ✅ Analysis Output | 源码阶段产出，引用为差距参考 |
| `docs/reimplementation-methodology.md` | ✅ Methodology | Loop Engineering 执行框架 |

### 10.2 Key Reference Files

| File | What It Contains |
|------|-----------------|
| `src/cscode/schema/` | 当前 Schema 层完整实现 |
| `src/cscode/tools2/` | 当前 Tool 系统 v2 完整实现 |
| `tests/test_tools2_contract.py` | Tool 系统契约测试 (15 tests) |
| `tests/test_tools2_impl.py` | Tool 系统实现测试 (13 tests) |
| `tests/test_tools2_all.py` | 其余 11 个工具测试 (24 tests) |

### 10.3 P0/P1/P2 优先级

| Priority | Items | Status |
|----------|-------|--------|
| P0 (必须对齐) | ~Tool.definition + Tool.make 分离~ | ✅ 完成 |
| P0 (必须对齐) | **LLM.generate 自动 tool 循环** | 🔜 当前迭代 |
| P0 (必须对齐) | 精确权限规则匹配 | ⏳ |
| P0 (必须对齐) | Session 恢复机制 | ⏳ |
| P1 (重要改进) | LLMError 分类 | ✅ 完成 (schema/errors.py) |
| P1 (重要改进) | 上下文压缩 + 溢出恢复 | ⏳ |
| P2 (优化) | 超时精细控制 (timeout + turnTimeout) | ⏳ |
| P2 (优化) | 消息 Parts 分层存储 | ⏳ |
