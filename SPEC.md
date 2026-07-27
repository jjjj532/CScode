# CScode vs OpenCode 差距分析 & 追齐规格

> 生成日期: 2026-07-27
> OpenCode 版本参考: dev-7 (v1.18.6)
> CScode 版本: v0.3.3

---

## 目录

1. [概述与架构对比](#1-概述与架构对比)
2. [差距矩阵](#2-差距矩阵)
3. [模块级规格](#3-模块级规格)
   - 3.1 [System Context 代数系统](#31-system-context-代数系统)
   - 3.2 [Session V2 架构](#32-session-v2-架构)
   - 3.3 [Schema/Protocol 层](#33-schemaprotocol-层)
   - 3.4 [LLM Provider 增强](#34-llm-provider-增强)
   - 3.5 [Tool Registry V2 完善](#35-tool-registry-v2-完善)
   - 3.6 [Plugin SDK V2](#36-plugin-sdk-v2)
   - 3.7 [Agent 系统增强](#37-agent-系统增强)
   - 3.8 [权限系统增强](#38-权限系统增强)
4. [追齐路线图](#4-追齐路线图)
5. [版本里程碑](#5-版本里程碑)

---

## 1. 概述与架构对比

### 1.1 OpenCode 架构 (dev-7)

```
@opencode-ai/schema       -> 领域模型定义 (Effect Schema, 61 文件)
       |
@opencode-ai/protocol    -> HttpApi 端点、错误、中间件放置
       |
@opencode-ai/core        -> 核心引擎 (SystemContext, SessionV2, Provider, Tool, Permission)
  |-- system-context/    -> ContextSource algebra
  |-- session/           -> SessionV2, Drain, Runner, Store, ContextEpoch, Input
  |-- tool/              -> Tool 注册表 + OutputStore
  |-- permission/        -> Location-scoped 权限
  |-- effect/            -> Effect 运行时
       |
@opencode-ai/server      -> Hono HTTP 服务器 + 路由
       |
@opencode-ai/llm         -> Schema-first LLM 抽象 (Protocols/Routes/Providers/Cache)
       |
@opencode-ai/client      -> 代码生成 HTTP 客户端 (Promise + Effect 双发射器)
packages/opencode/       -> 主应用 (TUI + CLI + Server 集成)
packages/tui/            -> OpenTUI 终端 UI
packages/app/            -> SolidJS Web 应用
packages/desktop/        -> Electron 桌面
packages/plugin/         -> Plugin SDK v2
packages/enterprise/     -> 企业功能
packages/codemode/       -> Code Mode
packages/stats/          -> 分析统计
packages/slack/          -> Slack 集成
sdks/vscode/             -> VS Code 扩展
```

### 1.2 CScode 当前架构

```
src/cscode/
  schema/          -> 基础 Pydantic 模型定义 (8 文件)
  core/            -> 核心引擎 (Session, Runner, Config, Permission, Plugin)
  server/          -> FastAPI 服务器
  llm/             -> LLM 客户端 (Client, Route, Service, Protocols)
  providers/       -> 16 个 Provider 实现
  tools/ & tools2/ -> 工具实现 (V1 + V2)
  tui/             -> Textual TUI
  web/             -> React Web UI
  desktop/ (Tauri) -> 桌面端
  mcp/             -> MCP 客户端/服务端
  plugins/         -> 插件系统
  auth/            -> 认证
  enterprise/      -> 企业功能
  sharing/         -> Session 分享
```

### 1.3 根本差距

| 维度 | OpenCode | CScode | 根本原因 |
|------|----------|--------|---------|
| 语言 | TypeScript + Bun | Python + asyncio | 复刻选择 |
| 类型系统 | Effect Schema (编译+运行时) | Pydantic + mypy | 语言差异 |
| 异步模型 | Effect TS (代数效应系统) | asyncio | 语言差异 |
| 包管理 | Turborepo 33+ 包 | 单 Python 包 | 可优化 |
| API 定义 | Schema -> 代码生成 | 手动 FastAPI | **需建立** |
| 版本 | 1.18.6 | 0.3.3 | 差距较大 |

---

## 2. 差距矩阵

### 2.1 P0 - 核心架构 (必须追齐)

| # | 模块 | 状态 | 工作量 | 依赖 |
|---|------|------|--------|------|
| P0.1 | System Context 代数系统 | 缺失 | 2周 | 无 |
| P0.2 | Session V2 重构 | 不完整 | 3周 | P0.1 |
| P0.3 | Schema 领域模型 | 基础 | 1周 | 无 |
| P0.4 | Protocol 协议层 | 缺失 | 1周 | P0.3 |
| P0.5 | LLM Provider 缓存 | 缺失 | 1周 | 无 |

### 2.2 P1 - 主要功能

| # | 模块 | 状态 | 工作量 | 依赖 |
|---|------|------|--------|------|
| P1.1 | 双 Agent 系统 | 接近 | 3天 | 无 |
| P1.2 | Tool Registry V2 完善 | 需完善 | 3天 | 无 |
| P1.3 | 权限系统增强 | 接近 | 2天 | 无 |
| P1.4 | Plugin SDK V2 | 需完善 | 3天 | 无 |
| P1.5 | Provider 补齐 | 缺7+ | 2天 | 无 |
| P1.6 | Workspace/Control Plane | 接近 | 2天 | 无 |

### 2.3 P2 - 次要功能

| # | 模块 | 状态 | 工作量 | 依赖 |
|---|------|------|--------|------|
| P2.1 | Code Mode | 缺失 | 3天 | 无 |
| P2.2 | Background Jobs | 接近 | 1天 | 无 |
| P2.3 | Stats/Analytics | 缺失 | 2天 | 无 |
| P2.4 | IDE 集成 | 基础 | 2天 | 无 |
| P2.5 | Session UI 组件 | 基础 | 2天 | 无 |

### 2.4 P3 - 基础设施

| # | 模块 | 状态 | 工作量 | 依赖 |
|---|------|------|--------|------|
| P3.1 | CI/CD 完善 | 缺失 | 3天 | 无 |
| P3.2 | Docker 容器 | 缺失 | 1天 | 无 |
| P3.3 | OpenTelemetry | 缺失 | 2天 | 无 |
| P3.4 | 文档站点 | 缺失 | 3天 | 无 |
| P3.5 | http-recorder | 缺失 | 2天 | 无 |
| P3.6 | VS Code 扩展 | 缺失 | 1周 | 无 |
| P3.7 | JS SDK | 缺失 | 1周 | 无 |

---

## 3. 模块级规格

### 3.1 System Context 代数系统

#### 3.1.1 目标

在 Python 中实现等效于 OpenCode `packages/core/src/system-context/index.ts` 的 ContextSource 代数系统 —— 一组将系统上下文建模为独立可刷新型类型源的接口和运行时。

#### 3.1.2 核心概念

| 概念 | OpenCode (TS) | CScode (Python) | 说明 |
|------|--------------|-----------------|------|
| Source | `Source<A>` 接口 + codec/load/baseline/update/removed | `ContextSource[T]` dataclass | 一个类型化上下文源的代数描述 |
| Key | `Branded<string>` "a/b" 格式 | `ContextKey` 值对象 | 命名空间稳定标识 |
| Unavailable | `Symbol.for("...")` | `UNAVAILABLE` 哨兵 | 临时不可观测 |
| SystemContext | 不透明 carrier (PackedSource[]) | `SystemContext` dataclass | 组合后可观测的上下文 |
| Generation | `{baseline, snapshot}` | `ContextGeneration` dataclass | 一次初始化的完整结果 |
| Snapshot | `Record<Key, SourceSnapshot>` | `dict[str, SourceSnapshot]` | 持久化比较状态 |
| ReconcileResult | `Unchanged | Updated | ReplacementReady | ReplacementBlocked` | `ReconcileResult` union | 刷新结果类型 |

#### 3.1.3 关键接口

```python
# src/cscode/core/system_context/__init__.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

A = TypeVar("A")

class UNAVAILABLE:
    """Sentinel indicating a source could not be observed."""
    pass


@dataclass(frozen=True)
class ContextKey:
    """Stable namespaced identity for one context source.
    Format: "namespace/name" (e.g. "core/environment", "core/date")
    """
    value: str


class ContextSource(Generic[A]):
    """Defines one typed source before its value type is hidden by make()."""
    key: ContextKey
    load: Callable[[], Awaitable[A | type[UNAVAILABLE]]]
    baseline: Callable[[A], str]
    update: Callable[[A, A], str]
    removed: Callable[[A], str] | None = None


@dataclass(frozen=True)
class SourceSnapshot:
    """Durable comparison state for one admitted source."""
    value: Any  # JSON-encodable
    removed: str | None = None


class SystemContext:
    """Opaque carrier for composable system context sources."""
    _sources: list[PackedSource]


@dataclass(frozen=True)
class ContextGeneration:
    """Immutable snapshot of one context initialization."""
    baseline: str
    snapshot: dict[str, SourceSnapshot]


# Reconcile result types
@dataclass(frozen=True)
class Unchanged:
    pass

@dataclass(frozen=True)
class Updated:
    text: str
    snapshot: dict[str, SourceSnapshot]

@dataclass(frozen=True)
class ReplacementReady:
    generation: ContextGeneration

@dataclass(frozen=True)
class ReplacementBlocked:
    pass

ReconcileResult = Unchanged | Updated | ReplacementReady | ReplacementBlocked
```

#### 3.1.4 核心函数

```python
def make(source: ContextSource[A]) -> SystemContext:
    """Closes a typed source into a context that composes uniformly."""

def combine(contexts: list[SystemContext]) -> SystemContext:
    """Combine contexts in order. Rejects duplicate keys."""

async def initialize(ctx: SystemContext) -> ContextGeneration:
    """Create immutable baseline + durable snapshot.
    Raises InitializationBlocked if any source is unavailable."""

async def reconcile(
    ctx: SystemContext, previous: dict[str, SourceSnapshot]
) -> ReconcileResult:
    """Compare current values with snapshot.
    Returns Unchanged | Updated | ReplacementReady | ReplacementBlocked."""

async def replace(
    ctx: SystemContext, previous: dict[str, SourceSnapshot]
) -> ReplacementReady | ReplacementBlocked:
    """Create a complete replacement or block if admitted sources unavailable."""
```

#### 3.1.5 内置 Context Sources

```python
# src/cscode/core/system_context/builtins.py

class SystemContextBuiltIns:
    """Register built-in context sources."""

    @staticmethod
    def create() -> SystemContext:
        return SystemContext.combine([
            SystemContext.make(ContextSource(
                key=ContextKey("core/environment"),
                load=_load_environment,
                baseline=_render_environment_baseline,
                update=_render_environment_update,
            )),
            SystemContext.make(ContextSource(
                key=ContextKey("core/date"),
                load=_load_date,
                baseline=lambda d: f"Today's date: {d}",
                update=lambda _prev, cur: f"Today's date is now: {cur}",
            )),
            SystemContext.make(ContextSource(
                key=ContextKey("core/instructions"),
                load=_load_instructions,
                baseline=_render_instructions_baseline,
                update=_render_instructions_update,
                removed=_render_instructions_removed,
            )),
            SystemContext.make(ContextSource(
                key=ContextKey("core/agent-skills"),
                load=_load_agent_skills,
                baseline=_render_skills_baseline,
                update=_render_skills_update,
            )),
        ])
```

#### 3.1.6 SystemContextRegistry

```python
# src/cscode/core/system_context/registry.py

class SystemContextRegistry:
    """Location-scoped registry of context source producers."""

    async def register(self, entry: SystemContext) -> None:
        """Register a context source. Duplicate keys fail."""

    async def load(self) -> SystemContext:
        """Load all registered sources and combine in stable key order."""
```

#### 3.1.7 ContextEpoch 存储

```python
# 使用现有 context_epochs 表 (不变)
# 表结构:
#   session_id TEXT
#   epoch INTEGER
#   baseline_seq INTEGER
#   snapshot TEXT    -- JSON encoded Snapshot
#   baseline TEXT    -- rendered baseline text (durable)
```

#### 3.1.8 测试规格

```
tests/test_system_context/
  test_make_and_combine.py        -- source 创建、组合、重复 key 拒绝
  test_initialize.py              -- 初始化成功/部分不可观测阻塞
  test_reconcile.py               -- 无变化/更新/不兼容触发替换
  test_replace.py                 -- 替换成功/阻塞
  test_registry.py                -- 注册/加载/重复 key
  test_builtins.py                -- 内置 source 渲染
  test_context_epoch.py           -- epoch 持久化/读取
```

---

### 3.2 Session V2 架构

#### 3.2.1 目标

将 CScode 的 session 系统从"消息列表 + prompt/response 追加"升级为 OpenCode SessionV2 风格的架构：durable prompt admission 与执行分离、prompt steering/queue、Session Drain 概念、Safe Provider-Turn Boundary。

#### 3.2.2 核心概念

| 概念 | OpenCode | CScode Python |
|------|----------|---------------|
| Admitted Prompt | 已录入但未入历史 | `AdmittedInput` |
| Prompt Promotion | 从 pending 移至 session history | `promote()` |
| Steering | 当前 drain 内立即 promote | `delivery="steer"` |
| Queue | 当前 drain 空闲后才 promote | `delivery="queue"` |
| Session Drain | 一次 process-local 执行范围 | `SessionDrain` |
| Provider Turn | 一次 LLM 请求+响应 | `ProviderTurn` |
| Run Coordinator | 同 Session 串行化 | `RunCoordinator` |
| Safe Boundary | provider 调用前一刻 | 事件溯源中自然位置 |

#### 3.2.3 数据模型

```python
# src/cscode/core/session_v2/input.py

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DeliveryMode(str, Enum):
    STEER = "steer"   # promote within current drain
    QUEUE = "queue"   # promote when idle


@dataclass
class AdmittedInput:
    """A durable prompt that has been admitted but not yet promoted."""
    id: str
    session_id: str
    prompt: str
    delivery: DeliveryMode
    admitted_seq: int
    time_created: datetime
    promoted_seq: int | None = None


@dataclass
class Prompt:
    """A user prompt with optional attachments."""
    text: str
    attachments: list[dict] = field(default_factory=list)
```

#### 3.2.4 SessionInput API

```python
# src/cscode/core/session_v2/input.py

class SessionInput:
    """Prompt admission and promotion operations."""

    @staticmethod
    async def admit(
        db: Database, events: EventStore, input: AdmittedInput
    ) -> AdmittedInput:
        """Durably admit a prompt. Idempotent on same ID."""

    @staticmethod
    async def promote_steers(
        db: Database, events: EventStore, session_id: str, cutoff_seq: int
    ) -> int:
        """Promote all steer deliveries up to cutoff_seq."""

    @staticmethod
    async def promote_next_queued(
        db: Database, events: EventStore, session_id: str
    ) -> bool:
        """Promote one queued input when idle."""

    @staticmethod
    async def has_pending(db: Database, session_id: str, delivery: DeliveryMode) -> bool:
        """Check for pending inputs."""

    @staticmethod
    async def find(db: Database, id: str) -> AdmittedInput | None:
        """Find an admitted input by ID."""
```

#### 3.2.5 SessionRunner (V2)

```python
# src/cscode/core/session_v2/runner.py

class SessionRunner:
    """Location-scoped runner that executes one provider turn."""

    async def run(self, session_id: str, force: bool = False) -> None:
        """
        Main drain loop:
        1. Load session + context epoch
        2. Promote eligible steers (up to current seq)
        3. Build context (baseline + mid-conversation updates + history)
        4. Execute provider turn
        5. If tools -> continue, else -> promote next queued
        6. Repeat until no eligible work or max turns reached
        """
```

#### 3.2.6 SessionRunCoordinator

```python
# src/cscode/core/session_v2/coordinator.py

class SessionRunCoordinator:
    """Per-session serialization: same session runs cannot overlap.
    Different sessions run concurrently.
    """

    async def run(self, session_id: str) -> None:
        """Start or join execution for a session ID."""

    async def wake(self, session_id: str) -> None:
        """Schedule a follow-up after newly admitted work."""

    async def interrupt(self, session_id: str) -> None:
        """Stop active execution. No-op if idle."""

    def active(self) -> set[str]:
        """Returns currently executing session IDs."""
```

#### 3.2.7 SessionExecution

```python
# src/cscode/core/session_v2/execution.py

class SessionExecution:
    """Routes execution from Session ID to the runner owned by that Location."""

    async def resume(self, session_id: str) -> None:
        """Start/resume execution."""

    async def wake(self, session_id: str) -> None:
        """Register newly recorded work (coalesced)."""

    async def interrupt(self, session_id: str) -> None:
        """Interrupt active execution."""

    def active(self) -> set[str]:
        """Currently executing sessions."""
```

#### 3.2.8 ContextEpoch 集成

```python
# src/cscode/core/session_v2/context_epoch.py

class SessionContextEpoch:
    """Manages the lifecycle of a Context Epoch for a session."""

    @staticmethod
    async def initialize(
        db: Database, context: SystemContext, session_id: str
    ) -> tuple[str, int] | None:
        """Initialize first epoch. Returns (baseline_text, baseline_seq)."""

    @staticmethod
    async def prepare(
        db: Database, events: EventStore, context: SystemContext,
        session_id: str
    ) -> tuple[str, int]:
        """Prepare for a provider turn.
        Returns (baseline_or_updated_text, baseline_seq).
        """

    @staticmethod
    async def compact(
        db: Database, events: EventStore, context: SystemContext,
        session_id: str
    ) -> None:
        """Compact: new epoch, fresh baseline, old mid-conversation msgs removed."""
```

#### 3.2.9 流程示例

```
用户输入 "Add validation"

1. SessionInput.admit(steer)
   -> 写入 session_input 表 (admitted_seq=N, promoted_seq=NULL)

2. SessionRunner.run() 开始 drain
   -> RunCoordinator 确保串行

3. SessionInput.promote_steers(cutoff_seq=N)
   -> 更新 promoted_seq=N
   -> 发布 Prompted 事件

4. SessionContextEpoch.prepare()
   -> reconcile current sources vs snapshot
   -> 无变化: 返回现有 baseline
   -> 有变化: 发布 MidConversationSystemMessage

5. 构建 context 消息列表:
   baseline_system + mid_conversation_updates + projected_history

6. Provider Turn:
   -> LLM.stream(request)
   -> 逐事件处理 (text.delta, text.ended, tool.called, ...)

7. 如果有 tool calls:
   -> 执行工具, 追加 tool result 到历史
   -> 回到 step 6 (next provider turn)

8. 无 tool calls:
   -> SessionInput.promote_next_queued()
   -> 如果有 queued: 回到 step 3
   -> 无 queued: drain 完成
```

#### 3.2.10 测试规格

```
tests/test_session_v2/
  test_input_admit.py         -- admit/promote 幂等性
  test_input_steer.py         -- steer promotion
  test_input_queue.py         -- queue promotion (仅空闲时)
  test_coordinator.py         -- 同 session 串行/不同 session 并行
  test_runner_drain.py        -- 完整 drain 流程
  test_context_epoch.py       -- epoch 初始化/刷新/compaction
  test_execution.py           -- resume/wake/interrupt
  test_interrupt.py           -- 中断正在运行的 session
```

---

### 3.3 Schema/Protocol 层

#### 3.3.1 目标

建立独立的 schema 定义层和 protocol 层，将领域模型与 API 端点实现解耦。

#### 3.3.2 当前状态问题

- `src/cscode/schema/` 只有 8 个文件，大量领域类型散落在各模块
- FastAPI 路由直接操作数据库 (server/app.py)
- 没有独立的 protocol 定义层

#### 3.3.3 目标架构

```
src/cscode/schema/         -- 领域模型定义
    ids.py                 -- SessionID, MessageID, ToolCallID, ModelID etc.
    session.py             -- SessionInfo, SessionState, SessionContext
    session_input.py       -- AdmittedInput, DeliveryMode, Prompt
    message.py             -- Message, Part, ToolCall, ToolResult
    tool.py                -- ToolDefinition, ToolResult, ToolError
    permission.py          -- Rule, Ruleset, RuleEffect
    credential.py          -- Credential, ProviderAuth

src/cscode/protocol/       -- API 协议定义
    __init__.py
    groups/
        sessions.py        -- Session 端点组定义
        tools.py           -- Tool 端点组定义
        config.py          -- Config 端点组定义
        permissions.py     -- Permission 端点组定义
    errors.py              -- 统一错误类型

src/cscode/server/         -- FastAPI 实现
    routes/
        sessions.py        -- Session 路由 (与 protocol 对齐)
        tools.py
        config.py
        permissions.py
    middleware/             -- 中间件
```

#### 3.3.4 Schema 规范节选

```python
# src/cscode/schema/ids.py
from typing import Annotated
from pydantic import StringConstraints

SessionID = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]{26}$")]
MessageID = Annotated[str, StringConstraints(pattern=r"^msg_[a-z0-9]{24}$")]
ToolCallID = Annotated[str, StringConstraints(pattern=r"^call_[a-z0-9]{24}$")]
ModelID = Annotated[str, StringConstraints(min_length=1)]
ProviderID = Annotated[str, StringConstraints(min_length=1)]
LocationID = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]+$")]
WorkspaceID = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]+$")]
```

```python
# src/cscode/schema/session_input.py
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class DeliveryMode(str, Enum):
    STEER = "steer"
    QUEUE = "queue"

class AdmittedInput(BaseModel):
    id: str
    session_id: str
    prompt: str
    delivery: DeliveryMode
    admitted_seq: int
    time_created: datetime
    promoted_seq: int | None = None
```

#### 3.3.5 Protocol 规范节选

```python
# src/cscode/protocol/groups/sessions.py

from pydantic import BaseModel
from cscode.schema.ids import SessionID, MessageID

class CreateSessionRequest(BaseModel):
    title: str = ""
    model: str = ""
    provider: str = ""

class CreateSessionResponse(BaseModel):
    id: SessionID
    title: str
    created_at: float

class ListSessionsRequest(BaseModel):
    limit: int = 50
    offset: int = 0

class ListSessionsResponse(BaseModel):
    sessions: list[SessionInfo]
    total: int

class PromptRequest(BaseModel):
    message: str
    delivery: str = "steer"  # "steer" | "queue"

class PromptResponse(BaseModel):
    admitted_id: str
    session_id: SessionID
```

#### 3.3.6 测试规格

```
tests/test_schema/
  test_ids.py              -- ID 格式验证
  test_session.py          -- Session 模型序列化/反序列化
  test_session_input.py    -- AdmittedInput 生命周期

tests/test_protocol/
  test_endpoints.py        -- 端点定义完整性
  test_errors.py           -- 错误类型
```

---

### 3.4 LLM Provider 增强

#### 3.4.1 目标

补齐 missing providers 并实现 Provider Caching 系统（auto/manual cache policy）。

#### 3.4.2 Missing Providers

```python
# 当前已有 (16):
#   anthropic, azure, bedrock, cohere, gemini, grok,
#   mistral, nvidia, ollama, openai, openrouter,
#   perplexity, vertex, xai, status, base

# 需要补齐 (7+):
# - Alibaba (通义千问)    -> OpenAI compatible
# - Cerebras              -> OpenAI compatible
# - DeepInfra             -> OpenAI compatible
# - Gateway (AI Gateway)  -> 统一 gateway 包装
# - Groq                  -> OpenAI compatible
# - Together AI           -> OpenAI compatible
# - Venice.ai             -> OpenAI compatible
```

#### 3.4.3 Provider Caching

```python
# src/cscode/llm/cache_policy.py

from dataclasses import dataclass
from typing import Literal

CacheHintType = Literal["ephemeral"]

@dataclass
class CacheHint:
    type: CacheHintType = "ephemeral"
    ttl_seconds: int | None = None

CachePolicyObject = dict[
    Literal["tools", "system", "messages", "ttl_seconds"],
    bool | str | int,
]

CachePolicy = bool | str | CachePolicyObject
# True/"auto"  -> default auto placement (默认)
# False/"none" -> no auto placement
# dict         -> explicit policy

def apply_cache_policy(request: LLMRequest, protocol_id: str) -> LLMRequest:
    """Apply cache policy to request parts.
    Auto: last tool + last system + latest user message.
    Only applies to anthropic-messages, bedrock-converse.
    """

PROTOCOL_CACHE_SUPPORT = {
    "anthropic-messages": True,   # cache_control markers
    "bedrock-converse": True,     # cachePoint blocks
    "openai-chat": False,         # implicit server-side
    "openai-responses": False,    # implicit server-side
    "gemini": False,              # implicit + out-of-band
}
```

#### 3.4.4 Provider 架构调整

```python
# 当前:
#   providers/openai.py -> provider()
#   providers/anthropic.py -> provider()

# 目标参考 opencode LLM Route:
#   四轴模型:
#   - Protocol: 请求体构建 + 流解析
#   - Endpoint: URL 构建
#   - Auth: 认证方式 (bearer, header, sigv4)
#   - Framing: 帧格式 (SSE, AWS event-stream)

class Route:
    id: str
    provider: str
    protocol: Protocol
    endpoint: Endpoint
    auth: Auth
    framing: Framing
```

---

### 3.5 Tool Registry V2 完善

#### 3.5.1 目标

为 tools2 添加 OpenCode 风格的 Output Bounding 和 Managed Tool Output Files。

#### 3.5.2 Output Bounding

```python
# src/cscode/tools2/output_store.py

class ToolOutputStore:
    """Manages tool output files for oversized results."""

    MAX_LINES = 500
    MAX_BYTES = 512 * 1024  # 512KB
    RETENTION_SECONDS = 3600

    async def store(self, session_id: str, content: str) -> ManagedOutput:
        """Store oversized output. Returns bounded preview + path."""

    async def read(self, path: str) -> str | None:
        """Read stored output file."""

    async def cleanup(self, session_id: str) -> None:
        """Clean up expired output files."""


@dataclass
class BoundedOutput:
    """Result of bounding tool output."""
    preview: str
    truncated: bool
    managed_path: str | None = None


async def bound_tool_output(
    content: str,
    max_lines: int = 500,
    max_bytes: int = 512 * 1024,
) -> BoundedOutput:
    """Generic truncation: preserve beginning and end."""
```

---

### 3.6 Plugin SDK V2

#### 3.6.1 目标

参照 OpenCode `packages/plugin/` v2 API，完善插件系统。

#### 3.6.2 当前

- `src/cscode/plugins/` -- bridge, hooks, loader, manifest, sdk
- 有 basic plugin loading + hooks

#### 3.6.3 需要补充

```python
# src/cscode/plugins/v2/context_source.py
class PluginContextSource:
    """Plugin-defined system context source."""
    key: str
    load: Callable[[], Awaitable[str]]
    baseline: Callable[[str], str]
    update: Callable[[str, str], str]

# src/cscode/plugins/v2/tool.py
class PluginTool:
    """Plugin-defined tool."""
    name: str
    description: str
    parameters: dict
    execute: Callable[..., Awaitable[str]]

# src/cscode/plugins/v2/lifecycle.py
class PluginLifecycle:
    async def on_activate(self) -> None: ...
    async def on_deactivate(self) -> None: ...
    async def on_session_start(self, session_id: str) -> None: ...
    async def on_session_end(self, session_id: str) -> None: ...
```

---

### 3.7 Agent 系统增强

#### 3.7.1 当前状态

- `src/cscode/core/agent/` -- base, build, plan, factory, registry, subagent, tab
- build/plan 模式已基本实现，PlanAgent 有只读权限限制

#### 3.7.2 需要补充

```python
# 1. 子 agent 支持 (@general)
class SubAgent:
    name: str
    system_prompt: str
    allowed_tools: frozenset[str]
    max_tool_rounds: int

SUB_AGENTS = {
    "general": SubAgent(
        name="general",
        system_prompt="You are a general-purpose research assistant...",
        allowed_tools={"read", "grep", "glob", "ls", "web_search", "web_fetch"},
        max_tool_rounds=10,
    ),
}

# 2. Agent Tab 切换 (build <-> plan)
class AgentTab:
    """Agent mode switching with permission context reset."""
    MODES = ["build", "plan"]

    async def switch(self, mode: str) -> None:
        """Switch agent mode. Reset permission context."""

    def current(self) -> str:
        """Current active mode."""
```

---

### 3.8 权限系统增强

#### 3.8.1 当前状态

- `permission_v2.py` -- Rule, RuleEffect, Ruleset, PermissionEvaluator
- `external_directory.py` -- ExternalDirectoryStore

#### 3.8.2 需要补充

```python
# 1. Arity-based evaluation
class Arity(str, Enum):
    EXACT = "exact"     # 必须完全匹配
    PREFIX = "prefix"   # 匹配前缀
    ANY = "any"         # 任何资源

# 2. Location-scoped 权限
class LocationPermissions:
    """Location-scoped permission context."""
    location_id: str
    rulesets: list[Ruleset]

    async def evaluate(self, action: str, resource: str) -> bool:
        """Evaluate permission in this location's context."""

# 3. Permission request 流程
class PermissionRequest:
    tool_name: str
    args: dict
    session_id: str
    status: Literal["pending", "approved", "denied"]
    created_at: float

class PermissionRequestStore:
    async def create(self, request: PermissionRequest) -> str: ...
    async def approve(self, request_id: str) -> None: ...
    async def deny(self, request_id: str) -> None: ...
    async def list_pending(self, session_id: str) -> list[PermissionRequest]: ...
```

---

## 4. 追齐路线图

### Phase 1: Core Architecture (5-6 周)

```
Week 1-2: System Context Algebra
  [P0.1] src/cscode/core/system_context/ 新建
  [P0.1] 实现 make/combine/initialize/reconcile/replace
  [P0.1] SystemContextRegistry
  [P0.1] 内置 sources (environment, date, instructions, skills)
  [P0.1] 测试覆盖

Week 3-5: Session V2 重构
  [P0.2] src/cscode/core/session_v2/ 新建
  [P0.2] SessionInput (admit/promote/find)
  [P0.2] SessionRunner (drain loop)
  [P0.2] RunCoordinator (per-session serialization)
  [P0.2] SessionExecution (resume/wake/interrupt)
  [P0.2] ContextEpoch 集成
  [P0.2] 旧 SessionV2 逐步迁移
  [P0.2] 测试覆盖

Week 5-6: Schema/Protocol 层
  [P0.3] schema/ids.py, session.py, tool.py 等领域模型
  [P0.4] protocol/groups/ 端点定义
  [P0.4] server/routes/ 按 group 分离
  [P0.3+P0.4] 测试覆盖
```

### Phase 2: Features (3-4 周)

```
Week 7: LLM Provider 增强
  [P0.5] cache_policy.py + 协议适配
  [P1.5] 补齐 7 个 missing providers
  [P1.5] Route 四轴模型 (protocol/endpoint/auth/framing)

Week 8: Tool Registry + Plugin SDK
  [P1.2] ToolOutputStore + output bounding
  [P1.4] Plugin SDK v2 (context source, tool, lifecycle hooks)

Week 9: Agent + Permission 增强
  [P1.1] @general 子 agent 支持
  [P1.3] Location-scoped 权限 + arity evaluation
  [P1.6] Workspace/Control Plane 完善
```

### Phase 3: Infrastructure (2-3 周)

```
Week 10: CI/CD + Docker + Telemetry
  [P3.1] GitHub Actions (typecheck, test, publish)
  [P3.2] Dockerfile 多平台
  [P3.3] OpenTelemetry 集成

Week 11-12: Docs + SDK + VS Code
  [P3.4] 文档站点 (MkDocs/ReadTheDocs)
  [P3.5] http-recorder (测试录制/回放)
  [P3.6] VS Code 扩展 (基础)
  [P3.7] JS SDK (生成)
```

---

## 5. 版本里程碑

| 版本 | 内容 | 预计时间 | 依赖 |
|------|------|---------|------|
| v0.4.0 | System Context 代数 + Schema/Protocol 层 | 6 周 | 无 |
| v0.5.0 | Session V2 重构 | 3 周 | v0.4.0 |
| v0.6.0 | LLM Provider 增强 + Provider Caching | 2 周 | 无 |
| v0.7.0 | Tool Registry + Plugin SDK V2 | 2 周 | 无 |
| v0.8.0 | Agent + 权限增强 | 1 周 | 无 |
| v0.9.0 | 基础设施 (CI/CD, Docker, Telemetry) | 2 周 | 无 |
| v1.0.0 | 文档站点 + SDK + VS Code | 2 周 | 无 |

---

## 附录：文件映射与参考

| OpenCode 源文件 | CScode 目标文件 | 优先级 |
|-----------------|----------------|--------|
| `packages/core/src/system-context/index.ts` | `src/cscode/core/system_context/__init__.py` | P0 |
| `packages/core/src/system-context/registry.ts` | `src/cscode/core/system_context/registry.py` | P0 |
| `packages/core/src/system-context/builtins.ts` | `src/cscode/core/system_context/builtins.py` | P0 |
| `packages/core/src/session/input.ts` | `src/cscode/core/session_v2/input.py` | P0 |
| `packages/core/src/session/runner/index.ts` | `src/cscode/core/session_v2/runner.py` | P0 |
| `packages/core/src/session/run-coordinator.ts` | `src/cscode/core/session_v2/coordinator.py` | P0 |
| `packages/core/src/session/execution.ts` | `src/cscode/core/session_v2/execution.py` | P0 |
| `packages/core/src/session/context-epoch.ts` | `src/cscode/core/session_v2/context_epoch.py` | P0 |
| `packages/core/src/session/store.ts` | `src/cscode/core/session_v2/store.py` | P0 |
| `packages/schema/src/session-input.ts` | `src/cscode/schema/session_input.py` | P0 |
| `packages/schema/src/session.ts` | `src/cscode/schema/session.py` | P0 |
| `packages/schema/src/message.ts` | `src/cscode/schema/message.py` | P0 |
| `packages/protocol/src/groups/` | `src/cscode/protocol/groups/` | P0 |
| `packages/llm/src/cache-policy.ts` | `src/cscode/llm/cache_policy.py` | P0 |
| `packages/core/src/tool-output-store.ts` | `src/cscode/tools2/output_store.py` | P1 |
| `packages/plugin/src/` | `src/cscode/plugins/v2/` | P1 |
| `packages/core/src/permission/` | `src/cscode/core/` (增强) | P1 |
