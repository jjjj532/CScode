# CScode v0.3.4 桌面应用端到端测试报告（修复后）

**测试时间**：2026-07-22  
**测试方式**：安装修复后的 DMG → 启动桌面应用 → API 端到端测试  
**测试版本**：v0.3.4（DMG 77MB）

---

## 1. 修复验证

### 1.1 打包结构修复

| 修复项 | 修复前 | 修复后 |
|--------|--------|--------|
| 依赖打包方式 | `site-packages.zip`（含 .so） | `python_deps/`（解压目录） |
| PYTHONPATH 分隔符 | `MAIN_SEPARATOR`（`/`） | 正确使用 `:` |
| 资源路径 | `/resources/cscode-backend/**/*` | `/resources/**/*` |

### 1.2 后端启动验证

```bash
# 启动命令
/Applications/CScode.app/Contents/MacOS/cscode-desktop

# 验证结果
curl http://127.0.0.1:8080/api/health
# {"status":"ok","version":"0.3.4"} ✅
```

---

## 2. 端到端测试结果

### 2.1 测试步骤汇总

| 步骤 | 测试项 | 结果 | 说明 |
|------|--------|------|------|
| 1 | DMG 挂载 | ✅ 通过 | 结构正确，含 python_deps/ 目录 |
| 2 | 应用安装 | ✅ 通过 | CScode.app → /Applications |
| 3 | 应用启动 | ✅ 通过 | Rust 二进制 + Python 后端 |
| 4 | 后端健康检查 | ✅ 通过 | `GET /api/health` → 200 |
| 5 | 创建会话 | ✅ 通过 | `POST /api/sessions` → 返回 ID |
| 6 | 获取会话列表 | ❌ 失败 | 返回空列表（数据库有记录） |
| 7 | 获取会话详情 | ❌ 失败 | `GET /api/sessions/{id}` → 404 |
| 8 | 获取配置 | ✅ 通过 | `GET /api/config` → 200 |
| 9 | 更新配置 | ❌ 失败 | `PUT /api/config` → 405 |
| 10 | 获取工具列表 | ✅ 通过 | 12 个工具正常返回 |
| 11 | 获取应用工具 | ✅ 通过 | 12 个应用工具正常返回 |
| 12 | 获取配置参考 | ✅ 通过 | 环境变量配置项正常 |
| 13 | WebSocket 连接 | ✅ 通过 | `GET /api/ws` → 101 Switching |
| 14 | 获取工作区 | ✅ 通过 | 空列表（无工作区） |
| 15 | 获取共享链接 | ✅ 通过 | 4 个历史共享链接 |
| 16 | WARNING 日志 | ✅ 通过 | 0 条 WARNING |

### 2.2 详细测试输出

#### ✅ 创建会话
```json
POST /api/sessions
Response: {"id": "1784713840986132000", "title": "New Session"}
```

#### ✅ 工具列表
```json
GET /api/tools
Response: {"tools": ["glob", "grep", "ls", "lsp", "lsp_diagnostics", 
           "lsp_find_references", "lsp_goto_definition", "lsp_symbols", 
           "read", "search", "webfetch", "websearch"]}
```

#### ✅ WebSocket 连接
```
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
```

#### ✅ 配置获取
```json
{"provider": "openai", "model": "MiniMax-M2.5", "max_tokens": 2048, ...}
```

---

## 3. 发现的问题

### 3.1 Session API 问题

**现象**：创建会话成功，但 `GET /api/sessions` 返回空列表，`GET /api/sessions/{id}` 返回 404

**数据库验证**：
```bash
sqlite3 ~/.config/cscode/cscode.db "SELECT COUNT(*) FROM events WHERE aggregate_id = '1784713840986132000'"
# 1 ✅ (有记录)

sqlite3 ~/.config/cscode/cscode.db "SELECT * FROM event_sequences WHERE aggregate_id = '1784713840986132000'"
# 1784713840986132000|1 ✅ (有记录)
```

**原因分析**：可能是 `GET /api/sessions` 查询逻辑问题，或 sessions.py 中列表查询的 SQL 条件不匹配。

### 3.2 配置更新问题

**现象**：`PUT /api/config` 返回 405 Method Not Allowed

**原因分析**：Config API 可能只支持 GET 方法，或 PUT 端点未正确注册。

### 3.3 终端 API 问题

**现象**：`GET /api/pty/init` 返回 404

**原因分析**：PTY 端点可能在不同路径或需要特定条件。

---

## 4. 修复效果验证

### 4.1 历史事件清理（修复后）

```bash
# 检查日志中是否有 WARNING
grep -i "warning" /tmp/cscode-desktop-run3.log
# (空) ✅ 0 条 WARNING

# 验证 migration 010 已运行
sqlite3 ~/.config/cscode/cscode.db "SELECT COUNT(*) FROM events WHERE type IN ('text.delta', 'error')"
# 0 ✅ 已清理
```

### 4.2 打包结构验证

```
/Applications/CScode.app/Contents/Resources/resources/
├── python/              # 源码
│   └── cscode/
└── python_deps/         # 解压的依赖（含 .so）
    ├── pydantic/
    ├── pydantic_core/
    │   └── _pydantic_core.cpython-314-darwin.so  ✅ 可加载
    └── ...
```

---

## 5. 测试结论

### 5.1 通过项

| 类别 | 测试项 |
|------|--------|
| **打包** | DMG 挂载、应用安装、版本号验证 |
| **启动** | Rust 二进制启动、Python 后端启动、端口监听 |
| **核心 API** | Health、Config、Tools、WebSocket、Share |
| **日志** | 0 条 WARNING（migration 010 生效） |

### 5.2 待修复项

| 优先级 | 问题 | 位置 |
|--------|------|------|
| P0 | Session 列表/详情查询失败 | [sessions.py](file:///Users/mac/AI/CScode/src/cscode/server/routes/sessions.py) |
| P1 | Config PUT 返回 405 | [routes/config.py](file:///Users/mac/AI/CScode/src/cscode/server/routes) |
| P2 | PTY 端点路径 | [routes/](file:///Users/mac/AI/CScode/src/cscode/server/routes) |

---

## 6. 建议

1. **立即修复**：Session API 查询逻辑，确保创建后能正确读取
2. **验证修复**：修复后重新测试完整端到端流程
3. **GUI 测试**：修复核心 API 后，使用 Playwright 进行完整 GUI 测试

---

**报告生成时间**：2026-07-22 18:00  
**报告路径**：`dogfood-output/DESKTOP_E2E_TEST_REPORT_V2.md`