# CScode vs OpenCode 差距分析 & 技术规格

> 生成日期: 2026-07-27
> OpenCode 版本参考: dev-7 (v1.18.6)
> CScode 版本: v0.3.5

---

## 目录

1. [差距矩阵](#1-差距矩阵)
2. [核心架构模块](#2-核心架构模块)
   - 2.1 [System Context 代数系统](#21-system-context-代数系统)
   - 2.2 [Context Epoch](#22-context-epoch)
   - 2.3 [Session V2 架构](#23-session-v2-架构)
   - 2.4 [Schema/Protocol 层](#24-schemaprotocol-层)
3. [LLM 抽象层](#3-llm-抽象层)
   - 3.1 [路由系统四轴架构](#31-路由系统四轴架构)
   - 3.2 [OpenAI Responses API](#32-openai-responses-api)
   - 3.3 [GitHub Copilot 集成](#33-github-copilot-集成)
   - 3.4 [Provider Caching](#34-provider-caching)
   - 3.5 [Provider-defined Tools](#35-provider-defined-tools)
4. [工具与插件系统](#4-工具与插件系统)
5. [其他功能增强](#5-其他功能增强)
6. [文件映射与参考](#6-文件映射与参考)

---

## 1. 差距矩阵

### P0 - 必须追齐（核心功能）

| # | 模块 | 状态 | 说明 |
|---|------|------|------|
| P0.1 | System Context 代数 | 缺失 | Context Epoch 前置依赖 |
| P0.2 | Context Epoch | 缺失 | 会话上下文快照 |
| P0.3 | LLM 路由四轴架构 | 部分 | Protocol/Endpoint/Auth/Framing 分层 |
| P0.4 | OpenAI Responses API | 缺失 | 新版 API + WebSocket |
| P0.5 | GitHub Copilot | 缺失 | OAuth + Copilot Provider |
| P0.6 | Schema/Protocol 层 | 缺失 | 领域模型与 API 解耦 |

### P1 - 重要功能

| # | 模块 | 状态 | 说明 |
|---|------|------|------|
| P1.1 | Provider Caching | 缺失 | auto/manual cache policy |
| P1.2 | Provider-defined Tools | 缺失 | Anthropic hosted tools |
| P1.3 | Tool Output Bounding | 需完善 | 超大输出管理 |
| P1.4 | Plugin SDK V2 | 需完善 | context source, lifecycle hooks |
| P1.5 | 子 Agent (@general) | 部分 | 权限受限子 agent |
| P1.6 | Permission 增强 | 需完善 | arity evaluation, location-scoped |

### P2 - 次要功能

| # | 模块 | 状态 | 说明 |
|---|------|------|------|
| P2.1 | TUI 音频 | 缺失 | 提示音 |
| P2.2 | TUI 剪贴板 | 缺失 | 系统剪贴板集成 |
| P2.3 | VS Code 扩展 | 缺失 | IDE 集成 |
| P2.4 | JS SDK | 缺失 | 客户端 SDK |
| P2.5 | CI/CD 完善 | 缺失 | 更多 GitHub Actions |

---

## 2. 核心架构模块

### 2.1 System Context 代数系统

#### 2.1.1 目标

实现 OpenCode `packages/core/src/system-context/` 的等效系统 —— 将系统上下文建模为独立可刷新的类型源代数。

#### 2.1.2 核心接口

```python
# src/cscode/core/system_context/__init__.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

A = TypeVar("A")

class UNAVAILABLE:
    """哨兵：临时不可观测"""
    pass

@dataclass(frozen=True)
class ContextKey:
    """命名空间稳定标识，格式: "namespace/name" """
    value: str

class ContextSource(Generic[A]):
    """一个类型化上下文源的代数描述"""
    key: ContextKey
    load: Callable[[], Awaitable[A | type[UNAVAILABLE]]]
    baseline: Callable[[A], str]
    update: Callable[[A, A], str]
    removed: Callable[[A], str] | None = None

@dataclass(frozen=True)
class SourceSnapshot:
    """持久化比较状态"""
    value: Any
    removed: str | None = None

class SystemContext:
    """可组合上下文的不透明载体"""
    _sources: list

@dataclass(frozen=True)
class ContextGeneration:
    """一次初始化的完整结果"""
    baseline: str
    snapshot: dict[str, SourceSnapshot]

# Reconcile 结果类型
@dataclass(frozen=True)
class Unchanged: pass

@dataclass(frozen=True)
class Updated:
    text: str
    snapshot: dict[str, SourceSnapshot]

@dataclass(frozen=True)
class ReplacementReady:
    generation: ContextGeneration

@dataclass(frozen=True)
class ReplacementBlocked: pass

ReconcileResult = Unchanged | Updated | ReplacementReady | ReplacementBlocked
```

#### 2.1.3 核心函数

```python
def make(source: ContextSource[A]) -> SystemContext:
    """将类型化 source 封装为可组合上下文"""

def combine(contexts: list[SystemContext]) -> SystemContext:
    """组合多个上下文，重复 key 拒绝"""

async def initialize(ctx: SystemContext) -> ContextGeneration:
    """创建不可变 baseline + 持久化 snapshot"""

async def reconcile(ctx: SystemContext, previous: dict[str, SourceSnapshot]) -> ReconcileResult:
    """比较当前值与 snapshot，返回变化类型"""

async def replace(ctx: SystemContext, previous: dict[str, SourceSnapshot]) -> ReplacementReady | ReplacementBlocked:
    """创建完全替换或在不可用时阻塞"""
```

#### 2.1.4 内置 Sources

```python
# src/cscode/core/system_context/builtins.py

def create_builtin_context() -> SystemContext:
    return SystemContext.combine([
        SystemContext.make(ContextSource(
            key=ContextKey("core/environment"),
            load=_load_environment,
            baseline=_render_baseline,
            update=_render_update,
        )),
        SystemContext.make(ContextSource(
            key=ContextKey("core/date"),
            load=_load_date,
            baseline=lambda d: f"Today: {d}",
            update=lambda p, c: f"Date changed to: {c}",
        )),
        SystemContext.make(ContextSource(
            key=ContextKey("core/instructions"),
            load=_load_instructions,
            baseline=_render_baseline,
            update=_render_update,
            removed=_render_removed,
        )),
        SystemContext.make(ContextSource(
            key=ContextKey("core/agent-skills"),
            load=_load_skills,
            baseline=_render_baseline,
            update=_render_update,
        )),
    ])
```

---

### 2.2 Context Epoch

#### 2.2.1 目标

实现会话上下文快照系统，支持跨会话高效恢复。

#### 2.2.2 依赖

**前置：System Context 代数系统 (P0.1)**

Context Epoch 依赖 System Context 的 `initialize/reconcile/replace` 函数来管理快照生命周期。

#### 2.2.3 接口

```python
# src/cscode/core/session_v2/context_epoch.py

class SessionContextEpoch:
    """管理 session 的 Context Epoch 生命周期"""

    @staticmethod
    async def initialize(
        db: Database,
        context: SystemContext,
        session_id: str
    ) -> tuple[str, int] | None:
        """初始化第一个 epoch。返回 (baseline_text, baseline_seq)。"""

    @staticmethod
    async def prepare(
        db: Database,
        events: EventStore,
        context: SystemContext,
        session_id: str
    ) -> tuple[str, int]:
        """准备 provider turn。返回 (baseline_or_updated_text, baseline_seq)。"""

    @staticmethod
    async def compact(
        db: Database,
        events: EventStore,
        context: SystemContext,
        session_id: str
    ) -> None:
        """压缩：新 epoch，新 baseline，旧中间消息移除。"""
```

#### 2.2.4 存储

```sql
-- 使用现有 context_epochs 表
CREATE TABLE context_epochs (
    session_id TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    baseline_seq INTEGER NOT NULL,
    snapshot TEXT NOT NULL,  -- JSON encoded Snapshot
    baseline TEXT NOT NULL,  -- rendered baseline text
    PRIMARY KEY (session_id, epoch)
);
```

---

### 2.3 Session V2 架构

#### 2.3.1 目标

durable prompt admission 与执行分离、prompt steering/queue、Session Drain 概念。

#### 2.3.2 核心概念

| 概念 | 说明 |
|------|------|
| AdmittedInput | 已录入但未入历史的 prompt |
| delivery="steer" | 当前 drain 内立即 promote |
| delivery="queue" | 当前 drain 空闲后才 promote |
| Session Drain | 一次 process-local 执行范围 |
| RunCoordinator | 同 Session 串行化 |

#### 2.3.3 数据模型

```python
# src/cscode/core/session_v2/input.py

class DeliveryMode(str, Enum):
    STEER = "steer"   # 当前 drain 内立即 promote
    QUEUE = "queue"   # 空闲后才 promote

@dataclass
class AdmittedInput:
    id: str
    session_id: str
    prompt: str
    delivery: DeliveryMode
    admitted_seq: int
    time_created: datetime
    promoted_seq: int | None = None
```

#### 2.3.4 SessionInput API

```python
class SessionInput:
    @staticmethod
    async def admit(db: Database, events: EventStore, input: AdmittedInput) -> AdmittedInput:
        """持久化 admit prompt。幂等。"""

    @staticmethod
    async def promote_steers(db: Database, events: EventStore, session_id: str, cutoff_seq: int) -> int:
        """promote 所有 steer deliveries。"""

    @staticmethod
    async def promote_next_queued(db: Database, events: EventStore, session_id: str) -> bool:
        """空闲时 promote 一个 queued input。"""

    @staticmethod
    async def has_pending(db: Database, session_id: str, delivery: DeliveryMode) -> bool:
        """检查是否有待处理输入。"""
```

#### 2.3.5 SessionRunner

```python
class SessionRunner:
    async def run(self, session_id: str, force: bool = False) -> None:
        """
        Main drain loop:
        1. Load session + context epoch
        2. Promote eligible steers
        3. Build context (baseline + mid-conv updates + history)
        4. Execute provider turn
        5. If tools -> continue, else -> promote next queued
        """
```

---

### 2.4 Schema/Protocol 层

#### 2.4.1 目标

将领域模型与 API 端点实现解耦，建立独立 schema + protocol 层。

#### 2.4.2 目标架构

```
src/cscode/schema/         -- 领域模型定义
    ids.py                 -- SessionID, MessageID, ToolCallID
    session.py             -- SessionInfo, SessionState
    session_input.py       -- AdmittedInput, DeliveryMode
    message.py             -- Message, Part, ToolCall

src/cscode/protocol/       -- API 协议定义
    groups/
        sessions.py        -- Session 端点组
        tools.py           -- Tool 端点组
        config.py          -- Config 端点组
    errors.py              -- 统一错误类型

src/cscode/server/routes/  -- FastAPI 实现
    sessions.py
    tools.py
    config.py
```

#### 2.4.3 Schema 示例

```python
# src/cscode/schema/ids.py
from typing import Annotated
from pydantic import StringConstraints

SessionID = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]{26}$")]
MessageID = Annotated[str, StringConstraints(pattern=r"^msg_[a-z0-9]{24}$")]
ToolCallID = Annotated[str, StringConstraints(pattern=r"^call_[a-z0-9]{24}$")]
```

---

## 3. LLM 抽象层

### 3.1 路由系统四轴架构

#### 3.1.1 目标

将 LLM Provider 抽象从"一个文件一个 provider"重构为四轴分层：

| 轴 | 职责 | 示例 |
|---|------|------|
| **Protocol** | 请求体构建 + 流解析 | OpenAI Chat, Anthropic Messages, Gemini |
| **Endpoint** | URL 构造 | api.openai.com/v1/chat/completions |
| **Auth** | 认证方式 | bearer, header, SigV4 |
| **Framing** | 帧格式 | SSE, AWS event-stream, WebSocket |

#### 3.1.2 接口设计

```python
# src/cscode/llm/route.py

from dataclasses import dataclass
from typing import Protocol, Literal

class Protocol(Protocol):
    """请求体构建 + 流解析"""
    def build_request(self, model: str, messages: list, **opts) -> dict: ...
    def parse_response(self, data: dict) -> LLMResponse: ...
    def parse_stream(self, chunk: dict) -> StreamChunk | None: ...

class Endpoint:
    """URL 构造"""
    base_url: str
    path: str

    def url(self, model: str) -> str: ...

class Auth:
    """认证方式"""
    type: Literal["bearer", "header", "sigv4", "oauth"]
    def headers(self) -> dict: ...

class Framing:
    """帧格式"""
    type: Literal["sse", "aws_event_stream", "websocket", "json"]
    def encode(self, data: dict) -> bytes: ...
    def decode(self, data: bytes) -> dict | None: ...

@dataclass
class Route:
    id: str
    provider: str
    protocol: Protocol
    endpoint: Endpoint
    auth: Auth
    framing: Framing
```

#### 3.1.3 现有 Provider 重构

```python
# src/cscode/llm/providers/openai_chat.py

class OpenAIChatProtocol:
    """OpenAI Chat API 协议实现"""

    def build_request(self, model: str, messages: list, **opts) -> dict:
        return {
            "model": model,
            "messages": messages,
            "stream": opts.get("stream", False),
            **opts,
        }

    def parse_response(self, data: dict) -> LLMResponse:
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            usage=data.get("usage", {}),
        )

    def parse_stream(self, chunk: dict) -> StreamChunk | None:
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        if "content" in delta:
            return StreamChunk(content=delta["content"])
        return None
```

---

### 3.2 OpenAI Responses API

#### 3.2.1 目标

支持 OpenAI 最新 Responses API（区别于 Chat API）。

#### 3.2.2 核心差异

| 特性 | Chat API | Responses API |
|------|----------|---------------|
| 工具调用 | function calling | built-in tools |
| 传输 | SSE | SSE + **WebSocket** |
| 文件输入 | URL | 直接上传 |

#### 3.2.3 接口设计

```python
# src/cscode/llm/protocols/responses.py

class OpenAIResponsesProtocol:
    """OpenAI Responses API 协议"""

    def build_request(self, model: str, messages: list, **opts) -> dict:
        return {
            "model": model,
            "input": messages,  # 不同格式
            "tools": opts.get("tools"),  # hosted tools
            "tool_choice": opts.get("tool_choice"),
            **opts,
        }

    # WebSocket 支持
    async def stream_websocket(self, url: str, request: dict) -> AsyncIterator[StreamChunk]:
        """WebSocket 流式传输"""
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps(request))
            async for msg in ws:
                yield self.parse_stream(json.loads(msg))
```

#### 3.2.4 Hosted Tools

```python
# src/cscode/llm/tools/hosted.py

class WebSearchTool:
    """OpenAI hosted web search"""
    name = "web_search"
    description = "Search the web for current information"

    async def execute(self, query: str) -> str:
        """调用 OpenAI hosted web search API"""

class FileSearchTool:
    """OpenAI hosted file search"""
    name = "file_search"
    description = "Search files in knowledge base"

    async def execute(self, query: str, knowledge_base_id: str) -> str:
        """调用 OpenAI hosted file search API"""

class CodeInterpreterTool:
    """OpenAI hosted code execution"""
    name = "code_interpreter"
    description = "Execute Python code in sandbox"

    async def execute(self, code: str) -> CodeResult:
        """调用 OpenAI hosted code interpreter API"""
```

---

### 3.3 GitHub Copilot 集成

#### 3.3.1 目标

支持 GitHub Copilot 作为 LLM Provider。

#### 3.3.2 核心挑战

- OAuth 认证流程（与 API Key 不同的认证方式）
- Copilot 特有的错误处理（rate limit, quota）
- 不同的 API 端点和请求格式

#### 3.3.3 接口设计

```python
# src/cscode/llm/providers/copilot.py

from dataclasses import dataclass

@dataclass
class CopilotAuth:
    """GitHub OAuth 认证"""
    access_token: str
    refresh_token: str | None = None
    expires_at: float | None = None

    async def refresh(self) -> CopilotAuth:
        """刷新 OAuth token"""

class CopilotProvider:
    """GitHub Copilot Provider"""

    def __init__(self, auth: CopilotAuth):
        self.auth = auth
        self.base_url = "https://api.github.com/copilot"

    async def complete(self, messages: list[Message], opts: dict) -> LLMResponse:
        """调用 Copilot API"""

    async def stream(self, messages: list[Message], opts: dict) -> AsyncIterator[StreamChunk]:
        """流式调用 Copilot API"""

    def parse_error(self, response: dict) -> CopilotError:
        """Copilot 特有错误处理"""
        # rate_limit_exceeded
        # quota_exceeded
        # authentication_failed
```

#### 3.3.4 OAuth 流程

```python
# src/cscode/llm/providers/copilot_oauth.py

class CopilotOAuth:
    """GitHub Copilot OAuth 流程"""

    CLIENT_ID = "github_copilot_client"
    SCOPES = ["read:user", "repo", "copilot"]

    @staticmethod
    def authorization_url(state: str) -> str:
        """生成授权 URL"""
        return f"https://github.com/login/oauth/authorize?client_id={CLIENT_ID}&scope={' '.join(CopilotOAuth.SCOPES)}&state={state}"

    @staticmethod
    async def exchange_code(code: str) -> CopilotAuth:
        """交换 authorization code 为 access token"""
        # POST https://github.com/login/oauth/access_token
        # 返回 access_token, token_type, expires_in

    @staticmethod
    async def refresh(auth: CopilotAuth) -> CopilotAuth:
        """刷新 token"""
        # POST https://github.com/login/oauth/access_token with grant_type=refresh_token
```

---

### 3.4 Provider Caching

#### 3.4.1 目标

实现 Provider 级别的请求缓存，减少重复调用。

#### 3.4.2 缓存策略

```python
# src/cscode/llm/cache_policy.py

from typing import Literal

CacheHintType = Literal["ephemeral"]

@dataclass
class CacheHint:
    type: CacheHintType = "ephemeral"
    ttl_seconds: int | None = None

# 缓存策略类型
# True/"auto"  -> 默认自动放置
# False/"none" -> 不缓存
# dict         -> 显式策略
CachePolicy = bool | str | dict[
    Literal["tools", "system", "messages", "ttl_seconds"],
    bool | str | int,
]

# 支持缓存的协议
PROTOCOL_CACHE_SUPPORT = {
    "anthropic-messages": True,   # cache_control markers
    "bedrock-converse": True,     # cachePoint blocks
    "openai-chat": False,         # 服务端隐式
    "openai-responses": False,    # 服务端隐式
    "gemini": False,              # 隐式 + out-of-band
}
```

#### 3.4.2 自动缓存逻辑

```python
def apply_cache_policy(request: dict, protocol_id: str) -> dict:
    """自动缓存策略：
    - 最后一次 tool 定义
    - 最后一次 system message
    - 最新 user message
    """
    if not PROTOCOL_CACHE_SUPPORT.get(protocol_id):
        return request

    # 添加 cache_control markers
    messages = request.get("messages", [])
    if messages:
        # last tool
        # last system
        # latest user
        pass

    return request
```

---

### 3.5 Provider-defined Tools

#### 3.5.1 目标

正确处理 Provider 提供的 hosted tools（如 Anthropic 的 web_search、code_execution）。

#### 3.5.2 核心概念

Provider-defined tools 由 LLM Provider 提供执行能力，只需提供参数：

```python
# OpenCode 中的标记
{
  "type": "tool_use",
  "id": "toolu_xxx",
  "name": "web_search",
  "input": {"query": "latest news"},
  "provider_executed": true  # <-- 关键标记
}
```

#### 3.5.3 实现

```python
# src/cscode/llm/provider_tools.py

class ProviderToolExecutor:
    """执行 provider 提供的工具"""

    PROVIDER_TOOLS = {
        "anthropic": {
            "web_search": AnthropicWebSearch(),
            "code_execution": AnthropicCodeExecution(),
        },
        "openai": {
            "web_search": OpenAIWebSearch(),
            "file_search": OpenAIFileSearch(),
            "code_interpreter": OpenAICodeInterpreter(),
        },
    }

    async def execute(
        self,
        provider: str,
        tool_name: str,
        arguments: dict
    ) -> ToolResult:
        """执行 provider 定义的工具"""
        tool = self.PROVIDER_TOOLS.get(provider, {}).get(tool_name)
        if not tool:
            raise ValueError(f"Unknown provider tool: {provider}.{tool_name}")

        return await tool.execute(**arguments)
```

---

## 4. 工具与插件系统

### 4.1 Tool Output Bounding

```python
# src/cscode/tools2/output_store.py

class ToolOutputStore:
    """管理超大工具输出的文件存储"""

    MAX_LINES = 500
    MAX_BYTES = 512 * 1024  # 512KB
    RETENTION_SECONDS = 36000

    async def store(self, session_id: str, content: str) -> ManagedOutput:
        """存储超大自然结果。返回 bounded preview + path。"""

    async def read(self, path: str) -> str | None:
        """读取存储的输出文件。"""

    async def cleanup(self, session_id: str) -> None:
        """清理过期的输出文件。"""

@dataclass
class BoundedOutput:
    preview: str
    truncated: bool
    managed_path: str | None = None
```

### 4.2 Plugin SDK V2

```python
# src/cscode/plugins/v2/context_source.py
class PluginContextSource:
    """插件定义的系统上下文源"""
    key: str
    load: Callable[[], Awaitable[str]]
    baseline: Callable[[str], str]
    update: Callable[[str, str], str]

# src/cscode/plugins/v2/lifecycle.py
class PluginLifecycle:
    async def on_activate(self) -> None: ...
    async def on_deactivate(self) -> None: ...
    async def on_session_start(self, session_id: str) -> None: ...
    async def on_session_end(self, session_id: str) -> None: ...
```

---

## 5. 其他功能增强

### 5.1 子 Agent (@general)

```python
# src/cscode/core/agent/subagent.py

@dataclass
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
```

### 5.2 Permission 增强

```python
# src/cscode/core/permission_enhanced.py

class Arity(str, Enum):
    EXACT = "exact"
    PREFIX = "prefix"
    ANY = "any"

class LocationPermissions:
    """Location-scoped 权限上下文"""
    location_id: str
    rulesets: list[Ruleset]

    async def evaluate(self, action: str, resource: str) -> bool:
        """在此 location 的上下文中评估权限。"""
```

---

## 6. 文件映射与参考

| OpenCode 源文件 | CScode 目标文件 | 优先级 |
|-----------------|----------------|--------|
| `packages/core/src/system-context/index.ts` | `src/cscode/core/system_context/__init__.py` | P0.1 |
| `packages/core/src/system-context/registry.ts` | `src/cscode/core/system_context/registry.py` | P0.1 |
| `packages/core/src/system-context/builtins.ts` | `src/cscode/core/system_context/builtins.py` | P0.1 |
| `packages/core/src/session/context-epoch.ts` | `src/cscode/core/session_v2/context_epoch.py` | P0.2 |
| `packages/core/src/session/input.ts` | `src/cscode/core/session_v2/input.py` | P0.3 |
| `packages/core/src/session/run-coordinator.ts` | `src/cscode/core/session_v2/coordinator.py` | P0.3 |
| `packages/llm/src/route.ts` | `src/cscode/llm/route.py` | P0.3 |
| `packages/llm/src/protocols/openai-responses.ts` | `src/cscode/llm/protocols/responses.py` | P0.4 |
| `packages/llm/src/providers/github-copilot.ts` | `src/cscode/llm/providers/copilot.py` | P0.5 |
| `packages/llm/src/cache-policy.ts` | `src/cscode/llm/cache_policy.py` | P1.1 |
| `packages/core/src/tool-output-store.ts` | `src/cscode/tools2/output_store.py` | P1.3 |
| `packages/plugin/src/` | `src/cscode/plugins/v2/` | P1.4 |