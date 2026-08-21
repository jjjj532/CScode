# CScode 迭代升级 Spec v1.0

> **依据**：DeepSeek Harness 深度分析（`docs/deepseek-harness-analysis.md`，792 行）+ OpenCode 最新源码分析（`github/opencode-dev-10`，3,353 文件 / 57,108 节点 / 198,804 边 codegraph 索引）+ CScode 现状核查（codegraph 逐一验证，2026-08-18）。
> **总览**：`docs/cscode-iteration-plan.md`（v2 核查修正版）
> **目标**：指导 CScode（当前 0.3.6 / `pyinstaller-bundle`）的迭代升级开发，补齐与两大 AI 编码工具的真实差距。
> **状态**：Draft → 评审中

---

## 1. 背景与依据（三方分析整合）

### 1.1 DeepSeek Harness 关键架构（dsh）

| 能力 | 要点 | CScode 现状（核查） |
|---|---|---|
| 插件树（Cordis） | 一切皆插件，Profiles + Bundles 组合 | ⚠️ 有 Plugin v2（`plugins/sdk.py`）但未全覆盖三层 UI |
| Session log + 投影 | 事件溯源，模型消息词汇统一 | ✅ 已实现（EventStore + projector） |
| **Capability Seams** | host/agent/seam 三角色决策表——「新行为放哪里」有明确规则 | ⚠️ 部分（工具分层有，但无正式 seam 文档化） |
| LlmAdapter 缝 | SSE 断连重试、超时、chunk 校验 + LlmError 结构化 | ✅ 已实现（错误代数 + retryable） |
| **沙箱体系** | landlock/seatbelt/E2B 平台 runner 链 | ❌ 无（G-4） |
| ApprovalPolicy | 审批策略可组合、可预设 | ⚠️ 有权限事件流，无组合策略层 |
| 子代理体系 | 10 provider 运行时分发 + 委托工具 | ✅ 已实现（AgentMode + SubAgentOrchestrator） |
| Skill 体系 | skill service + catalog + loader | ✅ 已实现（`skills/loader.py` 140 行） |
| **Compaction** | compaction-basic + tool-result-pruner（token 管理） | ⚠️ 有但未 token 化（G-1） |
| Native Landlock | OS 级文件访问限制 | ❌ 无（远期 P2） |

### 1.2 OpenCode 最新版关键架构

| 能力 | 要点 | CScode 现状（核查） |
|---|---|---|
| System Context 代数 | ContextSource + Registry + Epoch + Snapshot + Unavailable | ✅ 已实现（`core/system_context/` + `core/context_epoch.py`） |
| SessionInput admit | 幂等入口 + durable PromptAdmitted | ✅ 已实现（`schema/session_input.py` + STEER/QUEUE） |
| Runner 状态机 | Idle/Running/Shell/ShellThenRun + cancel | ✅ 已实现（`core/runner.py`） |
| EventV2 双表 | commit 原子 + /sync/replay + versionedType | ✅ 已实现（EventStore 原子 + scan_events_global 补拉） |
| Tool settle 管线 | decode→execute→encode→structured→toModelOutput | ✅ 已实现（`tools2/registry.py` materialize→settle） |
| **ToolResultValue** | 判别联合 `{json,text,error,content}` + providerExecuted | ❌ 缺（G-3） |
| LLM 错误代数 | 10 枚举 + retryable + ToolFailure≠defect | ✅ 已实现（`schema/errors.py`） |
| **Compaction** | Token.estimate + 序列化 + head/recent + LLM 摘要 | ⚠️ 有但未 token 化（G-1） |
| Permission 事件 | asked/replied + once/always/reject + 队列查询 | ⚠️ 有 ALLOW/DENY，缺三态 + 队列 API（G-7） |
| Agent modes | build/plan/subagent + Tab | ✅ 已实现（`core/agent/`） |
| Plugin v2 | Registration/Hooks/Integration/TuiPlugin | ✅ 已实现（`plugins/sdk.py` + `server/integration.py`） |
| **codemode** | JS 子集解释器 + 工具树 + 预算 + 诊断代数 | ❌ 无（G-4） |
| TUI 插件化 | Ink + 命令面板系统化 + 主题后处理 | ⚠️ Textual 自研未插件化（G-6） |
| **SDK 生成** | 67 HeyApiClient + OpenAPI | ⚠️ 前端手写 api.ts（G-8） |
| ACP 服务器 | session/load/resume/fork/prompt/cancel | ⚠️ 仅 93 行协议定义（G-5） |

### 1.3 三方交叉结论

**架构级共识（两个参考系都强调，CScode 已实现）**：事件溯源 + 投影、错误代数、工具 settle 管线、上下文代数、Agent modes、Plugin 体系。

**真实差距（两个参考系都强调，CScode 缺失或半实现）**：
1. **Compaction token 化**（dsh compaction-basic + OpenCode Token.estimate/序列化）——CScode 字符数 + 固定文本（G-1）
2. **沙箱**（dsh OS 沙箱链 + OpenCode codemode 解释器）——CScode 皆无（G-4）
3. **工具结果判别联合**（OpenCode ToolResultValue + providerExecuted）——CScode 简单 dataclass（G-3）
4. **ACP 互操作**（OpenCode acp + dsh 子代理）——CScode 仅协议定义（G-5）

---

## 2. 差距总览（G-1..G-9）

| # | 差距 | 现状证据 | 参考 | 等级 | 优先级 |
|---|---|---|---|---|---|
| G-1 | Compaction 未 token 化、SUMMARIZE 未实现 | `server/compactor.py` 固定文本；`core/compression.py` 字符数（100k chars）+ `logger.warning("not yet implemented")` | OpenCode §2.7 + dsh §14 | 半实现 | **P0** |
| G-2 | TruncateTool 是 stub | `tools2/truncate.py` execute 注释 "In a real implementation this would interact with the conversation store" | OpenCode §2.5 | 半实现 | **P0** |
| G-3 | ToolResult 无判别联合 | `tools2/base.py` 仅 success/data/error/tool_call_id/metadata | OpenCode §2.5 | 未实现 | **P0** |
| G-4 | 无任何执行沙箱 | `core/container.py` 是 DI 容器（ServiceContainer），无 run_code/sandbox | OpenCode §2.11 + dsh §18 | 未实现 | **P0** |
| G-5 | ACP 仅 93 行协议定义 | `acp/protocol.py` 无服务器端点 | OpenCode §2.9 | 半实现 | P1 |
| G-6 | TUI 未插件化 | `tui/app.py` 无 plugin 引用（rg 零命中） | OpenCode §2.12 | 未实现 | P1 |
| G-7 | Permission 无三态 + 队列查询 | `core/permission_v2.py` 仅 ALLOW/DENY | OpenCode §2.8 | 半实现 | P1 |
| G-8 | 前端 API 手写非生成 | `web/src/lib/api.ts` 手写 REST | OpenCode §2.13 | 未实现 | P2 |
| G-9 | 前端 sync 竞态未显式处理 | SyncPanel 有拉取/推送，无 `sync.status==="complete"` 再 fork 保护 | OpenCode §2.12 | 未实现 | P2 |

---

## 3. 设计原则

1. **分层独立**：Schema → LLM → Core → App，禁止跨层 import（CScode AGENTS.md 既有规则）
2. **TDD 先行**：每个差距先写契约测试（序列化格式、判别联合、截断语义、沙箱诊断），再写实现
3. **Ratchet**：每次修复的边界情况 → AGENTS.md 规则 + 回归测试
4. **最小迁移**：只补真实差距，不为对标而对标；半实现能力就地增强，不推倒重来
5. **兼容优先**：所有已有测试全通过（177 个文件），CLI/API 行为不变
6. **验证门禁**：`pytest tests/ && mypy src/ && ruff check src/` 全绿才算完成

---

## 4. P0 规格（架构级，4 项）

### 4.1 G-1: Compaction token 化 + LLM 摘要

**目标**：从「字符数阈值 + 固定文本占位」升级为「token 估算 + OpenCode 序列化规则 + head/recent 切分 + LLM 摘要」，对齐 OpenCode §2.7 与 dsh compaction-basic。

#### 4.1.1 现状（证据）

- `src/cscode/core/compression.py`：`ContextCompressor.threshold = 100_000`（**字符数**）；`SUMMARIZE` 分支仅 `logger.warning("SUMMARIZE strategy not yet implemented, falling back to TRUNCATE")`。
- `src/cscode/server/compactor.py`：snapshot 固定为 `"Previous context with N messages has been compacted."`，无 token 概念。

#### 4.1.2 目标架构

```
src/cscode/core/token_estimate.py   # 新增：Token.estimate 近似实现
src/cscode/core/compression.py      # 改造：token 阈值 + 序列化规则 + head/recent 切分
src/cscode/server/compactor.py      # 改造：LLM 摘要生成（SUMMARIZE 落地，失败回退 TRUNCATE）
tests/test_token_estimate.py        # 新增
tests/test_compression.py           # 改造：锁定序列化格式
tests/test_compression_integration.py  # 改造：LLM 摘要集成
```

#### 4.1.3 接口定义

```python
# token_estimate.py
def estimate_tokens(text: str) -> int:
    """OpenCode 兼容的 token 估算：CJK≈1 token/char，ASCII≈4 chars/token。
    不引入重型 tokenizer 依赖；文档锁定近似精度。"""

# compression.py — 常量对齐 OpenCode
DEFAULT_BUFFER_TOKENS: int = 20_000      # 触发压缩的缓冲阈值
DEFAULT_KEEP_TOKENS: int = 8_000         # 保留的 recent 段 token 数
TOOL_OUTPUT_MAX_CHARS: int = 2_000       # 工具输出截断上限
SUMMARY_OUTPUT_TOKENS: int = 4_096       # 摘要输出预算

# 序列化规则（单测锁定，逐字符比对）
#   user      → "[User]: text" + "[Attached mime: name]"
#   assistant → "[Assistant]: text" / "[Assistant reasoning]" / "[Assistant tool call]: name(input)"
#   tool      → "[Tool result]: truncated" / "[Tool error]: message"
#   system    → "[System update]"
#   synthetic → "[Synthetic context]"
#   shell     → "[Shell]: command\noutput"

class ContextCompressor:
    def __init__(self, buffer_tokens: int = DEFAULT_BUFFER_TOKENS,
                 keep_tokens: int = DEFAULT_KEEP_TOKENS,
                 strategy: CompressionStrategy = CompressionStrategy.SUMMARIZE): ...

    def needs_compression(self, messages: list[Message]) -> bool: ...
        # 改为 sum(estimate_tokens) > buffer_tokens

    def compress(self, messages: list[Message]) -> list[Message]:
        # 从尾部累积 token 切出 head（压缩段）与 recent（保留段）
        # TRUNCATE: 丢弃 head，插入压缩说明
        # SUMMARIZE: 将 head 序列化后交给 LLM 摘要，插入摘要消息

# compactor.py — LLM 摘要落地
async def _summarize(self, serialized_head: str, llm) -> str:
    """摘要 prompt：'Here is the conversation so far:\n\n<conversation>...</conversation>'
    输出受 SUMMARY_OUTPUT_TOKENS 约束；LLM 调用失败 → logger.exception + 回退固定文本。
    禁止静默吞错（AGENTS.md Ratchet）。"""
```

#### 4.1.4 验收标准

1. `needs_compression` 基于 token 估算而非字符数（测试：构造 5k token 中文消息触发，同长 ASCII 不触发）
2. 序列化格式与上表逐字符一致（契约测试锁定）
3. `compress()` 返回段满足 `sum(estimate_tokens(recent)) <= keep_tokens`
4. SUMMARIZE 在 mock LLM 下产出摘要消息；LLM 抛错时回退 TRUNCATE 且 `logger.exception()` 有记录
5. `Compactor.compact` 的 snapshot 在无 LLM 时保持兼容格式，有 LLM 时为真实摘要
6. 已有 `test_compression.py` / `test_compression_integration.py` 全通过（行为变化点更新断言）

### 4.2 G-2: TruncateTool 接入会话存储

**目标**：从返回假数据的 stub 变为真实调用 Compactor/EventStore 的工具，对齐 OpenCode `Truncate` 服务语义。

#### 4.2.1 现状（证据）

- `src/cscode/tools2/truncate.py`：`execute()` 直接 `return ToolResult(success=True, data=TruncateOutput(truncated=True, tokens_freed=input.max_tokens, ...))`——注释自认 "In a real implementation this would interact with the conversation store"。

#### 4.2.2 目标架构

```
src/cscode/tools2/truncate.py   # 改造：注入 Compactor + EventStore 依赖
tests/test_tools2_new.py        # 改造：真实截断语义
```

#### 4.2.3 接口定义

```python
class TruncateTool(Tool[TruncateInput, TruncateOutput]):
    # 新增依赖注入：构造函数接收 (compactor: Compactor, event_store: EventStore)
    async def execute(self, input: TruncateInput) -> ToolResult[TruncateOutput]:
        # 1. 读当前 session 事件，估算 token
        # 2. 调用 compactor.compact(session_id, system_prompt) → baseline_seq
        # 3. tokens_freed = 压缩前估算 - 压缩后估算（真实差值）
        # 4. remaining_tokens = 压缩后估算
        # 5. 失败路径：ToolFailure（raise）而非假 success
```

#### 4.2.4 验收标准

1. 调用后 `context_epochs` 表新增一行 epoch（baseline_seq 正确）
2. `tokens_freed` / `remaining_tokens` 反映真实 token 差值，非输入值原样返回
3. session 不存在 / 无事件 → 返回 `success=False` + 明确 error，不抛异常
4. `tests/test_tools2_new.py` 用真实 EventStore + in-memory DB 验证（复用 `tests/test_container.py` 模式）

### 4.3 G-3: ToolResult 判别联合 + providerExecuted

**目标**：`ToolResult` 从简单 dataclass 升级为判别联合 + `ToolOutput{structured, content}` + `providerExecuted`，对齐 OpenCode §2.5 ToolResultValue。

#### 4.3.1 现状（证据）

- `src/cscode/tools2/base.py`（92 行）：`ToolResult` 仅 `success/data/error/tool_call_id/metadata`；`data: OutputT | None` 直接承载结果。

#### 4.3.2 目标架构

```
src/cscode/schema/tool_result.py   # 新增：ToolResultValue 判别联合 + ToolOutput
src/cscode/tools2/base.py          # 改造：ToolResult 改用判别联合
src/cscode/schema/messages.py      # 改造：ToolCallPart/ToolResultPart 增补 providerExecuted/cache/metadata
src/cscode/llm/cache_policy.py     # 复用：CacheHint 挂到 ToolResultPart
tests/test_tool_result.py          # 新增：判别联合构造/序列化
tests/test_tools2_contract.py      # 改造：35 个工具迁移后契约
```

#### 4.3.3 接口定义

```python
# schema/tool_result.py
@dataclass
class ToolResultValue:
    """OpenCode ToolResultValue 判别联合。"""
    kind: Literal["json", "text", "error", "content"]
    json: Any | None = None
    text: str | None = None
    error: str | None = None
    content: list[ContentBlock] | None = None

@dataclass
class ToolOutput:
    """工具执行的结构化输出。"""
    structured: dict[str, Any] | None = None
    content: list[ContentBlock] | None = None

# tools2/base.py — ToolResult 兼容升级
@dataclass
class ToolResult(Generic[OutputT]):
    success: bool
    data: OutputT | None = None          # 保留：Pydantic 结构化输出
    value: ToolResultValue | None = None # 新增：判别联合（text/json/error/content）
    error: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    provider_executed: bool = False      # 新增：provider 预执行标记（Anthropic computer use）

# schema/messages.py — ToolResultPart 增补
@dataclass
class ToolResultPart:
    tool_call_id: str
    output: ToolOutput
    provider_executed: bool = False
    cache: CacheHint | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

#### 4.3.4 验收标准

1. `ToolResultValue` 四种 kind 可构造、可序列化（测试锁定 JSON 形状）
2. 35 个工具迁移后 `mypy src/` 严格模式通过（无 `Any` 泄漏）
3. `ToolResultPart` 携带 `provider_executed` / `cache` 时，序列化进消息不破坏既有会话数据模型（`Event("agg", 1, "type", data, t)` 位置参数兼容）
4. 旧 `ToolResult.data` 路径全部保留（向后兼容），新增 `value` 为可选

### 4.4 G-4: 受限执行沙箱（轻量）

**目标**：从「无任何沙箱」到「受限执行」——先评估实现路线，落地一个可安全执行模型生成脚本的轻量沙箱，对齐 OpenCode codemode（§2.11）思想与 dsh 沙箱（§18）的分层理念。

#### 4.4.1 现状（证据）

- `src/cscode/core/container.py`：`ServiceContainer` 是**依赖注入容器**（register/get/factory），无任何代码执行能力；全文无 `run_code`/`sandbox`/`subprocess` 执行入口。

#### 4.4.2 实现路线评估（决策点）

| 路线 | 成本 | 安全边界 | 适用场景 | 建议 |
|---|---|---|---|---|
| A. Python 子集解释器（仿 codemode） | 高（词法/语法/作用域全自研） | 最强（无子进程） | 模型生成小型脚本 | 远期（P2-1） |
| B. 受限 subprocess runner（RLIMIT + timeout + 资源限制） | 低（复用 stdlib） | 强（OS 级隔离 + 资源限制） | **本期（P0）** | ✅ 推荐 |
| C. OS 沙箱（Landlock/Seatbelt） | 中（平台绑定） | 最强（文件级） | 生产加固 | 远期（P2-2） |

**决策**：P0 落地路线 B（受限 subprocess runner + 执行预算 + 诊断代数），A/C 入远期路线图。

#### 4.4.3 目标架构

```
src/cscode/sandbox/__init__.py     # 导出
src/cscode/sandbox/runner.py       # SandboxRunner：受限 subprocess 执行
src/cscode/sandbox/limits.py       # ExecutionLimits（timeout_ms/max_output_bytes）
src/cscode/sandbox/diagnostics.py  # Diagnostic 代数（诊断种类 + location + suggestions）
src/cscode/sandbox/result.py       # SandboxResult 双态（Success/Failure，失败即数据非异常）
tests/test_sandbox.py              # 新增：超时/超输出/非法脚本/成功路径
```

#### 4.4.4 接口定义

```python
# limits.py
@dataclass
class ExecutionLimits:
    timeout_ms: int = 5_000
    max_output_bytes: int = 1_000_000

# diagnostics.py — 对齐 OpenCode DiagnosticKind（裁剪为 Python subprocess 场景）
class DiagnosticKind(str, Enum):
    TIMEOUT_EXCEEDED = "timeout_exceeded"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    EXECUTION_FAILURE = "execution_failure"     # 非零退出 / 启动失败
    INTERNAL_ERROR = "internal_error"

@dataclass
class Diagnostic:
    kind: DiagnosticKind
    message: str
    location: str | None = None
    suggestions: list[str] = field(default_factory=list)

# result.py — 失败是数据不是异常
@dataclass
class SandboxSuccess:
    ok: Literal[True] = True
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    truncated: bool = False

@dataclass
class SandboxFailure:
    ok: Literal[False] = False
    error: Diagnostic = ...  # 必填

SandboxResult = SandboxSuccess | SandboxFailure

# runner.py
class SandboxRunner:
    def __init__(self, limits: ExecutionLimits, workdir: str | None = None): ...
    async def run(self, script: str, argv: list[str] | None = None) -> SandboxResult:
        """subprocess.run 受限执行：
        - 强制 timeout（超时 → TIMEOUT_EXCEEDED + kill）
        - 输出超限截断（→ OUTPUT_LIMIT_EXCEEDED 或 truncated=True）
        - 非零退出 → EXECUTION_FAILURE（携带 stderr 摘要）
        - 禁止 shell=True；白名单解释器（如 sys.executable -I）；注入临时 workdir
        """
```

#### 4.4.5 验收标准

1. 超时脚本（`time.sleep(10)`）→ `TIMEOUT_EXCEEDED` 且子进程被 kill（测试 < 2s 返回）
2. 输出超限脚本（打印 2MB）→ 截断或 `OUTPUT_LIMIT_EXCEEDED`
3. 非法脚本（语法错误）→ `EXECUTION_FAILURE` 携带 stderr 摘要
4. `SandboxResult` 为判别联合——调用方必须处理双态（mypy exhaustive check 通过）
5. 成功脚本返回 stdout/exit_code；`truncated` 标志正确
6. 沙箱不依赖网络/环境变量（`-I` 隔离模式），测试隔离可复现

---

## 5. P1 规格（能力级，3 项）

### 5.1 G-5: ACP 服务器完整化

**目标**：从 93 行协议定义升级为可用的 ACP 服务器（session/loadSession/resumeSession/forkSession/prompt/cancel），对齐 OpenCode §2.9。

#### 5.1.1 现状（证据）

- `src/cscode/acp/protocol.py`（93 行）：只有 ACP 协议类型定义，无服务器实现、无端点、无 SessionRunner 复用。

#### 5.1.2 目标架构

```
src/cscode/acp/server.py      # 新增：ACPServer — 协议端点 → SessionRunner 桥接
src/cscode/acp/__init__.py    # 改造：导出 ACPServer
tests/test_acp_server.py      # 新增：session 生命周期 + prompt 流转
```

#### 5.1.3 接口定义

```python
class ACPServer:
    def __init__(self, runner: SessionRunner, session_factory): ...
    async def handle(self, request: ACPRequest) -> ACPResponse:
        # 端点：session/load_session/resume_session/fork_session/prompt/cancel
        # 全部复用 SessionRunner（不新造执行路径）
```

#### 5.1.4 验收标准

1. `session` 创建 → `prompt` 执行 → `load_session` 恢复 → `cancel` 中断全链路可用
2. `fork_session` 生成新 session 且不污染原 session（事件隔离）
3. 错误响应携带结构化错误（复用 `schema/errors.py` 语义），不抛裸异常
4. 复用 SessionRunner 已有能力验证桥接正确性（`tests/test_acp.py` 协议 + `tests/test_execution.py` 执行生命周期，实测 `tests/test_runner.py` 不存在，以这两个文件为准）

### 5.2 G-6: TUI 插件化

**目标**：Textual TUI 从自研单体变为可插件化，对齐 OpenCode §2.12 TuiPlugin 的命令面板系统化。

#### 5.2.1 现状（证据）

- `src/cscode/tui/`：`app.py` + `screens/` + `themes.py` + `autocomplete.py`；`rg "plugin" src/cscode/tui/*.py` 零命中——TUI 无插件接入点。

#### 5.2.2 目标架构

```
src/cscode/tui/plugin_api.py   # 新增：TuiPluginAPI — 暴露 app/screens/command/theme/kv 到插件
src/cscode/tui/commands.py     # 新增：命令面板系统化（session/model/agent/theme 命令注册表）
src/cscode/tui/app.py          # 改造：挂载插件加载点 + 命令注册
tests/test_tui_plugin_api.py   # 新增
```

#### 5.2.3 接口定义

```python
class TuiPluginAPI:
    """对齐 OpenCode TuiPlugin API 的 Python 版（裁剪）：
    app / command(register) / theme(install/set) / kv(state) / screens(navigate)
    """
    def register_command(self, name: str, handler: Callable[[str], Awaitable[None]],
                         category: str = "general", aliases: list[str] | None = None) -> None: ...
    def navigate(self, screen: str, params: dict | None = None) -> None: ...
    def theme_set(self, name: str) -> None: ...
```

#### 5.2.4 验收标准

1. 插件（Python 包）可注册命令 → 命令面板出现并可触发
2. 命令注册表按类别分组（session/model/agent/theme），与现有 TUI 快捷键共存
3. 插件生命周期：activate/deactivate 干净，无残留状态
4. 现有 `tests/test_tui_*.py` 全通过（`tui-session-list` / `tui-session-detail` 等既有 spec 行为不变）

### 5.3 G-7: Permission 三态 + 待处理队列

**目标**：从 ALLOW/DENY 二态升级为 `once/always/reject` 三态 + 待处理请求队列查询，对齐 OpenCode §2.8。

#### 5.3.1 现状（证据）【迭代 4+5 已实现，以下为落地后状态】

- `src/cscode/core/permission_v2.py`（~570 行）：已有完整 `Rule`/`RuleEffect`/`Wildcard`/`PermissionV2.evaluate`/`SavedRules`（global+session CRUD）体系 + G-7 新增 `ReplyMode`（once/always/reject 三态）+ `SessionPermission` 待处理队列（`ask`/`reply`/`list_pending`）+ `is_allowed(remember=...)`。`reply(ALWAYS)` 持久化 ALLOW 规则、`reply(REJECT)` 持久化 DENY 规则，跨 session reload 生效。
- `src/cscode/core/events.py`：`PermissionAskedEvent` / `PermissionRepliedEvent` 已存在（事件流底座已有）。
- `src/cscode/server/routes/permissions.py`：G-7 收尾已暴露 `GET /api/permission/request`（队列查询）+ `POST /api/permission/request/{id}/reply`（三态决议）；`state.permission_manager` 惰性共享实例。spec 偏差 #5 已消除。

#### 5.3.2 目标架构【已实现】

```
src/cscode/core/permission_v2.py   # 已改造：ReplyMode 三态 + SessionPermission 队列 + always 记忆
src/cscode/server/routes/permissions.py  # 已暴露：GET /api/permission/request + POST /reply
tests/test_permission_tristate.py  # 新增：三态语义 + 队列（9 测试）
tests/test_permissions_api.py      # 新增：REST 队列查询（4 测试）
```

#### 5.3.3 接口定义

```python
class ReplyMode(str, Enum):
    ONCE = "once"       # 本次允许
    ALWAYS = "always"   # 记住，之后自动允许（持久化）
    REJECT = "reject"   # 拒绝

# PermissionV2 新增
async def reply(self, request_id: str, mode: ReplyMode) -> bool: ...
async def list_pending(self, session_id: str | None = None) -> list[PermissionRequest]: ...
async def is_allowed(self, session_id: str, action: str, resource: str,
                     remember: bool = False) -> bool: ...
    # remember=True 时 ALWAYS 决策写入持久化规则表
```

#### 5.3.4 验收标准

1. `once` 只放行本次；`always` 写入持久化规则表，之后 `is_allowed` 自动通过；`reject` 拒绝并记录
2. `GET /api/permission/request` 返回待处理请求列表（含 session_id/action/resource/request_id）
3. `always` 规则在 session 重载后仍然生效（跨 session load 持久化，复用 EventStore 模式）
4. 已有 permission 测试全通过，`APPLICATION_TOOLS` 只读集合行为不变

---

## 6. P2 规格（增强级，按需）

### 6.1 G-8: SDK 生成客户端

**目标**：前端手写 `api.ts` → OpenAPI 生成 client，对齐 OpenCode §2.13。

- **目标文件**：`web/src/lib/api/generated/`（生成物）+ `scripts/gen-api.sh`（生成脚本）
- **验收**：`GET /openapi.json` 端点存在 → 生成 client → `web/src/lib/api.ts` 改为调用生成 client 门面；手写逻辑（错误处理/重试）保留在门面层

#### 6.1.1 现状核查（实测证据，2026-08-20）

- `GET /openapi.json`：FastAPI 默认 schema 可生成，**74 个路径**、18 个 components schemas。
- **schema 覆盖缺口**：`/api/session`（单数别名）等端点不在 schema（`/api/sessions` 复数在）——直接生成 client 会丢失前端实际调用的单数别名。
- **类型缺口**：多数端点返回 `dict[str, Any]`（无 response_model），OpenAPI 生成类型为 `any`，无法替代 `stores/useSessionStore.ts` / `useConfigStore.ts` 的手写 `Session`/`Message`/`Config` 类型。
- 前端 `api.ts`：110 行、7 处 import（Composer/Sidebar/ProjectItem/ThreadsHeader/CommandPalette/SettingsPanel/useChat）、内含重试/错误处理封装。

#### 6.1.2 设计决策（路线选型）

**不采用**全量 OpenAPI generator（openapi-typescript 等）——74 端点中大量 `dict[str, Any]` 会产出 `any` 类型，违背「无 Any 泄漏」原则，且丢失单数别名端点。

**采用**轻量生成器路线：
1. `scripts/gen-api.sh`：从运行中的后端 `GET /openapi.json` 拉取 schema
2. 生成 `web/src/lib/api/generated/endpoints.ts`——**端点清单 + 方法名 + 路径**（`Record<MethodName, { path, method, needsBody }>`），类型安全（路径模板字面量）
3. `api.ts` 门面改造：保留手写类型（`Session`/`Message`/`Config`）+ 重试/错误逻辑，**请求路径改为从 generated 端点表解析**——路径改动后 tsc 编译失败（类型错误），实现「路径漂移检测」
4. 单数别名端点**手工补录**进端点表（`/api/session` 等），生成脚本不覆盖手写补录段

#### 6.1.3 接口定义

```typescript
// web/src/lib/api/generated/endpoints.ts（生成物 + 手工补录段）
export interface ApiEndpoint {
  path: string;          // 路径模板，如 "/api/sessions/{session_id}"
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  needsBody: boolean;
}
export const ENDPOINTS = {
  listSessions: { path: '/api/sessions', method: 'GET', needsBody: false },
  // ... 74 个生成端点
  // ── 手工补录段（生成脚本不覆盖）──
  listSessionAlias: { path: '/api/session', method: 'GET', needsBody: false },
  // ...
} as const satisfies Record<string, ApiEndpoint>;

// api.ts 门面（改造后）
import { ENDPOINTS } from './api/generated/endpoints';
export const api = {
  session: {
    list: () => request<Session[]>(ENDPOINTS.listSessionAlias.path),
    // ...
  },
  // 重试/错误处理逻辑不变
};
```

#### 6.1.4 验收标准

1. `GET /openapi.json` 可访问（后端默认 FastAPI schema）
2. `scripts/gen-api.sh` 生成 `generated/endpoints.ts`（74 端点 + 方法名映射），可重复执行且幂等
3. `api.ts` 全部请求路径改为从 `ENDPOINTS` 解析（rg 验证 `api.ts` 内无硬编码 `/api/` 路径字面量）
4. 单数别名端点（`/api/session`）在补录段保留，生成脚本重新执行不覆盖
5. `npx tsc --noEmit` 通过 + `npm test` 全过（既有 jest 测试不破坏）
6. 路径漂移检测：若后端某路径删除，`endpoints.ts` 手工补录段仍在 → 编译通过但运行时 404；新增路径 → 重新生成后出现

### 6.2 G-9: 前端 sync 竞态处理

**目标**：对齐 OpenCode §2.12 的 `sync.status === "complete"` 语义——SyncPanel 建立 sync 状态机，push/pull 串行化，消除并发竞态。

#### 6.2.1 现状核查（实测证据，2026-08-20）

- `web/src/components/SyncPanel.tsx`（124 行）：纯展示组件——`/api/sync/events`（GET 拉取）+ `/api/sync/push`（POST 推送）两个按钮，**无状态机、无串行保护**。
- **无 `useSync.ts` hook**、**前端无任何 fork/session 分支功能**（`rg fork|duplicate|clone|branch` 零命中）——spec 原文的"fork 前等待 sync complete"中 fork 在前端不存在，需调整为状态机基础设施。
- 后端 `/api/sync/events` + `/api/sync/push` 存在（`server/app.py:2542,2562`），**无 status 概念**——只返回增量事件（id > after_id）。
- **真实竞态**：Push 与 Refresh 按钮无并发保护，快速连点会并发请求；拉取结果应用无 `complete` 追踪。

#### 6.2.2 设计决策

1. 新增 `useSync.ts` hook：暴露 `syncStatus: 'idle' | 'syncing' | 'complete' | 'error'` + `lastSyncedAt` + `push()` / `refresh()`（内部串行化：busy 期间调用排队/忽略）
2. SyncPanel 改造：按钮 disabled 绑定 `syncing`；状态机 `complete` 时显示最近同步时间——为未来 fork 功能提供 `sync.status === 'complete'` 检查点
3. **串行化**：hook 内部用 in-flight promise 锁，连点不产生并发请求
4. 竞态测试：模拟 push 进行中点击 refresh → 请求不并发（单次 fetch 调用）

#### 6.2.3 接口定义

```typescript
// web/src/hooks/useSync.ts（新增）
export type SyncStatus = 'idle' | 'syncing' | 'complete' | 'error';

export interface UseSyncResult {
  status: SyncStatus;
  lastSyncedAt: number | null;
  events: SyncEvent[];
  push: () => Promise<void>;   // 串行化：busy 时忽略
  refresh: () => Promise<void>; // 串行化：busy 时忽略
}
```

#### 6.2.4 验收标准

1. `push()` 执行期间状态为 `syncing`，完成后 `complete` + 刷新事件列表
2. `refresh()` 执行期间状态为 `syncing`，成功后 `complete`
3. **串行化**：busy 期间重复调用 `push()`/`refresh()` 被忽略（单测：mock fetch 计数 = 1）
4. 失败时状态为 `error` + 保留最后成功时间
5. SyncPanel 按钮 disabled 绑定状态；`npx tsc --noEmit` + `npm test` 全过

### 6.3 远期（P2-2/P2-3 合并项）

| 项 | 说明 | 依赖 |
|---|---|---|
| Python 子集解释器（G-4 路线 A） | 仿 codemode 解释执行，无子进程 | P0-4 沙箱底座 |
| OS 沙箱（G-4 路线 C） | Landlock/Seatbelt 文件级限制 | dsh §18 |
| Capability Seams 文档化 | 三角色决策表写入 `docs/` | 无 |

### 6.4 G-10: Capability Seams 文档化（迭代 9）

**目标**：把 dsh §6 的三角色模型（Service Definition / Provider / Consumer）映射到 CScode 真实代码，产出 `docs/capability-seams.md`——"新行为放哪里"决策表，每一项引用真实源码路径。

#### 6.4.1 现状核查（实测证据，2026-08-20）

CScode 已具备的"缝"及其实证：

| 缝 | Service Definition（接口） | Service Provider（实现） | Consumer（使用） |
|---|---|---|---|
| 沙箱 | `sandbox/runner.py` `SandboxRunner.run()` | `sandbox/limits.py` ExecutionLimits + `runner.py` 超时/输出限制 | `tools2/bash.py` spawn 前包装 argv |
| 工具系统 | `tools2/registry.py` `ToolRegistry.register()` | 22 个 `tools2/*.py` 工具 | `llm/tool_runtime.py` + `core/tool_registry.py` |
| Agent preset | `core/agent/registry.py` | `core/agent/base.py` + `build.py` + `factory.py` | `app/` agent 工厂 |
| TUI 命令 | `tui/commands.py` `CommandRegistry.register()` | `tui/plugin_api.py` TuiPluginAPI | `server/app.py` _handle_session_command |
| 后台任务 | `core/background_job.py` JobStore | `core/background_job.py` Job 模型 | TUI/前端任务面板 |
| 事件/权限 | `core/events.py` PermissionAsked/RepliedEvent | `core/permission_v2.py` PermissionV2 | `tools2/` 工具权限确认 |
| Provider | `providers/base.py` | 16 个 `providers/*.py`（anthropic/azure/gemini/ollama/openai/openrouter/grok/mistral/nvidia/vertex/xai/bedrock/cohere/copilot/perplexity…） | `llm/route.py` + `llm/client.py` |
| 文件系统 | `core/fs_protected.py` ProtectedPaths + `core/fs_ignore.py` | `core/fs_watcher.py` | `tools2/read.py`/`write.py`/`grep.py`/`glob.py` |
| 终端 | `tools2/pty.py` PTYAction/PTYInput/PTYCreateOutput | `tools2/pty.py` PTY 后端 | TUI 终端面板 |
| LSP | `lsp/manager.py` LSPManager | `lsp/manager.py` LSPClient | `tools2/lsp.py` |
| Sub-agent | `core/sub_agent.py` SubAgentOrchestrator | `core/agent/subagent.py` | `core/runner.py` 会话调度 |
| 同步 | `core/sync.py` SyncEngine | `server/app.py:2542,2562` /api/sync/* 端点 | `web/src/hooks/useSync.ts`（G-9） |

**关键发现（Ratchet 记录）**：
1. **CScode 无 session fork**（`rg fork` 前后端零命中）——dsh §6.3 的 `Fork 活跃 session` 行不适用，标注为"预留（依赖 G-9 sync.status 检查点）"
2. **16 个 provider**（dsh 分析时 7 个）——已扩至 16，决策表按实际列
3. **Permission 三态**（once/always/reject，G-7 交付）——事件缝的 provider 侧已就绪

#### 6.4.2 设计决策

1. 文档结构：三角色模型说明（映射 dsh §6.1）→ 决策表（映射 dsh §6.3）→ 缝清单（上表）→ 预留项
2. 决策表每行**必须引用真实源码路径**（Ratchet：禁止凭假设写文档）
3. 与 dsh 的差异显式标注（如 Fork 行标注"预留"）
4. 文档放置：`docs/capability-seams.md`（dsh 是 opencode 分析，本文件是 CScode 落地版）

#### 6.4.3 验收标准

1. `docs/capability-seams.md` 存在，含三角色模型 + 决策表 + 缝清单 + 预留项 4 节
2. 决策表 ≥ 10 行，每行 "目标 → 机制" 引用真实源码路径（`rg` 验证路径存在）
3. 缝清单每行 Definition/Provider/Consumer 三列均引用真实文件
4. 无 fork 项显式标注"预留"（不得虚构 fork 实现）
5. `docs/opencode-1to1-gap-analysis.md` 更新：对照本 spec 标注 G-1~G-9 已闭环的差距项（Compaction/Truncate/ToolResult/沙箱/ACP/Permission 三态/TUI 插件/OpenAPI 生成/sync 状态机）

---

### 6.5 G-11: Python 子集解释器（Route A，迭代 10-11）

**目标**：创建受限 Python 子集解释器——在父进程内解释执行模型生成的受限脚本，消除 subprocess 开销与隔离边界。

#### 6.5.1 现状核查（实测证据，2026-08-20）

- **当前执行方式**：`sandbox/runner.py` `SandboxRunner.run()` → `asyncio.create_subprocess_exec(sys.executable, "-I", script_path)`——subprocess 隔离（route B）
- **无解释器执行**：`rg "ast\.parse|exec\(|eval\(" src/cscode/sandbox/` 零命中——全文无 AST-walk 解释器
- **dsh §2.11 参考**：dsh 有 JS 子集解释器（自研，不跑子进程），含工具树 + 执行预算 + 诊断代数 + Result 双态
- **CScode 无等价物**：`core/container.py` 是 DI 容器（非沙箱），无 `run_code`/`subprocess`/`sandbox` 语义

#### 6.5.2 设计决策

1. **Python 子集定义**：限制为可 AST-walk 的子集——变量赋值、算术、条件、循环、函数定义、列表/字典操作、print。**禁止**：import、async、class 继承、with、try/except、exec/eval、文件 I/O、网络
2. **执行模型**：`compile()` → `ast.parse()` → 自定义 AST walker（`NodeVisitor` 子类）→ 执行。预算计数器（每步 +1，超限终止）
3. **工具调用**：通过 `tools_ns` 对象注入（`tools_ns.tool("bash", {"cmd": "ls"})`），调用经过权限检查
4. **诊断代数**：复用 `sandbox/diagnostics.py` DiagnosticKind（TIMEOUT_EXCEEDED/EXECUTION_FAILURE/...）
5. **Result 双态**：Success/Failure（与 SandboxRunner 输出兼容）
6. **执行预算**：`ExecutionLimits` 复用（timeout_ms/max_output_bytes）+ 新增 `max_steps`（AST 节点步数上限）

#### 6.5.3 接口定义

```python
# sandbox/interpreter.py（新增）
class PythonInterpreter:
    """解释执行受限 Python 子集，返回 SandboxResult。"""
    def __init__(self, limits: ExecutionLimits, tools_ns: dict[str, Any] | None = None): ...
    async def run(self, script: str, argv: list[str] | None = None) -> SandboxResult: ...
```

#### 6.5.4 验收标准

1. `PythonInterpreter.run()` 可执行：赋值/算术/条件/循环/函数/列表/字典/print——返回 `SandboxSuccess(stdout=...)`
2. 禁止操作（import/async/class/with/try/exec/eval/文件/网络）→ `SandboxFailure(DiagnosticKind.EXECUTION_FAILURE)`，脚本不执行
3. 执行预算：`max_steps=1000` 的循环在 1000 步后终止（`TIMEOUT_EXCEEDED`）
4. 工具调用：`tools_ns.tool("bash", {"cmd": "ls"})` 经过权限检查（复用 `core/permission_v2.py`）
5. 与 `SandboxRunner` 输出兼容：`SandboxResult` 类型不变
6. 性能基准：同等脚本下，解释器执行延迟 < subprocess 3x（消除进程创建开销）

#### 6.5.5 风险

| 风险 | 缓解 |
|------|------|
| Python AST 复杂度（30+ 节点类型） | 只实现子集（~15 节点类型），渐进扩展 |
| 执行性能（AST walk 比 bytecode 慢） | 预算步数限制 + 子集限制避免深循环 |
| 与现有工具调用语义不一致 | 复用 SandboxResult + PermissionV2 |

---

### 6.6 G-12: OS 沙箱（Route B，迭代 12）

**目标**：在 subprocess 隔离之上增加 OS 级文件系统访问限制——Landlock（Linux 5.13+）或 Seatbelt/App Sandbox（macOS）。

#### 6.6.1 现状核查（实测证据，2026-08-20）

- **当前沙箱**：`sandbox/runner.py` `SandboxRunner.run()` → subprocess 隔离（`-I` 模式 + 空环境 + 超时 + 输出上限）。**无 OS 级文件系统限制**
- **dsh §18 参考**：dsh 有 `@deepseek-ai/node-addon-landlock-run`（Rust node addon，Linux-only）——Landlock LSM 限制文件系统访问
- **macOS Seatbelt**：`docs/cscode-iteration-plan.md` 提到 "seatbelt"，但 macOS 10.14+ 已弃用 `sandbox-exec`；App Sandbox 需要 App Store 签名
- **Linux Landlock**：内核 5.13+（2021），无需 root，用户态 LSM——最可行方案

#### 6.6.2 设计决策

1. **平台策略**：Linux 用 Landlock（内核 LSM，无需 root）；macOS 暂不实现（Seatbelt 弃用 + App Sandbox 需签名）；Windows 暂不实现（需 AppContainer）
2. **集成点**：`SandboxRunner.run()` 在 `create_subprocess_exec` 前，调用 Landlock 限制子进程的文件系统访问（只读 bind + workspace-write）
3. **配置**：`ExecutionLimits` 新增 `allowed_read_paths: list[str]` + `allowed_write_paths: list[str]`（默认：脚本工作目录 + 系统只读路径）
4. **实现**：Python ctypes 绑定 Landlock 系统调用（`landlock_create_ruleset` / `landlock_add_rule` / `prctl(PR_SET_NO_NEW_PRIVS)`）
5. **降级**：Landlock 不可用时（旧内核/macOS）→ 回退到纯 subprocess 隔离（当前行为）

#### 6.6.3 接口定义

```python
# sandbox/landlock.py（新增，Linux-only）
def is_landlock_available() -> bool: ...
def apply_landlock_rules(allowed_read: list[str], allowed_write: list[str]) -> None: ...
```

```python
# sandbox/limits.py（扩展）
@dataclass
class ExecutionLimits:
    # 现有字段...
    allowed_read_paths: list[str] = field(default_factory=list)  # 新增
    allowed_write_paths: list[str] = field(default_factory=list)  # 新增
```

#### 6.6.4 验收标准

1. `is_landlock_available()` 在 Linux 5.13+ 返回 `True`；macOS/旧内核返回 `False`
2. `apply_landlock_rules(["/usr"], ["/tmp/sandbox"])` 后，子进程读 `/etc/passwd` 允许（只读），写 `/tmp/sandbox/file` 允许，写 `/etc/file` 拒绝（`EACCES`）
3. `SandboxRunner.run()` 在 Linux 上自动应用 Landlock（若内核支持）
4. Landlock 不可用时 → 回退到纯 subprocess（无行为变化）
5. 跨平台：macOS/Linux 测试均通过（macOS 跳过 Landlock 测试）

#### 6.6.5 风险

| 风险 | 缓解 |
|------|------|
| macOS Seatbelt 弃用 | 跳过 macOS，专注 Linux Landlock |
| Landlock 内核版本要求（5.13+） | `is_landlock_available()` 检测 + 降级 |
| ctypes 绑定系统调用复杂度 | 只实现 3 个系统调用（create_ruleset/add_rule/set_no_new_privs） |
| 文件路径白名单配置 | 默认值：脚本工作目录 + `/usr` 只读 + `/tmp` 写 |

---

## 7. 任务分解（迭代批次）

> 每个迭代 = DEFINE → PLAN → BUILD(TDD) → VERIFY → REVIEW，遵循 `docs/reimplementation-methodology.md`。

| 迭代 | 内容 | 依赖 | 验证门禁 |
|---|---|---|---|
| 迭代 1 | **G-1 Compaction token 化**（token_estimate + 序列化 + 切分 + 摘要） | 无 | `pytest tests/test_token_estimate.py tests/test_compression*.py` + mypy + ruff |
| 迭代 2 | **G-2 Truncate 接入** + **G-3 ToolResult 判别联合** | 迭代 1（Token.estimate 被 Truncate 复用） | `pytest tests/test_tools2_new.py tests/test_tool_result.py tests/test_tools2_contract.py` |
| 迭代 3 | **G-4 受限沙箱**（route B） | 无 | `pytest tests/test_sandbox.py`（超时/超限/非法/成功 4 路径） |
| 迭代 4 | **G-5 ACP 服务器** + **G-7 Permission 三态** | 迭代 2（ToolResult 判别联合被 ACP 复用） | `pytest tests/test_acp_server.py tests/test_permission_v2.py` |
| 迭代 5 | **G-6 TUI 插件化** | 无 | `pytest tests/test_tui_plugin_api.py` + 既有 TUI 测试 |
| 迭代 6+ | G-8 SDK 生成 → G-9 前端 sync 竞态 → 远期项 | 迭代 3（沙箱底座） | 前端 type-check + E2E |
| 迭代 9 | **G-10 Capability Seams 文档化** + gap-analysis 更新 | 无（纯文档） | `docs/capability-seams.md` 决策表路径 rg 验证 + gap-analysis 标注 |
| 迭代 10-11 | **G-11 Python 子集解释器**（Route A） | 无（独立） | `pytest tests/test_interpreter.py`（子集执行/禁止操作/预算/工具调用）+ mypy |
| 迭代 12 | **G-12 OS 沙箱**（Route B，Linux Landlock） | 迭代 3（沙箱底座） | `pytest tests/test_landlock.py`（可用性检测/规则应用/降级）+ Linux CI |

---

## 8. 全局验收标准

1. **测试**：`pytest tests/` 全通过（新增约 8 个测试文件，存量 177 个不受破坏）
2. **类型**：`mypy src/` 严格模式通过，无 `Any` 泄漏（沙箱判别联合 exhaustive）
3. **Lint**：`ruff check src/` 零告警
4. **兼容**：CLI（`cs chat` / `cs tui` / `cs server`）行为不变；既有 API 端点不破坏
5. **Ratchet**：每个迭代的边界情况 → AGENTS.md 规则 + 回归测试
6. **版本**：每批次完成按 AGENTS.md 版本号清单（7 处）统一 bump

---

## 9. 风险与依赖

| 风险 | 影响 | 缓解 |
|---|---|---|
| token 估算精度（无重型 tokenizer） | G-1 压缩时机偏差 | 文档锁定近似精度；阈值留 buffer；后续可换 tiktoken |
| SUMMARIZE 依赖 LLM 调用 | G-1 摘要失败会拖慢 compaction | 失败回退 TRUNCATE（现状骨架已有）+ `logger.exception()` |
| `tools2/base.py` 改动波及 35 工具 | G-3 回归风险 | 契约测试先行（`test_tools2_contract.py`）；`data` 路径向后兼容 |
| 沙箱 subprocess 逃逸 | G-4 安全 | `-I` 隔离模式 + timeout kill + 输出上限；远期 OS 沙箱加固 |
| ACP 与 SessionRunner 耦合 | G-5 执行路径分叉 | 只做桥接不新造执行路径 |
| 前端 sync 竞态难复现 | G-9 验证困难 | 模拟测试（reconcile 覆盖场景） |

---

## 10. 相关文档

- `docs/cscode-iteration-plan.md` — 迭代方案总览（v2 核查修正版）
- `docs/deepseek-harness-analysis.md` — dsh 全量分析（792 行）
- `docs/opencode-1to1-gap-analysis.md` — 旧版 opencode 对齐差距（需对照本 spec 更新）
- `openspec/specs/cscode-opencode-replication-p0.md` — 已完成的 P0 复刻 spec（本 spec 是其后续）
- `docs/reimplementation-methodology.md` — 迭代方法论
