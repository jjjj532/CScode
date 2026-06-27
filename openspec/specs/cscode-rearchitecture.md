# CScode 架构重写规格定义 (DEFINE)

> 基于 OpenCode (TypeScript, 31 packages) 源码深度分析 + CScode (Python) 现有源码逐模块对比
> 目标: 1:1 Python 重写，补齐全部架构层，消除 downstream bugs

---

## 1. 问题定义

### 1.1 当前症状

```
看着每个模块都有、功能很像 → 但运行起来功能和 OpenCode 差的太远，还有很多 bug
```

**根因:** CScode 现有代码只是 OpenCode 的"骨架"（文件名/目录名相似），缺少核心架构层：

| 缺失层 | 后果 |
|--------|------|
| Schema 层 (类型定义) | 类型错误运行时才暴露 |
| LLM 抽象层 (Route) | Provider 实现大量重复代码 |
| SessionRunner (标准化循环) | engine.py 474 行内联大函数 |
| Event Sourcing (事件溯源) | delete+reinsert 模式，并发丢数据 |
| Tool Materialize (工具编排) | 无权限过滤/无输出管理/无 schema 校验 |

### 1.2 范围边界

| 属于本阶段 | 不属于本阶段 |
|---|---|
| 核心引擎 (SessionRunner + EventSourcing) | TUI 改造 (无 UI 变化) |
| LLM Provider 抽象 (Route 系统) | CLI 重构 (API 兼容) |
| Tool 系统 (Materialize + Schema) | Plugin 系统 (现有保留) |
| 权限系统 (Wildcard + 持久化) | MCP 改造 (现有保留) |
| 消息系统 (Part 结构) | Desktop 改造 (无变化) |
| 错误模型 (LLMError + ToolFailure) | Web UI 改造 (无变化) |
| 配置系统 (多层级合并) | |

### 1.3 验收标准

1. **消息格式**: 所有内部消息使用 Part[] 结构而非 content: str
2. **SSR 恢复**: Session 可以通过事件溯源完整重建
3. **Tool 编排**: 工具调用经过 Schema 验证 + 权限过滤 + 输出管理
4. **LLM 事件**: Provider 输出标准化为 16 种 LLMEvent
5. **错误分类**: 所有 LLM 错误精确匹配 10 种 reason
6. **配置分层**: global → project → .cscode/ 三级合并生效
7. **现存测试**: 所有已有 `pytest tests/` + `mypy src/` + `ruff check src/` 通过

---

## 2. 目标架构

### 2.1 四层模型 (从 OpenCode 映射)

```
┌─────────────────────────────────────────────────────────┐
│                    app 层 (应用层)                        │
│  CLI / TUI / Server (保持现有入口兼容)                    │
│  使用 core 层 API, 不直接调 LLM/Storage                   │
├─────────────────────────────────────────────────────────┤
│                    core 层 (核心引擎)                      │
│  SessionRunner - 标准化 Agent Loop                       │
│  EventSourcing - 事件溯源 + 投影器                        │
│  ToolRegistry - 注册 + Materialize + Settlement          │
│  PermissionV2 - Wildcard 匹配 + 持久化                    │
│  Config - 多层级配置合并                                  │
├─────────────────────────────────────────────────────────┤
│                    llm 层 (LLM 抽象)                      │
│  Route - Protocol + Endpoint + Auth + Framing            │
│  LLMClient - generate / stream                           │
│  Schema - Message, ToolDefinition, LLMError, LLMEvent    │
│  ToolRuntime - dispatch                                  │
├─────────────────────────────────────────────────────────┤
│                    schema 层 (共享类型)                    │
│  LLMError, LLMEvent, SessionEvent, Message, Tool Schema  │
│  纯类型定义, 无运行时依赖                                  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 包结构

```
src/cscode/
├── schema/              # 新: 共享类型层
│   ├── __init__.py
│   ├── messages.py      # Message, SystemPart, TextPart, MediaPart, ToolCallPart, ToolResultPart
│   ├── events.py        # LLMEvent (16 种), SessionEvent (35+ 种)
│   ├── errors.py        # LLMError (10 reason), ToolFailure
│   ├── ids.py           # SessionID, ToolCallID, ModelID, ProviderID (NewType)
│   ├── options.py       # GenerationOptions, ProviderOptions, CachePolicy
│   └── tool.py          # ToolDefinition, ToolChoice
├── llm/                 # 新: LLM 抽象层
│   ├── __init__.py
│   ├── client.py        # LLMClient: generate/stream
│   ├── route.py         # Protocol, Endpoint, Auth, Framing
│   ├── tool_runtime.py  # ToolRuntime.dispatch
│   ├── protocols/       # openai_chat.py, anthropic_messages.py, gemini.py...
│   └── providers/       # openai.py, anthropic.py, google.py...
├── core/                # 改: 核心引擎层 (保留现有文件名兼容)
│   ├── session.py       # 新: SessionV2 (Event Sourcing)
│   ├── runner.py        # 新: SessionRunner (从 engine.py 提取)
│   ├── tool_registry.py # 新: ToolRegistryV2 (Materialize + Settlement)
│   ├── permission.py    # 改: PermissionV2 (Wildcard + 持久化)
│   ├── config.py        # 改: ConfigV2 (多层级 + Agent 配置)
│   ├── event_store.py   # 改: EventStoreV2 (集成投影器)
│   ├── compaction.py    # 改: CompactionV2 (overflow 恢复)
│   ├── engine.py        # 弃: 474 行大函数 → 迁移到 runner.py
│   ├── session_manager.py # 弃: 内存 dict → 迁移到 session.py
│   └── messages.py      # 弃: 迁移到 schema/messages.py
├── storage/
│   ├── db.py            # 改: 新增迁移
│   └── session.py       # 改: 基于 Event Sourcing 重写
├── tools/
│   └── base.py          # 改: 基于 Tool Schema 重写
├── providers/           # 改: 基于 llm 层重写
└── server/
    └── app.py           # 改: 迁移到 core 层 API
```

---

## 3. 模块规格

### 3.1 Schema 层 (`src/cscode/schema/`)

#### Message 系统

```python
@dataclass
class SystemPart:
    type: Literal["system"] = "system"
    text: str

@dataclass
class TextPart:
    type: Literal["text"] = "text"
    text: str

@dataclass
class MediaPart:
    type: Literal["media"] = "media"
    media_type: str  # MIME
    data: str | bytes  # base64 or raw

@dataclass
class ToolCallPart:
    type: Literal["tool-call"] = "tool-call"
    tool_call_id: str
    name: str
    args: dict[str, Any]

@dataclass
class ToolResultPart:
    type: Literal["tool-result"] = "tool-result"
    tool_call_id: str
    name: str
    result: str
    is_error: bool = False

@dataclass
class ReasoningPart:
    type: Literal["reasoning"] = "reasoning"
    text: str
    signature: str | None = None

Part = SystemPart | TextPart | MediaPart | ToolCallPart | ToolResultPart | ReasoningPart

@dataclass
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    parts: list[Part]
    # 兼容层: content 属性由 parts 合成
    @property
    def content(self) -> str:
        return "".join(p.text for p in self.parts if hasattr(p, "text"))
```

#### LLMError 系统

```python
class LLMErrorReason(str, Enum):
    INVALID_REQUEST = "InvalidRequest"           # 参数错误, 不可重试
    NO_ROUTE = "NoRoute"                          # 找不到路由, 不可重试
    AUTHENTICATION = "Authentication"             # 认证失败, 不可重试
    RATE_LIMIT = "RateLimit"                      # 限流, 可重试含 retryAfterMs
    QUOTA_EXCEEDED = "QuotaExceeded"              # 配额超限, 不可重试
    CONTENT_POLICY = "ContentPolicy"              # 内容策略, 不可重试
    PROVIDER_INTERNAL = "ProviderInternal"        # 服务端错误, 可重试
    TRANSPORT = "Transport"                       # 网络错误, 不可重试
    INVALID_PROVIDER_OUTPUT = "InvalidProviderOutput"  # 解析失败, 不可重试
    UNKNOWN_PROVIDER = "UnknownProvider"          # 未知 provider, 不可重试

@dataclass
class LLMError(Exception):
    module: str
    method: str
    reason: LLMErrorReason
    message: str
    retryable: bool = False
    retry_after_ms: int | None = None

class ToolFailure(Exception):
    message: str
```

#### LLMEvent 系统

```python
@dataclass
class TextStarted: ...
@dataclass
class TextDelta:
    text: str
@dataclass
class TextEnded: ...
@dataclass
class ToolCallStarted:
    tool_call_id: str
    name: str
@dataclass
class ToolCallDelta:
    tool_call_id: str
    args_text: str
@dataclass
class ToolCallEnded:
    tool_call_id: str
    name: str
    args: dict[str, Any]
@dataclass
class ToolResult:
    tool_call_id: str
    result: str
    is_error: bool
@dataclass
class ToolFailure2:  # 避免命名冲突
    tool_call_id: str
    error: str
@dataclass
class ReasoningStarted:
    signature: str | None = None
@dataclass
class ReasoningDelta:
    text: str
    signature: str | None = None
@dataclass
class ReasoningEnded:
    text: str
    signature: str | None = None
@dataclass
class Finish:
    finish_reason: str
    usage: dict[str, int] | None = None
@dataclass
class Error:
    error: LLMError
@dataclass
class Pending: ...  # Provider 占用 UI

LLMEvent = TextStarted | TextDelta | TextEnded | \
           ToolCallStarted | ToolCallDelta | ToolCallEnded | \
           ToolResult | ToolFailure2 | \
           ReasoningStarted | ReasoningDelta | ReasoningEnded | \
           Finish | Error | Pending
```

### 3.2 LLM 层 (`src/cscode/llm/`)

#### Route 系统

```python
@dataclass
class Route:
    protocol: str        # "openai-chat", "anthropic-messages"
    base_url: str        # 基础 URL
    headers: dict[str, str]  # 固定 header
    auth: AuthMode       # bearer / header / none
    framing: FramingMode # "sse" / "json"

    def build_request(self, llm_request: LLMRequest) -> HTTPRequest: ...
    def parse_response(self, raw: str) -> list[LLMEvent]: ...

# 具体路由注册
ROUTES: dict[str, Route] = {
    "openai-responses": Route("openai-responses", "https://api.openai.com/v1/responses", ...),
    "anthropic-messages": Route("anthropic-messages", "https://api.anthropic.com/v1/messages", ...),
    "openai-compatible-chat": Route("openai-compatible-chat", "{base_url}/chat/completions", ...),
}
```

#### LLMClient

```python
class LLMClient:
    async def generate(self, request: LLMRequest) -> LLMResponse: ...
    def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]: ...
```

#### ToolRuntime

```python
class ToolRuntime:
    @staticmethod
    async def dispatch(tools: dict[str, Tool], call: ToolCallPart) -> list[LLMEvent]: ...
```

### 3.3 Core 层 (`src/cscode/core/`)

#### SessionV2 (Event Sourcing)

```python
class SessionV2:
    @staticmethod
    async def create(db: Database) -> SessionInfo: ...

    async def prompt(self, user_input: str) -> None:
        """写入 event → 触发 runner wake (非阻塞)"""
        event = SessionEvent.Prompted(content=user_input)
        await self.event_store.append(self.id, [event])
        await self.scheduler.wake(self.id)

    async def resume(self) -> str:
        """从事件溯源重建 → 运行 runner"""
        events = await self.event_store.read(self.id)
        state = SessionProjector.project(events)
        return await SessionRunner.run(self.id, state)
```

#### SessionRunner

```python
class SessionRunner:
    @staticmethod
    async def run(session_id: str, state: SessionState) -> str:
        """
        循环: toLLMMessages → LLMClient.stream → 处理 LLMEvent → tool dispatch → loop
        提取自 engine.py 的 _run_loop, 但有明确的职责划分。
        """
        while needs_continuation:
            messages = to_llm_messages(state.history)
            tools = tool_registry.materialize(state.permissions)
            async for event in llm_client.stream(LLMRequest(model, messages, tools)):
                match event:
                    case TextDelta(): ...
                    case ToolCallEnded():
                        for result_event in ToolRuntime.dispatch(tools, event):
                            yield result_event
                    case Finish(): ...
                    case Error(): ...
            state = await apply_events(state, pending_events)
```

#### PermissionV2

```python
class PermissionV2:
    @staticmethod
    def evaluate(action: str, resource: str, rulesets: list[Ruleset]) -> Rule:
        """Wildcard 匹配, last-match-wins"""

class Wildcard:
    @staticmethod
    def match(pattern: str, value: str) -> bool: ...

class SavedRules:
    async def load(self) -> list[Rule]: ...
    async def save(self, rule: Rule) -> None: ...
```

#### ToolRegistryV2

```python
class ToolRegistryV2:
    # 两层作用域
    application_tools: dict[str, Tool]   # 进程级
    location_tools: dict[str, Tool]      # 项目级

    def register(self, name: str, tool: Tool, scope: Scope) -> None: ...
    def materialize(self, permissions: list[Rule]) -> Materialization:
        """按权限过滤 → definitions(给LLM) + settle(执行)"""
    def settle(self, tool_call: ToolCallPart) -> ToolResult: ...
```

### 3.4 配置系统 (ConfigV2)

```python
@dataclass
class ConfigV2:
    shell: ShellConfig | None = None
    model: ModelConfig | None = None
    agent: dict[str, AgentConfig] = field(default_factory=dict)
    permissions: list[Ruleset] = field(default_factory=list)
    mcp: list[MCPConfig] = field(default_factory=list)
    plugin: list[PluginConfig] = field(default_factory=list)
    provider: dict[str, ProviderConfig] = field(default_factory=dict)

    # 加载链: global → project discover → .opencode/
    @classmethod
    def load(cls) -> ConfigV2: ...
```

---

## 4. 迁移策略

### 4.1 兼容性要求

1. **向后兼容**: 现有 `Config.from_dict()/from_yaml()` 继续可用，内部映射到 `ConfigV2`
2. **消息兼容**: 新代码内部使用 `Part[]`，对外接口 `content` 属性保持现有字符串 API
3. **Provider 兼容**: 旧 provider 在新 Route 系统上线前继续可用
4. **API 兼容**: `Agent.run()`, `Agent.run_with_permissions()` 保持签名

### 4.2 增量迁移阶段

```
Phase 0: Schema 层
  └── 新建 src/cscode/schema/
  └── 无运行时影响, 纯类型定义
  └── 可并行开发

Phase 1: LLM 层
  └── 新建 src/cscode/llm/
  └── 旧 provider 保持不动
  └── 写完即可用少量测试验证 LLMClient.stream() 是否标准化

Phase 2: Core 层 (最关键的改造)
  └── 新建 SessionV2 / SessionRunner
  └── 旧 engine.py 保持不动
  └── 双轨并行: 新代码逐步替换旧代码调用点
  └── 每次替换: 先替换存储 → 再替换 engine → 再替换入口

Phase 3: 清理
  └── 删除 engine.py
  └── 删除 session_manager.py
  └── 统一所有 import 路径
```

### 4.3 风险控制

| 风险 | 缓解 |
|------|------|
| 双轨并行期间代码不一致 | 严格隔离新旧路径: 新代码无任何旧 import |
| Schema 层与 Pydantic 冲突 | schema/ 纯 dataclass, 不使用 Pydantic |
| Event Sourcing 性能 | 批处理投影器, 按 session 分片 |
| 迁移期间 bug 难定位 | 新旧路径各走各的, A/B 测试 |

---

## 5. 下一阶段 (PLAN) 输入

本 DEFINE 文档完成后的 PLAN 阶段需要:

1. 按 Phase 0-3 拆分为可执行的原子任务
2. 每个任务标注: 文件路径、依赖、预计代码行数
3. 确定并行执行机会 (Phase 0+Phase 1 可并行)
4. 明确每个任务的测试策略

### 当前状态总结

| 阶段 | 状态 | 产出 |
|------|------|------|
| OpenCode 源码分析 | ✅ 完成 | `docs/opencode-analysis/source-analysis.md` (900+ 行) |
| CScode 逐模块对比 | ✅ 完成 | 同上 (下篇) |
| DEFINE 规格定义 | ✅ 完成 | `openspec/specs/cscode-rearchitecture.md` |
| PLAN 任务规划 | ⏳ 待开始 | 下一个会话 |
| BUILD 实现 | ⏳ 待开始 | |
| VERIFY 验证 | ⏳ 待开始 | |
| REVIEW 审查 | ⏳ 待开始 | |
| SHIP 发布 | ⏳ 待开始 | |
