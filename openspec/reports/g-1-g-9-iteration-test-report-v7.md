# G-8 + G-9 迭代测试报告（迭代 6）

> **日期**: 2026-08-20（v7 — 迭代 6 G-8 SDK 生成客户端 + G-9 前端 sync 竞态处理 + 版本统一 bump 0.4.0）
> **Spec**: `openspec/specs/cscode-iteration-upgrade.md` §6.1, §6.2 + AGENTS.md 版本清单
> **结论**: **G-8 + G-9 验收全部通过**，P2 两项交付完成，G-1~G-9 差距全部闭环（远期项除外）

---

## 1. 测试范围

### 迭代 6 — G-8 SDK 生成客户端（16 项 Python + 验证门禁）

| 文件 | 角色 |
|------|------|
| `scripts/gen_api.py` | 新增：OpenAPI → TS 端点表生成器（纯函数可测） |
| `scripts/gen-api.sh` | 新增：生成器薄壳（对齐 spec 命名） |
| `web/src/lib/api/generated/endpoints.ts` | 生成物：100 端点 + 7 手工补录别名 |
| `web/src/lib/api.ts` | 改造：硬编码路径 → ENDPOINTS/MANUAL_ENDPOINTS 解析 |
| `tests/test_gen_api.py` | 新增：16 个测试（命名映射/端点表/TS 渲染/幂等） |

### 迭代 6 — G-9 前端 sync 竞态处理（7 项 jest）

| 文件 | 角色 |
|------|------|
| `web/src/hooks/useSync.ts` | 新增：sync 状态机（idle/syncing/complete/error）+ 串行化 |
| `web/src/components/SyncPanel.tsx` | 改造：接入 useSync，按钮绑定状态 + ✓ Synced / Sync failed 指示 |
| `web/__tests__/useSync.test.ts` | 新增：7 个测试（状态机/串行化/错误保持） |

### 版本统一 bump（0.3.6 → 0.4.0）

| # | 文件 | 验证 |
|---|------|------|
| 1 | `src/cscode/__init__.py` `__version__` | 0.4.0 ✓ |
| 2 | `src/cscode/server/app.py` `FastAPI(version=)` | 0.4.0 ✓ |
| 3 | `src/cscode/mcp/client.py` | 0.4.0 ✓ |
| 4 | `src/cscode/mcp/server.py` | 0.4.0 ✓ |
| 5 | `desktop/src-tauri/tauri.conf.json` | 0.4.0 ✓ |
| 6 | `desktop/src-tauri/Cargo.toml` + Cargo.lock（cscode-desktop 条目） | 0.4.0 ✓ |
| 7 | `scripts/build.sh` 全部硬编码 | 0.4.0 ✓ |

残留 `0.3.6` 均为第三方依赖（field-offset/tauri-winres/cssom），非项目版本。

---

## 2. 验收标准逐条对照

### 2.1 G-8: SDK 生成客户端（§6.1.4，6/6 PASS）

| # | 验收标准 | 结果 | 证据 |
|---|----------|------|------|
| 1 | `GET /openapi.json` 可访问 | **PASS** | `app.openapi()` 返回 74 路径 + 100 operations（实测 "Generated 100 endpoints"） |
| 2 | `gen-api.sh` 生成 endpoints.ts（可重复 + 幂等） | **PASS** | 两次运行 MD5 一致 `31f2cdd825a18c11c5d740d38f3abea9`；测试 test_render_is_deterministic |
| 3 | api.ts 无硬编码路径 | **PASS** | `rg "['\"]/api/" api.ts` 输出 0 行；全部经 ENDPOINTS/MANUAL_ENDPOINTS + endpointPath() 解析 |
| 4 | 单数别名保留 + 生成不覆盖 | **PASS** | MANUAL_ENDPOINTS 段含 7 个别名（listSessionAlias 等），位于生成段之后，重新生成 MD5 不变 |
| 5 | tsc --noEmit + npm test 全过 | **PASS** | tsc 0 错误；jest 195 passed（+G-9 后 202） |
| 6 | 路径漂移检测机制 | **PASS** | 生成段 100 端点 + 补录段 7 别名；新增路径重新生成即出现，删除路径补录段仍在（运行时 404） |

**关键设计决策**：不采用全量 OpenAPI generator——74 端点中大量 `dict[str, Any]` 无 response_model，全量生成产出 `any` 类型违背"无 Any 泄漏"；改为轻量端点表 + 门面保留手写类型/重试逻辑（符合 spec"手写逻辑保留在门面层"）。

### 2.2 G-9: 前端 sync 竞态处理（§6.2.4，5/5 PASS）

| # | 验收标准 | 结果 | 证据 |
|---|----------|------|------|
| 1 | push 期间 syncing → complete + 刷新事件 | **PASS** | test_push_posts_and_refreshes_events_on_completion：push 后 2 次 fetch（push + 拉取） |
| 2 | refresh 期间 syncing → complete | **PASS** | test_status_is_syncing_while_request_in_flight |
| 3 | 串行化：busy 期间重复调用忽略 | **PASS** | test_serialization_repeated_refresh_single_fetch（fetch 计数 = 1）+ test_push_serialization（double push = 1 次） |
| 4 | 失败 → error + 保留最后成功时间 | **PASS** | test_error_state_keeps_last_successful_sync_time |
| 5 | SyncPanel 按钮绑定状态 + tsc/jest 全过 | **PASS** | SyncPanel.tsx disabled=syncing + ✓/失败指示；tsc 0 + 202 jest |

**现状修正**（spec 原文过时部分）：spec 假设"SyncPanel 有拉取/推送，无 sync.status==='complete' 再 fork 保护"——实测前端**无 fork 功能**、无 useSync.ts、后端 sync 端点无 status 概念。G-9 交付调整为状态机基础设施 + 串行化，为未来 fork 提供 `sync.status` 检查点。

---

## 3. 代码质量门禁

| 门禁 | 结果 |
|------|------|
| `mypy scripts/gen_api.py --strict` | **Success: no issues found**（0 errors） |
| `ruff check scripts/gen_api.py` | **All checks passed** |
| `pytest tests/test_gen_api.py` | **16 passed** |
| `npx tsc --noEmit`（web） | **0 errors** |
| `npx jest --ci`（web） | **202 passed / 25 suites**（+7：G-9 useSync） |
| `python -c "from cscode import __version__"` | 0.4.0 ✓ |
| tauri.conf.json version | 0.4.0 ✓ |

---

## 4. 向后兼容性

| 检查项 | 结果 |
|--------|------|
| G-8: api.ts 导出形状不变（api.session/sessions/config/chat/health/permissionRules） | 兼容（7 处 import 组件无需改动） |
| G-8: 复数/单数 session 双端点均保留 | 兼容 |
| G-8: 重试/错误处理逻辑（request 封装）不变 | 兼容 |
| G-9: SyncPanel 导出签名不变（无 props） | 兼容 |
| G-9: 事件渲染逻辑（slice(-20).reverse()）保留 | 兼容 |
| 版本: Python/JS 运行时读取一致 | 兼容 |

---

## 5. 总结

| 维度 | G-8 | G-9 |
|------|-----|-----|
| 验收标准 | 6/6 | 5/5 |
| 专项测试 | 16 pytest | 7 jest |
| 源文件 | 3（gen_api/gen-api.sh/endpoints.ts 生成物 + api.ts 改造） | 2（useSync + SyncPanel） |
| mypy --strict | 0 | n/a（TS） |
| tsc --noEmit | 0 | 0 |
| 向后兼容 | ✓ | ✓ |
| 核心技术 | OpenAPI → 端点表生成器 + 门面 | 状态机 + busyRef 串行化 |

**G-8 + G-9 验收全部通过（11/11 验收标准），G-1~G-9 全部差距闭环。版本统一 bump 0.4.0（7 处一致）。P0（4 项）+ P1（3 项）+ P2（2 项）= 9/9 差距交付完成，spec §7 任务分解的迭代 1-6 全部落地。**
