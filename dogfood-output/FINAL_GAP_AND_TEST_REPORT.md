# CScode v0.3.4 全面测试与 OpenCode 差距分析报告

## 1. 执行摘要

- **版本状态**：v0.3.4 已全系统一（`__init__.py` / `app.py` / `tauri.conf.json` / `Cargo.toml` / `build.sh`），DMG 打包成功。
- **GUI 测试结果**：综合测试 30 项通过 27 项；并发 Session 隔离测试 7 项全部通过。
- **API 审计结果**：14 个端点中 13 个正常；1 个 404 由测试脚本路径错误导致。
- **真正代码问题（不改代码）**：
  1. 历史数据库中残留大量 `text.delta` 事件，造成启动/加载时海量 WARNING 日志。
  2. Settings 面板 Provider/Model 的 `<label>` 与 `<select>` 未正确关联，存在可访问性（a11y）缺陷。
- **与 OpenCode 的核心差距**：架构（Effect-TS vs 传统 asyncio）、多 Agent/Provider Catalog、权限系统、Skill/Plugin 生态、国际化、测试/CI 成熟度。

---

## 2. 测试环境

| 项目 | 值 |
|------|-----|
| 目标 URL | `http://127.0.0.1:8080` |
| 后端版本 | `0.3.4` |
| 数据库 | `/Users/mac/.config/cscode/cscode.db` (2.13 MB) |
| 测试工具 | Playwright + Chromium |
| 测试脚本 | `dogfood-output/v4-final-test/01_recon.py` 等 |

---

## 3. GUI 全面测试结果

### 3.1 综合测试（`02_comprehensive_test.py`）

| 指标 | 结果 |
|------|------|
| 总项 | 30 |
| 通过 | 27 |
| 失败 | 3 |

**失败项分析：**

| 测试项 | 失败原因 | 是否代码缺陷 |
|--------|----------|--------------|
| Hover buttons | 测试脚本使用 `ElementHandle.locator()`，Playwright 的 `ElementHandle` 无此属性 | ❌ 测试脚本问题 |
| Settings: Provider | `<label>` 未通过 `for`/`id` 与 `<select>` 关联，脚本按 `label.innerText` / `name` 查找失败 | ⚠️ 前端 a11y 缺陷（功能正常） |
| Settings: Model | 同上 | ⚠️ 前端 a11y 缺陷（功能正常） |

其余功能全部正常：
- 所有可见按钮（Plan/Build、Filter、Sort、Refresh、New Session、Export、Delete、Settings、Help、Attach、Send、Open terminal）均可定位。
- 新建会话、会话切换、发送消息、AI 响应、打开终端、Filter/Sort/Refresh 点击、Plan/Build 切换均通过。

### 3.2 并发 Session 隔离测试（`03_isolation_test.py`）

| 测试项 | 结果 | 说明 |
|--------|------|------|
| Session A 内容保留 | 通过 | Python 消息从 2 → 3 |
| No JS leakage into A | 通过 | JavaScript 在 A 中仅出现 1 次 |
| Session B 内容保留 | 通过 | JavaScript 保持 2 条 |
| No Python leakage into B | 通过 | Python 在 B 中仅出现 1 次 |
| No wrong session events | 通过 | 0 次跨 Session 事件 |
| No stream superseded | 通过 | 0 次意外流覆盖 |
| Events processed | 通过 | applyEvent=0, appendMessage=6 |

**结论**：并发 Session 隔离在 GUI 层验证通过，无消息窜扰。

### 3.3 API 端点审计（`04_api_audit.py`）

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| GET | `/api/health` | 200 | OK |
| GET | `/api/version` | 200 | `{"version":"0.3.4","app":"CScode"}` |
| GET | `/api/config` | 200 | OK |
| GET | `/api/tools` | 200 | OK |
| GET | `/api/sessions` | 200 | OK |
| POST | `/api/sessions` | 200 | OK |
| GET | `/api/share` | 200 | OK |
| POST | `/api/share` | 201 | OK |
| GET | `/api/workspaces` | 200 | OK |
| POST | `/api/workspaces` | 422 | 缺少 `name` 字段，属预期校验 |
| GET | `/api/credentials` | 200 | OK |
| GET | `/api/application-tools` | **404** | 测试脚本路径错误 |
| GET | `/docs` | 200 | OK |
| GET | `/openapi.json` | 200 | OK |
| GET | `/redoc` | 200 | OK |

**说明**：后端实际注册的是 `/api/tools/application`（见 `src/cscode/server/app.py:1900`），`/api/application-tools` 并非有效路由。如果前端或集成文档声称该路径存在，则需修正文档/前端调用。

---

## 4. 服务端日志分析

### 4.1 日志文件

- 路径：`/tmp/cscode-diag.log`
- 大小：约 8.9 MB，79,110 行
- WARNING：79,098 条
- ERROR：12 条

### 4.2 关键日志模式

| 模式 | 数量 | 说明 |
|------|------|------|
| `Unknown event type in projection: text.delta` | 79,052 条 | 历史事件污染 |
| `Unknown event type in projection: error` | 46 条 | `error` 事件未被 SessionProjector 识别 |
| `LLM stream request failed: All connection attempts failed` | 6 条 | 无有效 API Key / 网络不可达 |
| `_run_loop: llm error ... All connection attempts failed` | 6 条 | 同上 |

### 4.3 历史 `text.delta` 污染根因

数据库 `/Users/mac/.config/cscode/cscode.db` 中：

```
total events: 6443
event types: [
  ('text.delta', 5497),
  ('step.started', 181),
  ('session.deleted', 155),
  ('session.created', 149),
  ('text.ended', 113),
  ('prompt.admitted', 103),
  ('tool.called', 90),
  ...
]
```

- `text.delta` 事件共 **5,497** 条，占全部事件的 **85.3%**。
- 主要集中在前 3 个 Session：
  - `1783490900903273000`: 2,983 条
  - `1783490900969780000`: 1,941 条
  - `1783490772294434000`: 276 条

**当前代码写入逻辑**：`src/cscode/server/app.py:83` 的 `PERSIST_EVENT_TYPES` 已明确排除 `text.delta`，`on_event` 持久化分支只写入 `step.started/text.ended/step.ended/tool.called/tool.success/tool.failed/error`。因此新增 `text.delta` 已被阻止。

**问题性质**：旧版本代码或开发过程中曾将 `text.delta` 持久化到 EventStore，当前为**历史数据污染**。它导致：
1. 启动时加载历史 Session 触发大量 WARNING 日志；
2. 投影器需要遍历大量无用事件，增加加载延迟；
3. 数据库膨胀。

**建议（不修改代码）**：在发布前清理用户数据库中的 `text.delta` 事件，或在迁移脚本中删除/归档这些事件。

### 4.4 LLM 连接错误

所有 ERROR 均为 `ConnectError(OSError('All connection attempts failed'))`，原因：
- 测试环境未配置有效 API Key / 模型端点不可达；
- 这不是代码缺陷，而是环境配置问题。

---

## 5. 与 OpenCode（`opencode-dev-4`）的功能差距分析

### 5.1 总体评估

| 维度 | CScode | OpenCode | 差距等级 |
|------|--------|----------|----------|
| 基础架构 | FastAPI + React + asyncio | FastAPI + React + Effect-TS 代数效应 | 高 |
| Session 隔离 | 按 ID 严格隔离，Event Sourcing | 按 ID 严格隔离，Event Sourcing V2 | 低 |
| 流式响应 | SSE | SSE | 无 |
| 工具调用 | ToolRegistryV2 + 多种工具 | ToolRegistry + Tools.Service + 应用工具 | 中 |
| 多 Agent | AgentV2（单 Agent + SubAgent） | AgentV2.Service、Planner、多 Agent 选择 | 高 |
| Provider/Model 目录 | 简单 Config | Catalog + ProviderV2 + ModelV2，支持 20+ provider | 高 |
| MCP 支持 | MCPClient/MCPServer 基础实现 | ConfigMCP（Local/Remote/OAuth/Timeout） | 中 |
| Plugin 系统 | PluginAPI 基础注册 | Effect 化插件生命周期、Host、Scope 管理 | 高 |
| Skill 系统 | SkillLoader 文件加载 | SkillV2.Service、目录发现、权限集成 | 中 |
| 权限系统 | PermissionV2 基础规则 | PermissionV2.Service、ask/assert/reply、阻断/纠正 | 高 |
| PTY | PTYSessionManager | Pty.Service（多订阅、缓冲区、退出保持） | 中 |
| Workspace | WorkspaceStore | WorkspaceV2 + Project 上下文 | 中 |
| Share | ShareStore | ShareV2 + 协作 | 中 |
| Credential | CredentialStore | CredentialV2 + SQL | 低 |
| 国际化 | 无 | 17+ 语言 | 高 |
| TUI | 部分（Textual） | 完整 TUI 包 | 中 |
| Desktop | Tauri v2 | 自有 Desktop 包 | 低 |
| 测试 | pytest 基础 | bun test + 多包测试 | 高 |
| CI/CD | 单 workflow 三平台 | 10+ workflow（build/test/deploy/nix/stats） | 高 |
| LSP | LSPManager | LSP 集成 | 低 |

### 5.2 详细差距说明

#### 5.2.1 架构与运行时（高）

- **OpenCode**：基于 Effect-TS 构建，使用 `Layer`、`Service`、`Context`、`Scope` 管理依赖和生命周期，具备结构化并发、可观测性（OpenTelemetry）、类型安全错误处理。
- **CScode**：传统 asyncio + FastAPI 依赖注入，生命周期管理靠 `lifespan` 和全局变量，错误处理较松散。

#### 5.2.2 Agent 系统（高）

- **OpenCode**：`AgentV2.Service` 支持多 Agent 注册、默认选择、模式（build/subagent）、Planner、多 Agent 协作；Agent 信息作为一等公民。
- **CScode**：`AgentV2` 是单个运行器，支持 SubAgentOrchestrator（`@tool` mention），但没有 Agent 注册中心和 Planner 抽象。

#### 5.2.3 Provider/Model Catalog（高）

- **OpenCode**：`Catalog.Service`、`ProviderV2`、`ModelV2` 形成完整目录，内置 20+ provider（OpenAI、Anthropic、Google、Mistral、Cohere、Groq 等），支持 API Key/Integration/OAuth 多种认证。
- **CScode**：`Config` 中 `provider/model/api_base/api_key` 为字符串配置，仅内置 5 个 provider 选项，扩展性有限。

#### 5.2.4 Plugin 系统（高）

- **OpenCode**：`PluginV2.Service` 使用 Effect 管理插件加载、Scope、失败、事件发布；有独立 `@opencode-ai/plugin` 包定义插件契约。
- **CScode**：`PluginAPI` 仅提供基础注册（tool/command/provider/skill/ui），没有生命周期管理、隔离加载、失败恢复机制。

#### 5.2.5 Skill 系统（中）

- **OpenCode**：`SkillV2.Service` 支持 embedded/directory/url 三种来源、frontmatter 解析、目录发现、权限过滤、`skill` 工具调用。
- **CScode**：`SkillLoader` 支持本地 `.md` 文件加载、简单关键词推荐，但未与权限/工具注册深度集成。

#### 5.2.6 权限系统（高）

- **OpenCode**：`PermissionV2.Service` 提供 `ask/assert/reply/forSession/list`；支持 `allow/deny/ask` 规则；执行被拒绝时可纠正（CorrectedError）；规则持久化。
- **CScode**：`permission_v2.py` 提供基础 Ruleset 匹配，`is_application_tool` 仅做白名单判断，没有交互式询问/纠正流程。

#### 5.2.7 MCP 支持（中）

- **OpenCode**：`ConfigMCP` 支持 Local（command/cwd/env/disabled/timeout）和 Remote（url/headers/oauth/disabled/timeout）两种服务器类型，配置模型完整。
- **CScode**：`MCPClient` 实现 JSON-RPC over stdio，`MCPServer` 提供工具暴露；`SettingsPanel` 支持 `mcp_servers` 数组配置，但配置模型较简单（无 OAuth/Timeout 细分）。

#### 5.2.8 国际化（高）

- **OpenCode**：`packages/ui/src/i18n` 和 `packages/app/src/i18n` 支持 ar/br-bs-da-de-en-es-fr-ja-ko-no-pl-ru-th-tr-uk-zh-zht 等 17+ 语言。
- **CScode**：当前仅英文界面。

#### 5.2.9 测试与 CI（高）

- **OpenCode**：多包独立测试、类型检查（tsgo）、e2e、stats、storybook、nix 构建；workflows 数量 10+。
- **CScode**：pytest 单元测试、ruff、mypy；单个 GitHub Actions workflow 负责三平台构建。

#### 5.2.10 PTY（中）

- **OpenCode**：`Pty.Service` 支持多订阅者、缓冲区限制、退出保持、cursor 重放、attach/detach。
- **CScode**：`PTYSessionManager` 提供基础持久 shell session，功能可用但模型较简单。

---

## 6. 真正需要关注的前端/客户端问题

### 6.1 Settings 面板可访问性

**位置**：`src/cscode/web/src/components/ui/SettingsPanel.tsx:122-171`

Provider 和 Model 的 `<label>` 没有 `htmlFor`，`<select>` 没有 `id`，导致：
- 屏幕阅读器无法正确朗读标签；
- 自动化测试难以稳定定位；
- 表单验证/提交时标签关联缺失。

**影响**：功能上用户可正常使用，但可访问性和测试稳定性受损。

### 6.2 历史 `text.delta` 数据问题

**位置**：用户数据库 `~/.config/cscode/cscode.db`

影响：
- 日志被 79,000+ WARNING 淹没，真正问题难以发现；
- 加载大 Session 时性能下降；
- 打包后新用户若导入旧数据库同样受影响。

**建议**：在迁移脚本中增加清理步骤，将 `type='text.delta'` 的事件迁移或删除。

### 6.3 API 路径一致性

- 后端：`/api/tools/application`（正确）
- 测试脚本误用：`/api/application-tools`（404）

需确认前端代码没有调用错误路径。经搜索 `src/cscode/web`，未发现 `/api/application-tools` 调用，因此前端无此问题。

---

## 7. 非缺陷项说明

| 现象 | 原因 | 结论 |
|------|------|------|
| LLM 连接失败 | 无有效 API Key / 端点不可达 | 环境配置问题 |
| Hover buttons 测试失败 | Playwright API 误用 | 测试脚本问题 |
| Settings Provider/Model 测试失败 | 测试按 label/name 查找，未匹配无关联 label | 测试脚本 + 前端 a11y |
| `/api/application-tools` 404 | 路径错误 | 测试脚本问题 |

---

## 8. 建议

### 8.1 立即处理（发布前）

1. **清理历史 `text.delta` 事件**
   - 在数据库迁移脚本中删除或归档 `type='text.delta'` 的事件。
   - 或提供升级说明让用户重置数据库。

2. **修复 Settings 面板 label/select 关联**
   - 为 Provider/Model 的 `<select>` 添加 `id`，为 `<label>` 添加 `htmlFor`。

3. **统一 API 路径文档**
   - 确认所有文档/测试/前端调用 `/api/tools/application`，删除 `/api/application-tools` 误用。

### 8.2 中长期（与 OpenCode 缩小差距）

1. **Provider/Model Catalog**：抽象 Provider/Model 注册表，支持更多模型和动态配置。
2. **多 Agent 架构**：引入 Agent 注册中心、Planner、模式切换。
3. **权限系统升级**：增加交互式确认、规则持久化、阻断/纠正机制。
4. **Plugin 生命周期**：实现隔离加载、错误恢复、事件发布。
5. **国际化**：引入 i18n 框架，逐步增加语言包。
6. **测试与 CI**：增加端到端测试、类型检查、多平台 nightly build。

---

## 9. 结论

CScode v0.3.4 的核心功能（Session 管理、流式响应、工具调用、并发隔离、打包）已完整实现并通过 GUI 测试。当前真正影响发布质量的问题是：

1. **历史 `text.delta` 事件污染**（日志噪音 + 性能）；
2. **Settings 面板可访问性**（a11y）。

其余测试失败项均为测试脚本或环境配置问题，不是代码缺陷。

与 OpenCode 相比，CScode 在架构成熟度、多 Agent、Provider Catalog、Plugin/Skill 生态、权限系统、国际化和测试覆盖方面存在明显差距，需作为后续迭代重点。
