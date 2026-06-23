# CScode Windows 打包完整指南

## 概述

本文档描述如何在 Mac 电脑上通过 GitHub Actions 自动构建 Windows 版本的 CScode 桌面应用。

**核心方案**：嵌入式 Python 3.11 打包（Embedded Python Bundling）

---

## 文件结构

```
D:\AI\CScode\
├── scripts/
│   ├── setup-embedded-python.ps1    # 嵌入式 Python 下载脚本
│   └── build-windows.ps1            # Windows 完整构建脚本
├── .github/workflows/
│   └── build-windows.yml            # GitHub Actions 工作流
├── desktop/src-tauri/
│   ├── tauri.conf.json              # Tauri 配置（已更新）
│   └── src/lib.rs                   # Rust 代码（已更新）
└── docs/
    └── WINDOWS_BUILD_GUIDE.md       # 本文档
```

---

## 方案原理

### 为什么选择嵌入式 Python？

| 方案 | 优点 | 缺点 |
|------|------|------|
| 源码打包 (PYTHONPATH) | 体积小 | 二进制依赖（Playwright 等）不工作 |
| venv 打包 | 依赖隔离 | 体积大，需要 Python 运行时 |
| **嵌入式 Python** | **零依赖、完整兼容** | 体积 30-40MB |

嵌入式 Python 包含完整的 CPython 解释器，支持所有 C 扩展，用户无需安装任何软件。

### 构建流程

```
1. 下载 Python 3.11 嵌入式包 (python-3.11.9-embed-amd64.zip)
2. 安装 pip 和项目依赖到嵌入式目录
3. 复制 Python 源代码到 site-packages
4. 构建 React 前端
5. Tauri 构建 NSIS 安装程序
```

---

## GitHub Actions 工作流

### 触发条件

- push 到 `main` 或 `master` 分支
- 手动触发（workflow_dispatch）

### 构建步骤详解

```yaml
jobs:
  build-windows:
    runs-on: windows-2022  # Windows Server 2022 runner

    steps:
      # 1. 基础环境
      - Setup Python 3.12 (用于引导)
      - Setup Node 22
      - Setup Rust (x86_64-pc-windows-msvc)
      - Enable MSVC toolchain

      # 2. 嵌入式 Python 设置
      - setup-embedded-python.ps1
      - 安装 pip 依赖到嵌入式目录
      - 复制 Python 源代码

      # 3. 前端构建
      - npm ci && npx vite build

      # 4. Tauri 构建
      - npm ci (desktop 目录)
      - npx tauri build --bundles nsis

      # 5. 上传产物
      - cscode-windows-nsis (安装程序)
      - cscode-windows-exe (独立可执行文件)
```

---

## 关键文件内容

### 1. setup-embedded-python.ps1

```powershell
# 下载 Python 3.11 嵌入式包
$pythonUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"

# 解压到 desktop/src-tauri/embedded-python/
# 修改 python311._pth 启用 site-packages
# 安装 pip
```

### 2. build-windows.ps1

```powershell
# 主构建脚本，执行以下步骤：
# Step 1: 设置嵌入式 Python
# Step 2: 安装依赖
# Step 3: 打包 Python 源码
# Step 4: 构建 React 前端
# Step 5: 安装 Tauri 依赖
# Step 6: 构建 Tauri 应用
```

### 3. build-windows.yml

```yaml
# GitHub Actions 工作流
# 使用 windows-2022 runner
# 调用 PowerShell 脚本完成构建
```

### 4. tauri.conf.json 变更

```json
{
  "bundle": {
    "resources": [
      "web-dist/**/*",
      "python/**/*",
      "embedded-python/**/*"  // 新增
    ]
  }
}
```

### 5. lib.rs 变更

```rust
// 新增策略1：嵌入式 Python (Windows)
if let Some(dir) = resource_dir {
    let embedded_python = dir.join("embedded-python");
    let embedded_exe = embedded_python.join("python.exe");
    if embedded_exe.exists() {
        // 使用嵌入式 Python 启动
    }
}

// 保留策略2：源码打包 (macOS/Linux)
// 保留策略3：开发模式 (fallback)
```

---

## Mac 电脑操作步骤

### 首次配置

```bash
# 1. 克隆仓库
git clone <your-repo-url>
cd CScode

# 2. 确保以下文件存在
ls scripts/setup-embedded-python.ps1
ls scripts/build-windows.ps1
ls .github/workflows/build-windows.yml

# 3. 提交代码
git add .
git commit -m "Add embedded Python Windows build support"
git push origin main
```

### 触发构建

```bash
# 方法1：push 自动触发
git push origin main

# 方法2：手动触发
# 访问 GitHub 仓库 -> Actions -> Build Windows Installer -> Run workflow
```

### 下载构建产物

```bash
# 1. 访问 GitHub 仓库 -> Actions
# 2. 点击最新的构建
# 3. 在 Artifacts 部分下载：
#    - cscode-windows-nsis: NSIS 安装程序 (~30-40MB)
#    - cscode-windows-exe: 独立可执行文件 (~15MB)
```

---

## 版本管理

### 版本号位置（7处必须一致）

| # | 文件 | 字段 |
|---|------|------|
| 1 | `src/cscode/__init__.py` | `__version__` |
| 2 | `src/cscode/server/app.py` | `FastAPI(version=...)` |
| 3 | `src/cscode/mcp/client.py` | `"version"` |
| 4 | `src/cscode/mcp/server.py` | `"version"` |
| 5 | `desktop/src-tauri/tauri.conf.json` | `"version"` |
| 6 | `desktop/src-tauri/Cargo.toml` | `[package] version` |
| 7 | `scripts/build-windows.ps1` | `$PythonVersion` |

### 版本检查

```bash
# 查找所有版本号
grep -r "0\.2\." src/ desktop/src-tauri/ scripts/ --include="*.py" --include="*.json" --include="*.toml"
```

---

## 常见问题

### Q1: GitHub Actions 构建失败

**原因**：Windows runner 环境问题

**解决**：
1. 检查 Actions 日志
2. 确认 Rust 工具链安装成功
3. 确认 MSVC 编译器可用

### Q2: 嵌入式 Python 依赖安装失败

**原因**：pip 未正确安装到嵌入式目录

**解决**：
```bash
# 手动测试
desktop\src-tauri\embedded-python\python.exe -m pip install --target=desktop\src-tauri\embedded-python\Lib\site-packages click
```

### Q3: NSIS 安装程序体积过大

**原因**：包含完整的 Python 标准库

**优化**：
- 去除不需要的标准库模块
- 使用 UPX 压缩
- 排除测试文件

### Q4: Mac 上无法直接构建 Windows

**正确方式**：使用 GitHub Actions（云端构建）

**不支持**：在 Mac 上本地构建 Windows 可执行文件

---

## 技术细节

### 嵌入式 Python 目录结构

```
desktop/src-tauri/embedded-python/
├── python.exe                    # Python 解释器
├── python311._pth                # 路径配置
├── python311.dll                 # 运行时库
├── Lib/
│   ├── site-packages/            # 第三方包
│   │   ├── cscode/               # 项目源码
│   │   ├── click/
│   │   ├── fastapi/
│   │   ├── uvicorn/
│   │   └── ...
│   └── ...                       # 标准库
```

### Tauri 资源打包

```json
{
  "bundle": {
    "resources": [
      "embedded-python/**/*"  // 完整的嵌入式 Python
    ]
  }
}
```

打包后资源位于：
- Windows: `CScode.exe` 同级目录的 `resources/` 文件夹

### Rust 启动逻辑

```rust
// 优先级1：嵌入式 Python (Windows)
if embedded-python/python.exe exists {
    使用嵌入式 Python 启动
}

// 优先级2：源码打包 (macOS/Linux)
if python/cscode/server/app.py exists {
    使用 PYTHONPATH 启动
}

// 优先级3：开发模式
if src/cscode/server/app.py exists {
    使用本地 Python 启动
}
```

---

## 依赖清单

### Python 依赖

```
click>=8.1.0
rich>=13.0.0
httpx>=0.27.0
aiosqlite>=0.20.0
pyyaml>=6.0
textual>=0.52.0
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
pydantic>=2.0
python-multipart>=0.0.12
python-docx>=1.2.0
openpyxl>=3.1.0
playwright>=1.60.0
```

### 系统依赖

- Node.js 22+
- Rust (x86_64-pc-windows-msvc)
- MSVC 工具链

---

## 构建产物

| 文件 | 大小 | 用途 |
|------|------|------|
| `cscode_0.2.16_x64-setup.exe` | ~30-40MB | NSIS 安装程序 |
| `cscode-desktop.exe` | ~15MB | 独立可执行文件 |

---

## 联系方式

如有问题，请检查：
1. GitHub Actions 日志
2. 本文档的常见问题部分
3. 项目 README

---

*最后更新：2026-06-23*
