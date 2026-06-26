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
- Worktree isolation: use git worktrees for parallel agents
- Cost management: stop at $15 USD
- Stop: completed | max iterations | cost exceeded | human needed | error
## CScode Verification (Ratchet Principle)
Before completion, verify: pytest tests/ && mypy src/ && ruff check src/
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
