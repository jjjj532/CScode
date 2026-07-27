# CScode v0.3.4 桌面应用端到端测试报告

**测试时间**：2026-07-22  
**测试方式**：安装 DMG → 启动桌面应用 → 真实用户模拟  
**测试版本**：v0.3.4（DMG 62MB）

---

## 1. 测试执行步骤

### 1.1 DMG 安装

```bash
# 挂载 DMG
hdiutil attach dist/CScode_0.3.4_x86_64.dmg -mountpoint /tmp/cscode-dmg-test -nobrowse

# 验证内容
ls -la /tmp/cscode-dmg-test/
# 输出:
# drwxr-xr-x   CScode.app
# lrwxr-xr-x   Applications -> /Applications
```

✅ **安装步骤通过**

### 1.2 应用启动

```bash
# 启动桌面应用
/Applications/CScode.app/Contents/MacOS/cscode-desktop
```

**日志输出**：
```
Checking for PyInstaller binary: /Applications/CScode.app/Contents/Resources/resources/cscode-backend/cscode-backend
Started server from legacy bundled resources
/usr/local/opt/python@3.14/bin/python3.14: No module named cscode
```

❌ **后端启动失败**

---

## 2. 发现的打包问题

### 问题 A：Rust PYTHONPATH 分隔符错误（阻塞性）

**位置**：[lib.rs:142](file:///Users/mac/AI/CScode/desktop/src-tauri/src/lib.rs#L142)

**问题代码**：
```rust
pythonpath.push_str(&format!("{}", std::path::MAIN_SEPARATOR));
pythonpath.push_str(&site_packages_zip.to_string_lossy());
```

**实际生成的 PYTHONPATH**（错误）：
```
/Applications/CScode.app/Contents/Resources/resources/python//Applications/CScode.app/Contents/Resources/resources/site-packages.zip
```

**应该是**（正确）：
```
/Applications/CScode.app/Contents/Resources/resources/python:/Applications/CScode.app/Contents/Resources/resources/site-packages.zip
```

**原因**：`std::path::MAIN_SEPARATOR` 在 macOS 上是 `/`（文件路径分隔符），但 PYTHONPATH 环境变量需要用 `:`（Python 路径分隔符）。

**修复建议**：
```rust
// 错误
pythonpath.push_str(&format!("{}", std::path::MAIN_SEPARATOR));

// 正确
pythonpath.push(':');
```

---

### 问题 B：site-packages.zip 包含原生 .so 扩展（阻塞性）

**现象**：
```
ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'
```

**原因**：`site-packages.zip` 中包含 `pydantic_core/_pydantic_core.cpython-314-darwin.so`，Python 无法从 zip 文件中加载原生扩展模块。

**检查结果**：
```bash
$ unzip -l site-packages.zip | grep pydantic_core.*\.so
  4899452  pydantic_core/_pydantic_core.cpython-314-darwin.so
```

**修复方案**：

**方案 1**：不使用 zip，直接将依赖解压到 `resources/python_deps/` 目录

**方案 2**：将 `.so` 文件放在 zip 外部，PYTHONPATH 同时包含 zip 和 `.so` 所在目录

**方案 3**：使用 PyInstaller 打包独立后端（Rust 代码已支持，但打包脚本未复制）

---

### 问题 C：PyInstaller 后端未打包进 DMG

**检查结果**：
```bash
$ ls -la /Applications/CScode.app/Contents/Resources/resources/cscode-backend/
ls: No such file or directory

# 但 PyInstaller 产物存在
$ ls -la /Users/mac/AI/CScode/dist/cscode-backend/
drwxr-xr-x  _internal/
-rwxr-xr-x  cscode-backend  (12MB)
```

**原因**：`build-desktop.sh` 没有复制 PyInstaller 打包的后端到 DMG resources 目录。

**修复建议**：在 `build-desktop.sh` 中添加：
```bash
# Copy PyInstaller backend if exists
if [ -d "$ROOT/dist/cscode-backend" ]; then
    mkdir -p "$ROOT/desktop/src-tauri/resources/cscode-backend"
    cp -r "$ROOT/dist/cscode-backend/"* "$ROOT/desktop/src-tauri/resources/cscode-backend/"
fi
```

---

## 3. 打包结构分析

### 3.1 当前打包产物

```
/Applications/CScode.app/
└── Contents/
    ├── MacOS/
    │   └── cscode-desktop (12MB Rust 二进制)
    └── Resources/
        ├── CScode.icns
        └── resources/
            ├── python/cscode/ (源码，无依赖)
            └── site-packages.zip (57MB，包含原生扩展但无法从 zip 加载)
```

### 3.2 需要的打包结构

```
/Applications/CScode.app/
└── Contents/
    ├── MacOS/
    │   └── cscode-desktop
    └── Resources/
        └── resources/
            ├── cscode-backend/  (PyInstaller 独立后端)
            │   ├── cscode-backend (可执行文件)
            │   └── _internal/ (所有依赖)
            OR
            ├── python/cscode/ (源码)
            └── python_deps/ (解压的依赖，含 .so)
```

---

## 4. 测试结论

| 测试项 | 结果 | 说明 |
|--------|------|------|
| DMG 挂载 | ✅ 通过 | 结构正确，含 CScode.app 和 Applications 快捷方式 |
| 应用图标 | ✅ 通过 | CFBundleShortVersionString = 0.3.4 |
| 桌面应用启动 | ✅ 通过 | Rust 二进制正常启动 |
| 后端服务启动 | ❌ 失败 | PYTHONPATH 分隔符错误 + zip 原生扩展问题 |
| GUI 渲染 | ⏭️ 跳过 | 后端未启动，无法测试 |

---

## 5. 修复优先级

| 问题 | 优先级 | 修复文件 | 修复难度 |
|------|--------|----------|----------|
| PYTHONPATH 分隔符 | P0（阻塞） | [lib.rs:142](file:///Users/mac/AI/CScode/desktop/src-tauri/src/lib.rs#L142) | 低（1行） |
| zip 原生扩展 | P0（阻塞） | `build-desktop.sh` | 中等 |
| PyInstaller 未打包 | P1 | `build-desktop.sh` | 低 |

---

## 6. 建议

### 6.1 立即修复（发布前必须）

1. **修复 lib.rs PYTHONPATH 分隔符**
   - 将 `MAIN_SEPARATOR` 改为 `':'`

2. **修复打包脚本**
   - 选择方案：
     - A. 解压依赖到目录（推荐，简单）
     - B. 打包 PyInstaller 后端（推荐，最可靠）

### 6.2 验证修复后

修复后重新测试完整端到端流程：
1. 安装 DMG
2. 启动应用
3. 验证后端 API 响应
4. 执行 GUI 操作测试（创建会话、发送消息、切换会话、Settings、Terminal 等）

---

## 7. 附录：错误日志

### 后端启动失败日志
```
Checking for PyInstaller binary: /Applications/CScode.app/Contents/Resources/resources/cscode-backend/cscode-backend
Started server from legacy bundled resources
/usr/local/opt/python@3.14/bin/python3.14: No module named cscode
```

### Python 导入失败日志
```
ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'
```

---

**报告生成时间**：2026-07-22 17:20  
**报告路径**：`dogfood-output/DESKTOP_E2E_TEST_REPORT.md`