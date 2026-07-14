# Phase 0: OpenCode 核心功能复刻 — Agent 系统 + Session 引擎 + Plugin v2

> 基于 OpenCode v1.17.18 源码深度对比分析（2026-07-13）
> 目标：3 个 P0 模块补齐，达到 OpenCode 核心功能 ~70% 覆盖率

---

## 1. 问题定义

### 1.1 当前差距

| 模块 | CScode 现有 | OpenCode 目标 | 差距 |
|------|-------------|---------------|------|
| **Agent 系统** | `SubAgentOrchestrator` 仅处理 `@tool:` 文本替换，无 mode 概念 | `agent.ts` — build/plan/subagent 三种 mode，Tab 切换，8 种内置 agent 类型 | ❌ 核心缺失 |
| **Session 引擎** | `SessionRunner.run()` + `SessionCoordinator` 基本状态机 | `SessionV2` + durable prompt admission + compaction + error recovery + interrupt | ⚠️ 部分有，缺高级特性 |
| **Plugin 系统** | `PluginLoader` 硬导入 Python 包，`SkillLoader` 加载 md 文件 | `plugin/v2/` — Effect 生命周期，50+ TUI hooks，tool/command/skill/provider 注册 | ❌ 架构级别缺失 |

### 1.2 根因

CScode 的现有代码是 OpenCode 的"骨架级"实现：
- Agent 系统：只有名字没有架构（`sub_agent.py` 只是工具调用包装）
- Session 引擎：核心 loop 硬编码在 `runner.py` 的 `run()` 方法中（被上层直接调用），无标准化执行管线
- Plugin 系统：只有 discovery 没有 lifecycle，无法扩展 TUI/CLI/Web 三层

### 1.3 范围边界

#### 属于本阶段 (P0)

| 模块 | 包含 |
|------|------|
| Agent 系统 | `AgentV2` 类层次、3 种 mode (build/plan/subagent)、mode 切换、system prompt 模板、Tab 管理 |
| Session 引擎 | `SessionExecution` 标准化管线、durable prompt admission、中断/恢复、RunState 管理 |
| Plugin 系统 v2 | `PluginHost` 生命周期、`PluginAPI` (TUI/CLI/Web)、tool/command/provider 注册、npm 发现 |

#### 不属于本阶段 (Phase 1+)

| 模块 | 规划 |
|------|------|
| ACP (Agent Connect Protocol) | Phase 1 |
| LSP 集成 | Phase 1 |
| SDK 生成 | Phase 1 |
| 快照/压缩 | Phase 1 |
| Console 云平台 | Phase 2 |
| Enterprise 门户 | Phase 2 |

### 1.4 验收标准

1. **Agent 系统**: `cs chat --mode plan` 启动 plan mode，`/mode build` 切换 mode，不同 mode 注入不同 system prompt 和 tool 白名单
2. **Session 引擎**: 多 session 并发执行不冲突，中断响应 < 2s，错误不会造成 session 状态损坏，prompt 先落盘再执行
3. **Plugin v2**: Python 包可作为插件注册 tool/command/provider，TUI/CLI/Web 层可接收插件注入的 UI 扩展
4. **测试**: 新增代码 `pytest tests/` 覆盖率 > 80%，`mypy src/` 严格模式通过
5. **兼容**: 所有已有测试全通过，已有 CLI 命令行为不变

---

## 2. 目标架构

### 2.1 Agent 系统

```
src/cscode/core/agent/
  __init__.py      # 导出
  base.py          # AgentV2 基类
  build.py         # BuildModeAgent (默认, 工具使用)
  plan.py          # PlanModeAgent (分步计划)
  subagent.py      # SubAgentModeAgent (子代理)
  factory.py       # AgentFactory — mode → agent 映射
  tab.py           # TabManager — 多 Tab 并发会话
  system_prompts.py # mode 对应的 system prompt 模板
```

**核心流程**:
```
User Input → AgentV2.run()
                │
        ┌───────┴───────┐
        │   mode check   │
        └───┬───┬───┬───┘
            │   │   │
       build  plan subagent
            │   │   │
        ┌───┘   │   └───┐
        ▼       ▼       ▼
   ToolLoop  PlanGen  Dispatch
        │       │       │
        └───────┴───────┘
                │
          SessionV2.prompt()
```

### 2.2 Session 引擎增强

```
src/cscode/core/
  session.py        # 增强: RunState + durable prompt
  coordinator.py    # 增强: 多 session 并发 + 中断
  runner.py         # 增强: 标准化 SessionExecution 管线
  execution.py      # 新增: SessionExecution — 标准化执行循环
```

**状态机扩展**:
```
         ┌────────────────────────────────────┐
         │                                    │
         ▼                                    │
    ┌────────┐  prompt()  ┌──────────┐  done  ┌──────────┐
    │  IDLE  │ ────────→  │ ADMITTED │ ─────→ │ RUNNING  │
    └────────┘            └──────────┘        └──────────┘
         ▲                      │                  │
         │                      │ error            │ interrupt
         │                      ▼                  ▼
         │                 ┌──────────┐     ┌──────────┐
         └─────────────────│  ERROR   │     │ STOPPING │
                           └──────────┘     └──────────┘
```

### 2.3 Plugin 系统 v2

```
src/cscode/core/plugin/
  __init__.py       # 导出
  host.py           # PluginHost — 生命周期管理器
  api.py            # PluginAPI — TUI/CLI/Web API 定义
  registry.py       # PluginRegistry — 插件注册表
  discovery.py      # 插件发现 (PyPI/git/本地)
  hooks.py          # Hook 点定义
```

**生命周期**:
```
┌─────────┐  discover  ┌──────────┐  load  ┌─────────┐  activate  ┌──────────┐
│ UNKNOWN │ ────────→  │ DISCOVER │ ─────→ │ LOADED  │ ────────→  │ ACTIVE   │
└─────────┘            └──────────┘        └─────────┘            └──────────┘
                                                                       │
                                                               deactivate
                                                                       │
                                                                       ▼
                                                                  ┌──────────┐
                                                                  │ INACTIVE │
                                                                  └──────────┘
```

---

## 3. 实现细节

### 3.1 Agent 系统

#### AgentV2 基类

```python
class AgentV2:
    mode: AgentMode  # BUILD | PLAN | SUBAGENT
    session: SessionV2
    tool_registry: ToolRegistryV2
    
    async def run(self, user_input: str) -> AsyncIterator[LLMEvent]:
        ...
    
    async def get_system_prompt(self) -> str:
        ...
    
    def get_allowed_tools(self) -> list[str]:
        ...
```

#### 三种 Mode

| Mode | 用途 | System Prompt | Tool 白名单 | 行为 |
|------|------|---------------|-------------|------|
| BUILD | 默认开发模式 | "You are a coding assistant..." | 全部工具 | 标准 LLM + Tool 循环 |
| PLAN | 分步计划 | "First, create a plan..." | 只读工具 (read/grep/glob) | 先输出计划框架，用户确认后执行 |
| SUBAGENT | 子代理 | 动态生成，依 task 类型 | 依 task 限制 | 一次性执行，结果回传父 session |

#### Tab 管理

```python
@dataclass
class AgentTab:
    id: str
    mode: AgentMode
    session_id: str
    title: str
    created_at: float

class TabManager:
    def create_tab(self, mode: AgentMode) -> AgentTab: ...
    def switch_tab(self, tab_id: str) -> AgentTab: ...
    def close_tab(self, tab_id: str) -> None: ...
    def list_tabs(self) -> list[AgentTab]: ...
```

### 3.2 Session 引擎增强

#### RunState

```python
class RunState(Enum):
    IDLE = "idle"
    ADMITTED = "admitted"  # prompt 已落盘，等待执行
    RUNNING = "running"    # LLM 调用中
    STOPPING = "stopping"  # 中断中
    ERROR = "error"        # 执行出错
    
class RunStatus:
    state: RunState
    error: str | None
    started_at: float | None
    duration_ms: int | None
```

#### SessionExecution 管线

```python
class SessionExecution:
    """标准化执行管线"""
    
    async def execute(
        self,
        session: SessionV2,
        user_input: str,
        agent: AgentV2,
        on_event: Callable[[LLMEvent], Any] | None = None,
    ) -> AsyncIterator[LLMEvent]:
        # 1. ADMIT — prompt 先落盘
        await session.set_run_status(RunState.ADMITTED)
        await session.prompt(user_input)
        
        # 2. RUN — 委托给 agent
        await session.set_run_status(RunState.RUNNING)
        async for event in agent.run(user_input):
            yield event
            # 检查中断
            if session.check_interrupted():
                await session.set_run_status(RunState.STOPPING)
                break
        
        # 3. COMPLETE / ERROR
        ...
```

#### SessionCoordinator 增强

```python
class SessionCoordinator:
    # 现有: IDLE → DRAINING → QUEUED
    # 新增:
    #   - interrupt(): 中断指定 session 的当前执行
    #   - get_status(): 查询所有 session 状态
    #   - wait_for_completion(): 等待指定 session 完成
    #   - 并发限制 (max_concurrent): 防止过多 session 同时执行
```

### 3.3 Plugin 系统 v2

#### PluginHost

```python
class PluginHost:
    """插件生命周期管理器"""
    
    async def discover(self, sources: list[str]) -> list[PluginManifest]: ...
    async def install(self, source: str) -> PluginManifest: ...
    async def activate(self, plugin_id: str) -> None: ...
    async def deactivate(self, plugin_id: str) -> None: ...
    async def uninstall(self, plugin_id: str) -> None: ...
    
    def get_tool_providers(self) -> list[ToolProvider]: ...
    def get_commands(self) -> list[CommandDef]: ...
    def get_ui_extensions(self, layer: str) -> list[UIExtension]: ...
```

#### PluginAPI (插件可见 API)

```python
class PluginAPI:
    """插件在生命周期中可以调用的 API"""
    
    # 注册
    def register_tool(self, tool: type[BaseTool]) -> None: ...
    def register_command(self, cmd: CommandDef) -> None: ...
    def register_provider(self, provider: type[LLMProvider]) -> None: ...
    def register_skill(self, skill: SkillDef) -> None: ...
    
    # UI 扩展
    def add_tui_panel(self, panel: PanelDef) -> None: ...
    def add_web_route(self, route: RouteDef) -> None: ...
    def add_cli_group(self, group: GroupDef) -> None: ...
    
    # 钩子
    def on_session_start(self, handler) -> None: ...
    def on_tool_call(self, handler) -> None: ...
    def on_message(self, handler) -> None: ...
```

---

## 4. 数据模型

### Agent Mode (新增表 / session 模型扩展)

```sql
-- agent_tabs 表
CREATE TABLE agent_tabs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    mode TEXT NOT NULL CHECK(mode IN ('build', 'plan', 'subagent')),
    title TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

### Session RunState (session 状态字段扩展)

```sql
-- sessions 表增加字段
ALTER TABLE sessions ADD COLUMN run_state TEXT NOT NULL DEFAULT 'idle';
ALTER TABLE sessions ADD COLUMN run_error TEXT;
ALTER TABLE sessions ADD COLUMN run_started_at REAL;
```

### Plugin Manifest

```sql
-- plugins 表
CREATE TABLE plugins (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    version TEXT NOT NULL,
    description TEXT,
    author TEXT,
    source TEXT,  -- pip package, git url, local path
    state TEXT NOT NULL DEFAULT 'discovered',
    installed_at REAL NOT NULL,
    activated_at REAL
);
```

---

## 5. 工作顺序

```
                    ┌──────────────────────┐
                    │ Phase 0 Kickoff      │
                    │ (基础数据模型 + CLI)   │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
    ┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
    │ Agent 系统       │ │ Session 引擎  │ │ Plugin 系统 v2   │
    │ ─ agent/base.py  │ │ ─ execution  │ │ ─ host.py        │
    │ ─ build/plan/    │ │  管线        │ │ ─ api.py         │
    │   subagent       │ │ ─ coordinator│ │ ─ registry.py    │
    │ ─ tab manager    │ │   增强       │ │ ─ discovery.py   │
    │ ─ factory        │ │ ─ RunState   │ │ ─ hooks.py       │
    └────────┬─────────┘ └──────┬───────┘ └────────┬─────────┘
             │                  │                   │
             └──────────────────┼───────────────────┘
                                ▼
                    ┌──────────────────────┐
                    │ 集成测试 + 兼容验证    │
                    │ pytest && mypy && ruff│
                    └──────────────────────┘
```

三个 P0 模块可**并行开发**，相互依赖最小：
- Agent 系统依赖 SessionV2（已有）+ ToolRegistryV2（已有）
- Session 引擎基本独立（增强现有 coordinator）
- Plugin v2 基本独立（新增模块）

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Agent mode 切换影响现有 CLI/TUI 行为 | High | 保持 `cs chat` 默认 build mode，mode 切换只通过显式参数 |
| Plugin v2 与现有 PluginLoader 兼容 | Medium | 新实现与旧加载器共存，逐步迁移 |
| Session 中断导致数据不一致 | High | Durable admit：prompt 先序列化再执行 |
| 多 Tab 导致 EventStore 并发冲突 | Medium | Tab 与 session 一一对应，复用现有 session 锁机制 |

---

## 7. 相关文件

### 新文件清单
- `src/cscode/core/agent/__init__.py`
- `src/cscode/core/agent/base.py`
- `src/cscode/core/agent/build.py`
- `src/cscode/core/agent/plan.py`
- `src/cscode/core/agent/subagent.py`
- `src/cscode/core/agent/factory.py`
- `src/cscode/core/agent/tab.py`
- `src/cscode/core/agent/system_prompts.py`
- `src/cscode/core/execution.py`
- `src/cscode/core/plugin/__init__.py`
- `src/cscode/core/plugin/host.py`
- `src/cscode/core/plugin/api.py`
- `src/cscode/core/plugin/registry.py`
- `src/cscode/core/plugin/discovery.py`
- `src/cscode/core/plugin/hooks.py`

### 修改文件清单
- `src/cscode/core/session.py` — 加 RunState 字段 + durable prompt
- `src/cscode/core/coordinator.py` — 增强中断 + 并发限制
- `src/cscode/core/runner.py` — 集成 SessionExecution 管线
- `src/cscode/plugins/loader.py` — 可选: 软链到新的 PluginHost
- `src/cscode/cli.py` — 加 `--mode` 参数 + `/mode` 子命令
- `src/cscode/tui/app.py` — Tab 切换 UI
- `src/cscode/server/routes/sessions.py` — 暴露 RunState API

### 测试文件
- `tests/test_agent_base.py`
- `tests/test_agent_modes.py`
- `tests/test_agent_tab.py`
- `tests/test_execution.py`
- `tests/test_plugin_host.py`
- `tests/test_plugin_api.py`
