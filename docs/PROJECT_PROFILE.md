# CScode 智能体系统分析及画像文档

> 文档版本: 1.0 | 更新时间: 2025-06-28 | 版本: 0.3.4

---

## 一、智能体系统分析及画像信息

### 1.1 文档版本与更新记录

| 版本 | 更新时间 | 更新人 | 变更内容 |
|------|----------|--------|----------|
| 1.0 | 2025-06-28 | AI Agent | 初始版本，完整系统画像 |

### 1.2 项目归属与干系人

| 角色 | 职责 |
|------|------|
| 项目负责人 | 整体规划、决策 |
| 核心开发者 | 核心模块开发 |
| 维护团队 | 日常维护、Bug修复 |

### 1.3 环境说明

**开发环境**:
- 前端: http://localhost:5173
- 后端: http://localhost:8001
- 数据库: SQLite本地文件

**测试环境**:
- Python 3.11+
- Node.js 22+
- Rust (Tauri桌面端)

### 1.4 术语定义

| 术语 | 定义 |
|------|------|
| MCP | Model Context Protocol，模型上下文协议 |
| Plugin | 可动态加载的扩展模块 |
| Skill | 预定义的Agent行为模式 |
| Event Sourcing | 以事件为中心的架构模式 |
| Session | 用户与AI的交互上下文 |
| Tool | Agent可调用的原子功能单元 |
| TUI | 基于Textual的终端用户界面 |

---

## 二、项目概述

### 2.1 项目定位

- **核心问题**: 为开发者提供AI编程辅助，支持代码编写、审查、调试
- **目标用户**: 个人开发者、软件开发团队
- **竞品差异**: 开源可自部署、支持多LLM Provider、完整工具生态、Tauri桌面端

### 2.2 核心特性

| 特性 | 优先级 | 说明 |
|------|--------|------|
| 多LLM Provider支持 | P0 | OpenAI, Anthropic, Ollama, Gemini, Azure, OpenRouter |
| 完整工具系统 | P0 | read, write, edit, bash, grep, glob, web |
| 多会话管理 | P0 | SQLite持久化 + Event Sourcing |
| MCP支持 | P1 | Model Context Protocol |
| Plugin/Skill扩展 | P1 | 动态加载 |
| 桌面端 | P1 | Tauri v2 |

### 2.3 技术栈

| 层级 | 技术 | 版本 | 选型理由 |
|------|------|------|----------|
| 前端 | React 18 + TypeScript | 18.x | 生态成熟 |
| 状态管理 | Zustand | 4.x | 轻量 |
| 构建 | Vite + Tailwind | 5.x | 快速HMR |
| 后端 | FastAPI (Python) | 0.115.x | 异步+类型安全 |
| 桌面 | Tauri v2 | 2.x | 比Electron轻 |
| 跨平台 | Rust | 2024 Edition | 性能+安全 |
| 存储 | SQLite | 3.x | 零配置 |

### 2.4 核心指标

| 类别 | 指标 | 目标值 |
|------|------|--------|
| 性能 | LLM首token延迟 | < 2s |
| 性能 | 并发会话 | 50+ |
| 质量 | 请求成功率 | > 99% |
| 测试 | 覆盖率 | > 80% |

---

## 三、架构设计

### 3.1 分层架构

```
┌─────────────────────────────────────────────┐
│  UI Layer (CLI / TUI / Web / Desktop)       │
├─────────────────────────────────────────────┤
│  App Layer (factory.py, app.py)             │
├─────────────────────────────────────────────┤
│  Core Layer (session/coordinator/engine)     │
├─────────────────────────────────────────────┤
│  LLM Layer (protocol/service/runtime)       │
├─────────────────────────────────────────────┤
│  Provider Layer (openai/anthropic/ollama)   │
├─────────────────────────────────────────────┤
│  Schema Layer (纯类型，零依赖)               │
├─────────────────────────────────────────────┤
│  Storage Layer (db, event_store)            │
└─────────────────────────────────────────────┘
```

### 3.2 分层依赖规则

- **Schema → LLM → Core → App → Server/UI** (单向)
- 禁止跨层调用，禁止循环import
- 第三方依赖版本锁定在pyproject.toml

### 3.3 容错策略

| 场景 | 降级 | 兜底 |
|------|------|------|
| LLM不可用 | 友好错误提示 | 建议重试 |
| 数据库失败 | 内存缓存 | 离线模式 |
| 网络超时 | 重试3次 | 超时错误 |

---

## 四、模块详解

### 4.1 Schema (`src/cscode/schema/`)

核心类型定义，**零运行时依赖**:

| 文件 | 内容 |
|------|------|
| ids.py | SessionID, MessageID, EventID类型 |
| messages.py | Message, Part, Text/ToolCall/ToolResult |
| events.py | LLMEvent枚举 (TextDelta, ToolCall等) |
| tool.py | ToolCall, ToolResult模型 |
| providers.py | Provider配置和类型 |
| errors.py | ProviderError, ConfigError等 |

### 4.2 LLM层 (`src/cscode/llm/`)

| 文件 | 职责 |
|------|------|
| protocol/ | Provider协议适配 |
| service.py | 请求构建、响应解析 |
| route.py | Provider路由分发 |
| runtime.py | token计费、中止控制 |

### 4.3 Providers (`src/cscode/providers/`)

| Provider | 核心模型 |
|----------|----------|
| openai.py | gpt-4o, gpt-4o-mini |
| anthropic.py | claude-3-5-sonnet |
| ollama.py | 本地模型 |
| gemini.py | gemini-1.5-pro |
| azure.py | Azure部署模型 |
| openrouter.py | 聚合网关 |

### 4.4 Core (`src/cscode/core/`)

| 模块 | 职责 |
|------|------|
| session.py | Event Sourcing: append_event, rebuild_state |
| coordinator.py | 会话串行化，schedule_run |
| engine.py | Agent执行引擎，工具调度 |
| runner.py | Agent运行器 |
| tracker.py | 任务进度跟踪 |

### 4.5 Tools (`src/cscode/tools/`)

| 工具 | 功能 |
|------|------|
| read/write/edit | 文件操作 |
| bash | Shell执行 |
| grep/glob/ls | 搜索和查找 |
| webfetch/websearch | 网页和搜索 |
| browser | Playwright自动化 |

### 4.6 MCP (`src/cscode/mcp/`)

- 协议版本: **2025-03-26**
- 传输: stdio (JSON-RPC)
- 双端: client + server

### 4.7 Plugins (`src/cscode/plugins/`)

加载流程: `discover()` → `load_plugin()` → `importlib.import_module()` → 读取 `__tools__`

### 4.8 Skills (`src/cscode/skills/`)

Skill结构: name, slug, content, path, description

---

## 五、API接口

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/health | 健康检查 |
| POST | /api/chat | 发送消息 |
| POST | /api/chat/stream | 流式聊天 |
| GET | /api/events | 获取事件 |
| GET | /api/sessions | 会话列表 |
| POST | /api/sessions | 创建会话 |
| PATCH | /api/sessions/{id} | 更新会话 |
| DELETE | /api/sessions/{id} | 删除会话 |
| POST | /api/sessions/{id}/stop | 停止会话 |
| POST | /api/sessions/{id}/export | 导出 |
| POST | /api/sessions/import | 导入 |
| GET | /api/files/search | 文件搜索 |
| GET | /api/config | 获取配置 |
| POST | /api/config | 保存配置 |

**错误码**: 400=参数错误, 401=未授权, 404=不存在, 500=内部错误

---

## 六、数据模型

### SessionState

| 字段 | 类型 | 说明 |
|------|------|------|
| session_id | SessionID | 主键 |
| title | str | 会话标题 |
| provider/model | str | Provider和模型 |
| messages | tuple[Message] | 消息列表 |
| status | str | 状态 |
| created_at | float | 创建时间 |
| updated_at | float | 更新时间 |
| seq | int | 事件序列号 |

### Message

- role: user/assistant/system/tool
- parts: list[Part] (Text/ToolCall/ToolResult/Reasoning)

### LLMEvent

TextDelta, TextEnded, ToolCallStarted, ToolCallEnded, ToolResult, Finish

---

## 七、调用链路

```
用户输入 → API → create_agent_v2() → AgentEngine
→ LLM Service → Provider → 外部API
→ SSE流式响应 → EventStore持久化 → 前端更新
```

**关键节点监控**:

| 节点 | 监控指标 | 告警 |
|------|----------|------|
| API | 延迟P99 > 3s | ⚠ |
| LLM | 成功率 < 98% | ⚠ |
| EventStore | 写入 > 100ms | ⚠ |

---

## 八、扩展机制

### Plugin注册

```python
class MyTool(BaseTool):
    name = "my_tool"
    async def execute(self, **kwargs): ...

__tools__ = [MyTool()]
```

### Skill注册

.md文件放入skills/目录，SkillLoader自动发现

---

## 九、存储架构

| 环境 | 数据库 | 连接池 |
|------|--------|--------|
| 开发 | SQLite | - |
| 生产 | PostgreSQL | min=5, max=20 |

Event Sourcing: append-only日志 → rebuild_state()重建Session

---

## 十、目录结构

```
src/cscode/
├── schema/       # 数据模型 (零依赖)
├── llm/          # LLM协议层
├── providers/    # LLM Provider
├── core/         # 核心逻辑
├── tools/        # 工具实现
├── app/          # 应用层
├── server/       # FastAPI服务
├── mcp/          # MCP协议
├── plugins/      # 插件系统
├── skills/       # 技能系统
├── storage/      # 存储层
├── web/          # React前端
├── tui/          # Textual TUI
└── utils/        # 工具函数
```

---

## 十一、维护与调试

| 场景 | 排查步骤 |
|------|----------|
| LLM调用失败 | 检查API Key → 检查网络 → 确认Provider状态 |
| Plugin异常 | 检查目录结构 → 检查__init__.py → 验证__tools__ |
| 会话状态异常 | 检查EventStore → 查看seq连续性 |

**日志**: `cscode.*` 分级日志输出

---

## 十二、优化方向

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P0 | LLM响应优化 | 首token延迟 < 2s |
| P0 | 流式体验 | SSE稳定性 |
| P1 | 缓存层 | 减少重复请求 |
| P1 | 会话性能 | Event Store压缩 |

---

> 本画像文档由智能体自动生成，用于后续维护、调试和迭代参考。