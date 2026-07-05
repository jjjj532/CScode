# CScode DMG 打包检查清单

## 版本号统一（打包前必须全部一致）

以下 **7 处** 必须统一为同一版本号，漏一个 DMG 版本就不对：

| # | 文件 | 字段 |
|---|------|------|
| 1 | `src/cscode/__init__.py` | `__version__` |
| 2 | `src/cscode/server/app.py` | `FastAPI(version=...)` |
| 3 | `src/cscode/mcp/client.py` | `"version"` |
| 4 | `src/cscode/mcp/server.py` | `"version"` |
| 5 | `desktop/src-tauri/tauri.conf.json` | `"version"` |
| 6 | `desktop/src-tauri/Cargo.toml` | `[package] version` |
| 7 | `scripts/build.sh` | 所有硬编码版本号 |

验证命令：
```bash
rg "0\.2\.\d+" src/ desktop/src-tauri/ scripts/ --type py --type json --type toml --type sh | grep -v node_modules | grep -v playwright
```

## 打包前清理（必须彻底）

```bash
# 卸载旧镜像
diskutil unmount force /Volumes/CScode* 2>/dev/null || true
# 删除系统旧应用
rm -rf /Applications/CScode.app
# 删除所有编译缓存
rm -rf desktop/src-tauri/target
rm -rf desktop/src-tauri/.dmg-background
rm -rf desktop/dist
rm -rf desktop/src-tauri/web-dist
rm -rf desktop/src-tauri/python
rm -f dist/*.dmg dist/cscode-desktop
```

## 打包命令

```bash
source .venv/bin/activate
bash scripts/build-desktop.sh
```

## 打包后验证

```bash
hdiutil attach dist/CScode_*.dmg -mountpoint /tmp/dmgcheck -nobrowse
# 版本
defaults read /tmp/dmgcheck/CScode.app/Contents/Info CFBundleShortVersionString
# Python 运行时版本
PYTHONPATH=/tmp/dmgcheck/CScode.app/Contents/Resources/python python3 -c "from cscode import __version__; print(__version__)"
# Applications 快捷方式
ls -la /tmp/dmgcheck/Applications
hdiutil detach /tmp/dmgcheck -force
```

## 图标生成

源图: `截屏2026-06-17 16.15.17.png` (134x122, 深蓝底色 #1F375D)
- 背景色必须保持深蓝 (31,55,93)，不能透明不能白色
- 缩放时用深蓝色填充空白区域
- 输出: `desktop/src-tauri/icons/` 下 32/128/256 PNG + cscode.icns

## 独立二进制图标

```bash
fileicon set dist/cscode-desktop desktop/src-tauri/icons/cscode.icns
```

---

# CI/CD (GitHub Actions) — 三平台构建

## 触发方式

推送 `v*` tag 或手动触发 `workflow_dispatch`。

## CI 工作流文件

`.github/workflows/build.yml` — 一个 job 用 matrix 跑三平台，再加一个 `create-release` job。

## 构建步骤

1. **Python venv**: `pip install -e .` 安装项目自身（不含 dev 依赖）
2. **React 前端**: `src/cscode/web/` 下 `vite build`
3. **Spinner 页**: 生成 `desktop/dist/index.html`（Tauri 需要的 frontendDist）
4. **Python 依赖打包**:
   - `pip install --target=TMPDIR .` 安装到临时目录
   - 删除 `__pycache__`、`bin/`（保留 `playwright/driver` 确保 browser 工具开箱即用）
   - Python zipfile 打包为 `site-packages.zip`（避免 Tauri build script 枚举 4426 个文件崩溃）
5. **源码打包**: 复制 `src/cscode/**/*.py` + `web/dist` 到 `resources/python/`
6. **资源验证**: 检查 `site-packages.zip`、`app.py`、`index.html` 存在
7. **npm ci**: `desktop/` 下安装 Tauri npm 依赖
8. **构建**:
   - macOS: `npx tauri build --verbose --bundles app`
   - Linux: `npx tauri build --verbose` → 自动 deb
   - Windows: `cargo fetch` → `cargo build --release`（重试3次）→ `npx tauri build --verbose --bundles nsis`
9. **DMG 创建** (macOS): 用 `hdiutil` 从 `.app` 创建 DMG
10. **上传 artifacts**: `desktop/src-tauri/target/release/bundle/`
11. **create-release**: 用 `softprops/action-gh-release` 发布到 GitHub Release

## 已知痛点 & 解决方案（历史教训！）

### 1. Windows PDB 文件名冲突

**症状**: `cargo build --release` 退出码 101（Rust panic），日志末尾显示 `output filename collision at ...cscode_desktop.pdb`

**原因**: `[lib] name = "cscode_desktop"` 和 `[package] name = "cscode-desktop"` 在 Windows 上生成同名 `.pdb` 文件

**修复**: 重命名 lib target，避免与 package name 冲突
```toml
# Cargo.toml
[lib]
name = "cscode_app"  # 不能是 cscode_desktop
```
同时更新 `main.rs` 中的引用：`cscode_desktop::run()` → `cscode_app::run()`

### 2. Windows 缺少 icon.ico

**症状**: taigi-build 报错 `icons/icon.ico not found; required for generating a Windows Resource file`

**原因**: Windows PE 需要 `.ico` 文件嵌入资源信息，Tauri 在 `tauri-build` 阶段自动查找 `icons/icon.ico`

**修复**: 确保 `desktop/src-tauri/icons/icon.ico` 存在（用 PIL 从 PNG 生成），不需要在 `tauri.conf.json` 的 icon 列表中声明

### 3. lib.rs Windows 代码类型错误

**症状**: `error[E0308]: mismatched types at src\lib.rs:46:114`

**原因**: `port` 是 `u16`，直接放入 `.args(["/C", "...", port])` 数组导致类型不匹配

**修复**: 用 `format!()` 把 port 格式化到命令字符串中

### 4. 资源文件过多导致 Windows 构建脚本崩溃

**症状**: Tauri build script 进程退出码非 0，原因是 `cargo:rerun-if-changed=` 枚举了 4426 个文件

**原因**: `pip install --target=resources/` 装到 `resources/python/` 下产生海量文件

**修复**: 用 `site-packages.zip` 替代 flat 目录，Python 原生支持从 zip 导入

### 5. Windows 网络超时下载 crates

**症状**: `spurious network error (3 tries remaining): [55] Failed sending data to the peer`

**修复**: `cargo fetch` 预下载 + 重试 3 次循环

### 6. tee 在 Windows 不可用

**原因**: Git Bash on Windows 没有 `tee`

**修复**: 用 `>` 重定向到文件 + `cat`/`head` 显示内容，或用 `&& rc=0 || rc=$?` 模式捕获退出码

### 7. macOS DMG 创建

**注意**: DMG 创建在 CI 上对磁盘空间敏感，如果构建产物过大可能 `hdiutil create` 失败

**修复**: 确保 `cp -rf` 目标有足够空间，或考虑直接用 Tauri 自身的 bundler 创建 DMG

## 图标清单

Windows 不需要 `.ico` 在 tauri.conf.json 的 icon 数组中，但文件必须存在于 `icons/icon.ico`。如果缺失，tauri-build 会在 Windows 上报错。

```bash
# 生成 icon.ico（需要 Pillow）
python3 -c "
from PIL import Image
img = Image.open('desktop/src-tauri/icons/128x128.png')
img.save('desktop/src-tauri/icons/icon.ico', format='ICO', sizes=[(32,32),(64,64)])
"
```

---
# Loop Engineering Rules (Based on Addy Osmani Best Practices)
## Core Loop Principles
- Maker/Checker: write code vs verify must be different agents
- State persistence: track in .opencode/loop-state/
- Worktree isolation: use git worktrees for parallel agents (2+ concurrent tasks must)
- Cost management: stop at $15 USD
- Stop: completed | max iterations | cost exceeded | human needed | error

## Ratchet Rules (Archived from REVIEW)
- No silent `except Exception: pass` — must `logger.exception()` at minimum
- Every `except Exception` needs a comment explaining why it's intentional
- REVIEW findings must produce new test or AGENTS.md rule, not just one-time fix
- Session callback failures must never be silently swallowed

## CScode Verification (Ratchet Principle)
Before completion, verify: pytest tests/ && mypy src/ && ruff check src/

## WebSocket 系统注意事项（Ratchet Rules）
- WebSocket 状态检查用 `WebSocketState.DISCONNECTED` 比较，不要用 `client_state.closed`（后者不存在）
- `_event_bridge_once` 没有 `break` — 必须转发 subscribe generator 的所有事件，不能只取第一个
- WebSocketManager 测试用 `MockWebSocket`/`MockWebSocketQueue` 辅助类，`client_state` 设置 `WebSocketState` 枚举值
- `WebSocketManager.__init__` 接受可选的 `event_store`，用于事件桥接
- WebSocket endpoint 在 `api_router` 上注册为 `@api_router.websocket("/ws")`，路径为 `/api/ws`

## Workspace 系统注意事项（Ratchet Rules）
- `from __future__ import annotations` + 类方法名为 `list` → 字符串标注 `list[Workspace]` 会解析为类方法而非内置 `list`。用 `typing.List[Workspace]` 替换。
- Workspace CRUD endpoint 用 `api_router` 前缀 `/api/workspaces`，遵循已有的 `CredentialStore`/`ShareStore` 模式
- Workspace 使用简单 SQLite 表（非 EventStore），因为 workspace 是元数据而非事件溯源

## Anti-Patterns to Avoid
- Same agent writes and reviews code
- No state file for resume
- Unlimited iterations without cost controls
- Skip tests before claiming completion

---
# 项目概述
CScode 是一个 AI 编程助手，支持 Claude Code、Cursor 等主流 AI 编码工具的本地化部署。

## 技术栈
- Python 后端: FastAPI, Textual TUI, SQLite + Event Sourcing
- 前端: React 18 + TypeScript + Vite + Tailwind CSS
- 桌面端: Tauri v2 + Rust
- 测试: pytest + pytest-asyncio
- 代码质量: ruff + mypy

## 开发命令
- 桌面端开发: npm run tauri dev
- 桌面端打包: bash scripts/build- desktop.sh
- Python 测试: pytest tests/
- 类型检查: mypy src/
- 代码检查: ruff check src/
- 代码格式化: ruff format src/

## 目录结构
- src/cscode/ - 核心 Python 代码
- desktop/ - Tauri 桌面端
- tests/ - 单元测试
- scripts/ - 构建脚本

## 编码规范
- Python: 必须类型标注，禁止 Any
- TypeScript: 严格模式
- 先写测试再写代码 (TDD)
- 提交前: pytest tests/ && mypy src/ && ruff check src/

## PTY 系统注意事项（Ratchet Rules）
- `os.read()` on non-blocking PTY fd 必须用 sync os.read + await asyncio.sleep() backoff，不要用 asyncio.to_thread()
- Shell echoes command text containing the marker — marker 检测必须搜索 `\nMARKER`（行首匹配），不能子串匹配
- PTY fd 在 create_subprocess_exec 前设置 set_blocking(False)，slave fd 传给子进程后 parent 关闭
- `os.openpty()` 返回 (master_fd, slave_fd) pair，slave_fd 在子进程中作为 stdin/stdout/stderr

## Sync 系统注意事项（Ratchet Rules）
- `Event.id` 必须放在 dataclass 字段最后（`id: int = 0`），避免破坏位置参数兼容性（`Event("agg", 1, "type", data, t)`）
- `scan_events_global()` 使用 `id > ?` 而非 `id >= ?` 作为 after_id 过滤条件，避免重复拉取
- SyncEngine 提供两种传输模式：direct (EventStore-to-EventStore) 用于测试，HTTP (REST API) 用于生产
- Sync dedup 依赖 events 表的 `UNIQUE(aggregate_id, seq)` 约束，而非应用层去重
- `_push_direct`/`_pull_direct` 在 append 失败时静默跳过（预期行为：duplicate key），其他异常也应该跳过

## Session Instruction 系统注意事项（Ratchet Rules）
- `SessionV2.set_instruction()` / `delete_instruction()` 必须通过事件溯源（instruction.set / instruction.deleted），不能直接修改 state
- `build_context()` 在有 `state.instruction` 时自动注入为第一个 system message，位置在 epoch snapshot 之后（如果存在）
- Instruction API 端点（GET/PUT/DELETE）遵循现有 `@api_router` 模式，异常处理同上
- Instruction 必须跨 session load 持久化（通过 EventStore）

## Session List 系统注意事项（Ratchet Rules）
- `GET /api/sessions` 必须从 `event_sequences` 表获取 aggregate ID 列表，而非直接从 EventStore 扫描（后者无法列出无事件但已注册的 aggregate）
- 分页参数 `limit` / `offset` 直接在 SQL 层面实现（`ORDER BY aggregate_id LIMIT ? OFFSET ?`），不在 Python 层面过滤
- 响应包含 `status`、`message_count`、`event_count` 等增强字段，按需从 SessionState 读取
- 每个 session 的 load 用 try/except 包裹，单个 session 失败不影响返回列表

## Session Run State 系统注意事项（Ratchet Rules）
- `SessionState` 新增 `run_status` / `run_error` 字段必须在构造器中显式传入默认值，避免投影状态未覆盖
- `SessionV2.mark_run_error()` 接受可选的 `error` 参数，其他 run state 方法无参数
- API 端点 `GET/PUT /sessions/{id}/run-state` 接受 `dict[str, str]` 而非 Pydantic 模型（与现有端点风格一致）
- 默认初始状态为 `idle`，非 `running`

## Config Reference 系统注意事项（Ratchet Rules）
- Config metadata (`CONFIG_KEY_META`) 定义在 `config.py` 中，以静态字典形式存在，与 Config dataclass 字段一一对应
- API 端点 `GET /config/reference` 读取 `CONFIG_KEY_META` 并转换为列表返回，不做运行时反射
- 描述信息保持简短、面向终端用户

## Application Tools 系统注意事项（Ratchet Rules）
- `APPLICATION_TOOLS` 作为不可变集合导出（`Final[set[str]]`），对外只读
- `is_application_tool()` 是纯函数，无副作用，可被任何权限模块调用
- 默认集合包含只读工具（read, grep, glob, ls），不含写入/执行工具
- API 端点 `GET /tools/application` 返回排序列表，不可修改集合

## Session Overflow 系统注意事项（Ratchet Rules）
- `SessionV2.check_overflow()` 返回字典而非抛出异常，无副作用
- overflow 检测基于 `len(state.messages)` 计数，不做 token 估算
- 阈值默认 100，可通过 `threshold` 参数覆盖
- `near_overflow` 阈值为 `int(threshold * 0.8)`

## Session Retry 系统注意事项（Ratchet Rules）
- `SessionV2.get_last_prompt()` 从后向前扫描 messages，返回最后一条 USER role 消息的 text 内容
- `SessionV2.retry()` 无参数，调用 `get_last_prompt()` + `self.prompt(last)` 实现
- `role` 属性是字符串（`"user"` / `"assistant"`），不是 `MessageRole` 枚举实例
- 空 session 的 `get_last_prompt()` 返回 `None`，`retry()` 返回空列表

## Session Reminders 系统注意事项（Ratchet Rules）
- 提醒通过 `session.reminder_added` 事件实现事件溯源，不设独立删除/清除事件（简化实现）
- `SessionState.reminders` 使用 `field(default_factory=list)` 而非元组，因为 reminder 列表是可变增长的
- `add_reminder()` 使用 `time.time_ns()` 生成唯一 ID，不依赖数据库自增
- 当前实现只支持添加和查询，不支持删除（未来可通过 `session.reminder_removed` 事件扩展）

## Config tui-cwd 系统注意事项（Ratchet Rules）
- `Config` 新增字段必须在 dataclass 字段列表和 `CONFIG_KEY_META` 字典中同时添加，缺一不可
- `CONFIG_KEY_META` 的 `"type"` 字段使用字符串描述（`"string"` / `"int"` / `"float"`），非 Python 类型对象
- `from_dict()` 默认将空字符串跳过（`if isinstance(v, str) and not v: continue`），因此 `tui_cwd` 的空字符串默认值会正确保留

## External Directory 系统注意事项（Ratchet Rules）
- `ExternalDirectoryStore` 是纯内存存储，不依赖数据库，适合轻量级权限管理
- `is_approved()` 使用 `normalized.startswith(prefix)` 匹配子路径，`prefix` 必须包含尾部 `/` 确保目录边界正确
- `_normalize_path()` 调用 `os.path.abspath()` 解析为绝对路径并去除尾部斜杠（根目录 `/` 除外）
- 添加重复路径时抛出 `ValueError`，API 层将其转换为 409 响应

## Config tui-host-attention 系统注意事项（Ratchet Rules）
- 与 tui-cwd 模式相同：Config 类加字段 + CONFIG_KEY_META 加条目，两步缺一不可

## mcp-websearch 系统注意事项（Ratchet Rules）
- `APPLICATION_TOOLS` 中的名称必须与工具类的 `name` 属性完全一致（如 `"websearch"` 而非 `"web_search"`）
- 名称不一致会导致 `is_application_tool()` 返回 False，触发不必要的权限确认
- WebSearchTool 有 v1（`tools/websearch.py`）和 v2（`tools2/websearch.py`）两个版本，名称必须同步对齐

## Control-Plane 系统注意事项（Ratchet Rules）
- `SessionV2.create()` 直接构造 SessionState（绕过 projector），新增字段必须在 `SessionState()` 构造器中显式传入，不能只靠事件追加
- `EventStore.scan_events_by_type()` 用于跨 aggregate 的事件扫描，适用于 workspace→session 映射等跨聚合查询
- `WorktreeManager._parse_line()` 处理非 porcelain 格式，bare repo 无 hash 字段需先判断 `(bare)` 再赋 hash
- 生产代码优先使用 `--porcelain` 格式（`_parse_output()`），`_parse_line()` 仅为辅助/测试用
- `WorkspaceStore.list_sessions()` 使用事件溯源方式（scan_events_by_type）而非 SQL 直接查询
