# P0 复刻任务计划 — Agent 系统 + Session 引擎 + Plugin v2

> 基于 `openspec/specs/cscode-opencode-replication-p0.md`
> 总估计: ~2-3 周 (1 人全职)

---

## 依赖图

```
Task 0: 基础脚手架 (数据模型 + CLI 扩展)
  │
  ├──────────────┬──────────────────┐
  ▼              ▼                  ▼
Task 1       Task 2              Task 3
Agent 系统   Session 引擎增强     Plugin v2
  │              │                  │
  └──────────────┴──────────────────┘
                  │
               Task 4
              集成测试 + 兼容验证
```

---

## Task 0: 基础脚手架 (2-3 天)

### T0.1: 数据模型定义

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/agent/__init__.py` | 创建空 `__init__` | 5min |
| `src/cscode/core/agent/base.py` | `AgentMode` enum (`BUILD`, `PLAN`, `SUBAGENT`), `AgentTab` dataclass | 30min |
| `src/cscode/core/agent/tab.py` | `TabManager` 类 (CRUD tab, 切换, 列表) | 1h |
| `src/cscode/core/execution.py` | `RunState` enum + `RunStatus` dataclass + `SessionExecution` 骨架 | 1h |
| `src/cscode/core/plugin/__init__.py` | 创建空 `__init__` | 5min |
| `src/cscode/core/plugin/hooks.py` | `HookPoint` 枚举 + `HookRegistry` | 1h |
| `tests/test_agent_tab.py` | `TabManager` 单元测试 | 30min |
| `tests/test_execution.py` | `RunState` + `RunStatus` 单元测试 | 30min |
| `tests/test_plugin_hooks.py` | `HookRegistry` 单元测试 | 30min |

**验证**: `pytest tests/test_agent_tab.py tests/test_execution.py tests/test_plugin_hooks.py`

### T0.2: Session 模型扩展

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/session.py` | `SessionState` 加 `run_status`/`run_error`/`run_started_at` 字段 | 1h |
| `src/cscode/core/session.py` | `SessionV2.set_run_status()` / `mark_run_error()` / `check_interrupted()` 方法 | 1h |
| `tests/test_core_session.py` | 新增 RunState 方法测试 | 1h |

**验证**: `pytest tests/test_core_session.py`

### T0.3: CLI 扩展

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/cli.py` | `cs chat --mode plan` 参数 | 1h |
| `src/cscode/cli.py` | `cs agent` 命令组 (list/switch/mode) | 1h |
| `tests/test_cli.py` | CLI 参数测试 | 30min |

**验证**: `python -m cscode.cli chat --help && python -m cscode.cli agent --help`

---

## Task 1: Agent 系统 (4-5 天)

### T1.1: AgentV2 基类

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/agent/base.py` | `AgentV2` 抽象基类: `run()`, `get_system_prompt()`, `get_allowed_tools()` | 2h |
| `tests/test_agent_base.py` | 基类测试 (mock 继承验证) | 1h |

**验证**: `pytest tests/test_agent_base.py`

### T1.2: BuildModeAgent

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/agent/build.py` | `BuildModeAgent(AgentV2)` — 原有 `SessionRunner.run()` 逻辑封装 | 2h |
| `src/cscode/core/agent/system_prompts.py` | `BUILD_SYSTEM_PROMPT` — "你是一个编程助手..." | 30min |
| `tests/test_agent_modes.py` | Build mode 测试 (mock LLM client) | 1.5h |

**验证**: `pytest tests/test_agent_modes.py -k build`

### T1.3: PlanModeAgent

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/agent/plan.py` | `PlanModeAgent(AgentV2)` — 2-pass: 计划生成 + 确认后执行 | 3h |
| `tests/test_agent_modes.py` | Plan mode 测试 | 1.5h |

**验证**: `pytest tests/test_agent_modes.py -k plan`

### T1.4: SubAgentModeAgent

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/agent/subagent.py` | `SubAgentModeAgent(AgentV2)` — 从 `SubAgentOrchestrator` 提取通用逻辑 | 2h |
| `tests/test_agent_modes.py` | Subagent mode 测试 | 1h |

**验证**: `pytest tests/test_agent_modes.py -k subagent`

### T1.5: AgentFactory + 集成

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/agent/factory.py` | `create_agent(mode, ...)` 工厂函数 | 1h |
| `src/cscode/core/agent/__init__.py` | 导出所有 agent 类 | 15min |
| `src/cscode/app/agent.py` | 集成 AgentV2 替代直接调 SessionRunner | 2h |
| `src/cscode/tui/app.py` | Tab 选择 UI + mode 切换 | 2h |

**验证**: `cs chat --mode build` / `cs chat --mode plan` / `cs agent list`

---

## Task 2: Session 引擎增强 (3-4 天)

### T2.1: SessionExecution 管线

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/execution.py` | `SessionExecution.execute()` 完整实现 (admit → run → complete/error) | 3h |
| `src/cscode/core/runner.py` | `SessionRunner.run()` → 内部使用 `SessionExecution` | 2h |
| `tests/test_execution.py` | 完整执行管线测试 (mock agent) | 2h |

**验证**: `pytest tests/test_execution.py tests/test_core_session.py`

### T2.2: Coordinator 增强

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/coordinator.py` | `interrupt()` 完善, `get_status()` 批量查询, `max_concurrent` 限制 | 2h |
| `tests/test_coordinator.py` | 并发测试 + 中断测试 | 2h |
*(注: 可能已有 `tests/test_core_session.py` 含 coordinator 测试)*

**验证**: `pytest tests/test_coordinator.py`

### T2.3: 错误恢复

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/execution.py` | `_handle_error()` — LLMError/ToolFailure 分类处理 | 1.5h |
| `src/cscode/core/session.py` | `recover_from_error()` — 回滚到最近有效状态 | 1.5h |
| `tests/test_execution.py` | 错误恢复测试 | 1.5h |

**验证**: `pytest tests/test_execution.py`

---

## Task 3: Plugin 系统 v2 (3-4 天)

### T3.1: PluginManifest + Registry

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/plugin/registry.py` | `PluginManifest` dataclass + `PluginRegistry` (CRUD, 状态机) | 2h |
| `tests/test_plugin_registry.py` | Registry 单元测试 | 1h |

**验证**: `pytest tests/test_plugin_registry.py`

### T3.2: PluginHost 生命周期

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/plugin/host.py` | `PluginHost` — discover/install/activate/deactivate/uninstall | 3h |
| `tests/test_plugin_host.py` | 生命周期测试 | 2h |

**验证**: `pytest tests/test_plugin_host.py`

### T3.3: PluginAPI

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/core/plugin/api.py` | `PluginAPI` — register_tool/command/provider/skill, UI 扩展接口 | 2h |
| `src/cscode/core/plugin/discovery.py` | 插件发现 (本地目录, pip 包) | 1.5h |
| `tests/test_plugin_api.py` | API 注册 + 查询测试 | 1.5h |

**验证**: `pytest tests/test_plugin_api.py`

### T3.4: 与现有 PluginLoader 桥接

| 文件 | 变更 | 估计 |
|------|------|------|
| `src/cscode/plugins/__init__.py` | 新增 `get_v2_host()` 兼容函数 | 1h |
| `tests/test_plugin_compat.py` | 兼容测试 | 1h |

**验证**: `pytest tests/test_plugin_compat.py`

---

## Task 4: 集成测试 + 兼容验证 (2 天)

### T4.1: 端到端集成

| 测试场景 | 估计 |
|----------|------|
| `cs chat --mode plan "write a hello world"` → 输出计划而非直接执行 | 1h |
| 多 Tab: `cs agent switch tab2` → 切换到不同 session/mode | 1h |
| 插件注册: 安装测试插件 → `cs plugin list` 显示已激活 | 1h |
| Session 中断: ctrl+c → session 状态为 stopped 可恢复 | 1h |

### T4.2: 回归验证

```bash
# 全部验证通过方可声称完成
pytest tests/ && mypy src/ && ruff check src/
```

| 检查项 | 预期 |
|--------|------|
| `pytest tests/` | 全部通过 (含已有测试) |
| `mypy src/` | 严格模式 0 error |
| `ruff check src/` | 0 error |
| `chat --help` | 显示 `--mode` 参数 |
| `cs chat` (无参数) | 行为不变 (默认 build mode) |

---

## 汇总

| Task | 天数 | 文件数 | 复杂度 |
|------|------|--------|--------|
| T0: 基础脚手架 | 2-3 | 14 (6新 + 3改 + 5测试) | Low |
| T1: Agent 系统 | 4-5 | 13 (7新 + 2改 + 4测试) | High |
| T2: Session 引擎 | 3-4 | 6 (1新 + 3改 + 2测试) | Medium |
| T3: Plugin v2 | 3-4 | 9 (5新 + 1改 + 3测试) | High |
| T4: 集成验证 | 2 | — | Low |
| **合计** | **14-18** | **~42** | |

### 并行建议

```
Week 1: T0 (3天) + T2 (4天)  — 基础设施和 Session 增强并行
Week 2: T1 (5天) + T3 (4天)  — Agent 和 Plugin 并行
Week 3: T4 (2天)              — 集成验证
```

最快路径: **12 天** (充分利用 Week 1-2 并行)。
