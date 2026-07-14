# CScode 全面 GUI 测试报告

**测试时间**: 2026-07-09
**测试方式**: Playwright 自动化模拟真实用户操作
**测试目标**: http://localhost:8000 (前端构建版本 + Python 后端)

---

## 一、测试概览

| 指标 | 数值 |
|------|------|
| 测试模块数 | 11 个 |
| 测试用例执行 | 11/11 (100%) |
| 发现问题数 | 3 个 |
| P0 阻断性 | 0 |
| P1 严重 | 2 |
| P2 一般 | 1 |
| P3 轻微 | 0 |

---

## 二、测试覆盖范围

### ✅ 已测试功能模块

1. **侧边栏基本功能** - 过滤/排序/刷新/新建会话按钮
2. **会话 hover 按钮** - Export 导出按钮（中文标题会话）
3. **聊天主界面** - Plan/Build 切换、输入框、Attach file、Open terminal
4. **设置页面** - 设置项加载、保存按钮
5. **帮助页面** - 帮助内容加载
6. **过滤/排序/刷新** - 三个顶部操作按钮
7. **多会话创建** - 连续创建多个会话
8. **键盘快捷键** - ESC 关闭侧边栏、Enter 发送
9. **Share 按钮** - 分享功能（发现问题）
10. **会话删除按钮** - Delete 按钮
11. **工作区切换** - 工作区选择器

---

## 三、发现的问题

### P1-1: Share API 路径重复前缀，前端调用 404

**严重程度**: P1 - 严重  
**影响功能**: 会话分享功能完全不可用

**问题描述**:
前端调用 `GET /api/share` 返回 404 Not Found。

**根因**:
后端 `api_router` 已配置 `prefix="/api"`，但 share 相关路由又写了 `/api/share` 前缀，导致实际路径变成 `/api/api/share`。

**受影响的 4 个路由**:
- `GET /api/share` → 实际是 `/api/api/share`
- `POST /api/share` → 实际是 `/api/api/share`
- `GET /api/share/{share_id}` → 实际是 `/api/api/share/{share_id}`
- `DELETE /api/share/{share_id}` → 实际是 `/api/api/share/{share_id}`

**位置**: [app.py:1284-1340](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L1284-L1340)

```python
# 错误写法 (重复 /api 前缀)
@api_router.get("/api/share")
@api_router.post("/api/share")
@api_router.get("/api/share/{share_id}")
@api_router.delete("/api/share/{share_id}")

# 正确写法 (api_router 已有 prefix="/api")
@api_router.get("/share")
@api_router.post("/share")
@api_router.get("/share/{share_id}")
@api_router.delete("/share/{share_id}")
```

**验证结果**:
| URL | HTTP 状态 |
|-----|----------|
| `/api/share` | 404 Not Found ❌ |
| `/api/api/share` | 500 Internal Server Error ❌ |

**复现步骤**:
1. 打开 CScode 应用
2. 浏览器控制台会看到 404 错误: `GET /api/share 404`
3. 点击 Share 按钮无法正常加载分享列表

---

### P1-2: Share API 500 错误 (Internal Server Error)

**严重程度**: P1 - 严重  
**影响功能**: 即使路径正确，分享功能也报错

**问题描述**:
访问 `/api/api/share` (正确路径应该是 `/api/share`，但由于前缀重复实际路径多了一层) 返回 500 错误。

**根因**:
每次请求都创建新的 `Database()` 对象，但没有调用 `await db.init()`，导致 `self.conn` 未初始化。

```
AttributeError: 'Database' object has no attribute 'conn'
```

**错误代码**:
```python
# 错误写法 - 每次都创建新的 Database，没有调用 init()
@api_router.get("/api/share")
async def list_shares(session_id: str | None = None) -> list[dict[str, object]]:
    from cscode.core.sharing import ShareStore
    from cscode.storage.db import Database
    db = Database()  # ❌ 创建了新对象，但没有 await db.init()
    store = ShareStore(db)
    ...
```

**正确做法**:
其他 API 都使用全局 `_db` 对象（在 lifespan 中已调用 `init()`）：
```python
# 正确写法 - 使用全局 _db
@api_router.get("/workspaces")
async def list_workspaces():
    global _workspace_store
    ...
```

**位置**: [app.py:1284-1340](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L1284-L1340) — 所有 4 个 Share 路由都有此问题

**验证**:
```python
# 后端日志显示
File "/Users/mac/AI/CScode/src/cscode/storage/db.py", line 78, in fetchall
    cursor = await self.conn.execute(query, params)
                   ^^^^^^^^^
AttributeError: 'Database' object has no attribute 'conn'
```

**修复建议**:
1. 在 lifespan 中初始化全局 `_share_store`（推荐，与其他 store 保持一致）
2. 或在每个 Share API 路由中使用全局 `_db` 对象

---

### P2-1: 聊天发送消息出现网络错误

**严重程度**: P2 - 一般  
**影响功能**: 发送消息失败（可能是测试环境缺少 API Key 配置导致）

**问题描述**:
控制台报错 `Chat error: TypeError: network error`

**说明**:
这可能是测试环境没有配置有效的 API Key 导致的，不一定是代码 bug。需要在有正确 API Key 配置的环境下进一步验证。

---

## 四、已验证修复的问题

### ✅ Export 会话导出功能 — 已修复

**之前的问题**:
1. 前端 `api.session.export()` 使用 GET，后端只接受 POST → 405 Method Not Allowed
2. 中文标题会话导出时 `Content-Disposition` header 编码错误 → UnicodeEncodeError

**当前状态**: ✅ 已修复并验证通过

**验证结果**:
- 中文标题会话点击 Export 按钮
- 绿色 Toast 提示 "Session exported" ✅
- 导出功能正常工作

**修复位置**:
- 前端: [api.ts:42,53](file:///Users/mac/AI/CScode/src/cscode/web/src/lib/api.ts#L42-L53) — 添加 `{ method: 'POST' }`
- 后端: [app.py:1241-1247](file:///Users/mac/AI/CScode/src/cscode/server/app.py#L1241-L1247) — RFC 5987 编码 `filename*=UTF-8''`

---

## 五、功能正常的模块

| 模块 | 状态 | 备注 |
|------|------|------|
| 侧边栏打开/关闭 | ✅ 正常 | Toggle menu 按钮工作正常 |
| 新建会话 | ✅ 正常 | Create new session 按钮正常 |
| 过滤/排序/刷新 | ✅ 正常 | 三个按钮均可点击 |
| Plan/Build 模式切换 | ✅ 正常 | 单选按钮状态正确切换 |
| 输入框 + 发送按钮 | ✅ 正常 | 输入文字后发送按钮变为可用 |
| Attach file 按钮 | ✅ 正常 | 可点击 |
| Open terminal 按钮 | ✅ 正常 | 终端面板正常打开 |
| 设置页面 | ✅ 正常 | 页面加载正常，有 Save 按钮 |
| 帮助页面 | ✅ 正常 | 页面加载正常，有内容 |
| 多会话创建 | ✅ 正常 | 连续创建 3+ 会话正常 |
| 会话删除按钮 | ✅ 正常 | hover 后显示 Delete 按钮 |
| 会话导出 (Export) | ✅ 正常 | 中文标题也能正常导出 |

---

## 六、截图证据

所有测试截图保存在: `dogfood-output/screenshots/`

| 截图文件 | 说明 |
|----------|------|
| 01-home.png | 首页初始状态 |
| 02-sidebar-open.png | 侧边栏打开状态 |
| 03-new-session.png | 新建会话后 |
| 04-after-export.png | 点击 Export 后（绿色成功提示） |
| 05-chat-input.png | 聊天输入框测试 |
| 06-attach-file.png | Attach file 按钮测试 |
| 07-terminal.png | 终端面板 |
| 08-settings.png | 设置页面 |
| 09-after-save-settings.png | 保存设置后 |
| 10-help.png | 帮助页面 |
| 11-filter-sort-refresh.png | 过滤/排序/刷新测试 |
| 12-multi-sessions.png | 多会话创建 |
| 13-keyboard-test.png | 键盘快捷键测试 |
| 15-delete-clicked.png | 删除按钮测试 |

---

## 七、测试脚本

测试脚本位置: [dogfood-output/full_test.py](file:///Users/mac/AI/CScode/dogfood-output/full_test.py)

测试结果 JSON: [dogfood-output/test-results.json](file:///Users/mac/AI/CScode/dogfood-output/test-results.json)

---

## 八、建议优先级

### 高优先级 (立即修复)
1. **P1-1**: 修复 Share API 路径重复前缀问题 — 影响分享功能可用性
2. **P1-2**: 排查 Share API 500 错误 — 可能是全局变量未初始化

### 中优先级
3. **P2-1**: 验证聊天发送消息在有效 API Key 下是否正常

### 后续改进建议
- 增加单元测试覆盖 Share API
- 增加 E2E 测试覆盖所有按钮的 happy path
- 建议在 CI 中加入 Playwright E2E 测试

---

*报告生成时间: 2026-07-09*
