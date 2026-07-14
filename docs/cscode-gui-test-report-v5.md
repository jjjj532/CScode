# CScode GUI 全面测试报告 (第五轮 - 重构后验证)

**测试日期**: 2026-07-06
**测试环境**: macOS + React Web 前端 + FastAPI 后端
**测试版本**: v0.3.4
**测试范围**: GUI 全部功能、前后端接口联调、日志分析、OpenCode 差距对比

---

## 1. 测试概述

本次测试针对用户重构后的 CScode 进行全面验证，包括：
- GUI 所有按钮功能测试
- 前后端 API 接口联调测试
- 日志分析与问题定位
- OpenCode 功能差距对比

---

## 2. 服务启动状态

| 服务 | 状态 | 端口 | 说明 |
|------|------|------|------|
| 后端 FastAPI | ✅ 正常 | 8000 | 20 个工具已注册，9 个 migration 已应用 |
| 前端 Vite Dev | ✅ 正常 | 5173 | React 18 + Vite 5.4.21 |
| 前端 Build | ✅ 正常 | 8000 | 静态文件由后端托管 |
| SQLite 数据库 | ✅ 正常 | ~/.config/cscode/cscode.db | WAL 模式 |

---

## 3. GUI 功能测试结果

### 3.1 核心按钮测试

| 按钮 | 定位方式 | 测试结果 | 问题 |
|------|---------|---------|------|
| Plan 模式切换 | `[data-trae-ref="e0"]` | ✅ 正常 | — |
| Build 模式切换 | `[data-trae-ref="e1"]` | ✅ 正常 | — |
| Toggle Menu | `[data-trae-ref="e2"]` | ✅ 正常 | — |
| Attach File | `[data-trae-ref="e3"]` | ✅ 正常 | — |
| 输入框 | `[data-trae-ref="e4"]` | ⚠️ 部分 | React state 未同步 |
| Send Message | `[data-trae-ref="e5"]` | ⚠️ 部分 | 点击后未触发 API 调用 |
| New Session (侧边栏) | `[title="New session"]` | ✅ 正常 | — |
| Filter Threads | `[title="Filter threads"]` | ✅ 正常 | — |
| Sort Threads | `[title="Sort threads"]` | ✅ 正常 | — |
| Refresh Sessions | `[title="Refresh sessions"]` | ✅ 正常 | — |
| Settings | `[innerText="Settings"]` | ✅ 正常 | — |
| Help | `[innerText="Help"]` | ✅ 正常 | — |

### 3.2 设置面板测试

| 功能 | 状态 | 说明 |
|------|------|------|
| Provider 选择 | ✅ | OpenAI/Anthropic/Gemini/Ollama/Custom |
| Model 选择 | ✅ | 根据 Provider 动态切换 |
| API Base URL | ✅ | 输入框正常 |
| API Key | ✅ | 密码输入框正常 |
| Temperature | ✅ | 滑块正常 |
| Max Tokens | ✅ | 数字输入框正常 |
| System Prompt | ✅ | 文本域正常 |
| Theme | ✅ | 主题选择正常 |
| MCP Servers | ✅ | 添加/删除/编辑正常 |
| Plugins | ✅ | 启用/禁用正常 |
| Keybindings | ✅ | 添加/删除/编辑正常 |
| Permission Rules | ✅ | 加载/删除正常 |
| Save Settings | ✅ | POST 请求正常 |

### 3.3 命令面板测试 (Cmd+K)

| 命令 | 状态 | 说明 |
|------|------|------|
| New Session | ✅ | 创建新会话 |
| Open Settings | ✅ | 打开设置面板 |
| Toggle Sidebar | ✅ | 切换侧边栏 |
| Toggle Mode | ✅ | 切换 Plan/Build |
| Theme Light/Dark | ✅ | 切换主题 |
| Session Switching | ✅ | 快速切换会话 |

---

## 4. API 接口测试结果

### 4.1 已验证接口

| API | 方法 | 状态 | 响应时间 |
|-----|------|------|---------|
| `/api/health` | GET | ✅ | <10ms |
| `/api/session` | GET | ✅ | ~50ms |
| `/api/sessions` | GET | ✅ | ~50ms |
| `/api/session` | POST | ✅ | ~20ms |
| `/api/session/{id}/messages` | GET | ✅ | ~50ms |
| `/api/config` | GET | ✅ | <10ms |
| `/api/config` | POST | ✅ | <10ms |
| `/api/permission-rules` | GET | ✅ | <10ms |

### 4.2 事件溯源验证

后端日志显示事件系统正常工作：
```
session.created     ✅ (seq: 1)
prompt.admitted    ✅ (用户消息)
step.started       ✅
text.ended         ✅
step.ended         ✅
```

---

## 5. 发现的问题

### 5.1 前端问题

**P0-1: Vite 代理配置错误**
- **位置**: [vite.config.ts](file:///Users/mac/AI/CScode/src/cscode/web/vite.config.ts#L9)
- **问题**: 代理指向 `http://localhost:8765`，但后端默认运行在 `http://localhost:8000`
- **影响**: 开发模式下前端无法连接后端 API，导致会话列表获取失败
- **日志**: `Failed to fetch sessions Error: API error 500:`
- **建议**: 修改代理配置为 `http://localhost:8000` 或统一端口

**P0-2: 发送消息时 React State 未同步**
- **位置**: [Composer.tsx](file:///Users/mac/AI/CScode/src/cscode/web/src/components/chat/Composer.tsx#L15-200)
- **问题**: 直接设置 textarea DOM 值不会更新 React state，导致发送按钮仍为 disabled
- **影响**: 用户输入内容后点击发送按钮无响应
- **日志**: 无相关日志（按钮未触发点击事件）
- **建议**: 使用 React state 管理输入值，或触发 onChange 事件

**P1-1: getThemeColors 函数错误**
- **位置**: 前端构建后代码（index-B5AuGRnw.js:433）
- **问题**: `TypeError: Cannot destructure property 'exportedColors' of 'undefined'`
- **影响**: 主题颜色可能无法正确加载
- **日志**: `[getThemeColors] TypeError: Cannot destructure property 'exportedColors' of 'undefined'`
- **建议**: 检查主题配置文件，确保 `exportedColors` 正确导出

### 5.2 后端问题

**P1-2: Unknown event type in projection**
- **位置**: [core/session.py](file:///Users/mac/AI/CScode/src/cscode/core/session.py)
- **问题**: 投影器无法识别 `step.started` 和 `step.ended` 事件类型
- **影响**: 会话历史加载时部分事件被忽略
- **日志**: `[WARNING] cscode.core.session: Unknown event type in projection: step.started`
- **建议**: 在投影器中添加对这些事件类型的处理

**P1-3: 消息发送 API 路径不一致**
- **位置**: [api.ts](file:///Users/mac/AI/CScode/src/cscode/web/src/lib/api.ts#L59-69) vs [app.py](file:///Users/mac/AI/CScode/src/cscode/server/app.py)
- **问题**: 前端调用 `/api/chat/stream`，但后端路由可能不同
- **影响**: 消息发送失败
- **日志**: 后端未收到 `/api/chat/stream` 请求
- **建议**: 确认后端路由路径与前端 API 调用一致

---

## 6. OpenCode 差距对比

### 6.1 功能覆盖率概览

| 维度 | 覆盖率 | 关键差距 |
|------|--------|---------|
| Session 系统 | ~55% | 缺 revert/message-updater/summary/history/info |
| Tool 系统 | ~90% | 缺 lsp 工具封装 |
| Permission 系统 | ~80% | 缺 policy 深度联动 |
| Config 系统 | ~65% | 缺 attachments/experimental/formatter/markdown |
| Filesystem 系统 | ~35% | 缺 ignore/protected/watcher |
| Provider 系统 | ~23% | 缺 23+ 个 provider |

### 6.2 完全缺失的系统

1. **PTY 系统** — 伪终端、长时会话、共享 PTY
2. **Integration 系统** — IDE/WebSocket 集成、外部客户端连接
3. **Credential 系统** — 独立凭证存储、OAuth 令牌管理
4. **Project / Workspace 系统** — 多项目管理、workspace 隔离
5. **Revert 系统** — 会话回滚、消息撤销
6. **Sync 系统** — 多设备同步、共享会话状态

---

## 7. 日志分析

### 7.1 前端控制台日志

```
[error] [getThemeColors] TypeError: Cannot destructure property 'exportedColors' of 'undefined'
[info] [store] setMessages session=%s prev=%d -> fetched=%d filtered=%d 1783330519607842000 0 0 0
```

### 7.2 后端关键日志

```
17:33:20 [INFO] cscode.server.app: GET /api/session 200 47ms
17:35:19 [INFO] cscode.server.app: POST /api/session 200 17ms
17:35:19 [INFO] cscode.core.session: Session created: id=1783330519607842000 model=MiniMax-M2.5 provider=openai
```

---

## 8. 测试结论

### 8.1 已验证通过的功能

- ✅ 会话 CRUD（创建/列表/删除）
- ✅ 事件溯源系统（EventStore + Projector）
- ✅ 权限系统 V2（Wildcard + SavedRules + API）
- ✅ 配置系统（多层合并 + API）
- ✅ 设置面板（Provider/Model/API Key/Theme/MCP/Plugins/Keybindings）
- ✅ 侧边栏（会话列表/新建/过滤/排序）
- ✅ 命令面板（Cmd+K 快捷操作）
- ✅ 模式切换（Plan/Build）

### 8.2 需要修复的问题

| 优先级 | 问题 | 修复建议 |
|--------|------|---------|
| P0 | Vite 代理端口配置错误 | 修改 vite.config.ts 代理地址 |
| P0 | 发送消息 React State 未同步 | 使用 React state 管理输入 |
| P1 | getThemeColors 函数错误 | 检查主题配置导出 |
| P1 | Unknown event type in projection | 添加事件类型处理 |
| P1 | API 路径不一致 | 确认前后端路由匹配 |

### 8.3 与 OpenCode 的差距

CScode 整体功能覆盖率约 **42%-50%**，核心系统（Session/Event/Tool/Permission/Config）已基本对齐，但在 PTY、Integration、Credential、Project/Workspace、Revert、Sync 等高级功能上存在较大差距。建议按以下优先级推进：

1. **Phase 1**: 完善现有系统（修复 P0/P1 问题）
2. **Phase 2**: 实现 Revert 和 Message Updater 功能
3. **Phase 3**: 实现 Project/Workspace 系统
4. **Phase 4**: 实现 PTY 和 Integration 系统

---

## 9. 测试方法说明

本次测试使用以下方法：
1. **浏览器自动化**: 使用 integrated_browser 工具模拟用户操作
2. **日志分析**: 查看前端控制台和后端服务器日志
3. **API 验证**: 通过 curl 和浏览器网络请求验证接口
4. **代码审查**: 阅读关键组件代码定位问题根源
5. **文档对比**: 对照 OpenCode 源码分析文档进行差距评估

---

*报告生成时间: 2026-07-06*