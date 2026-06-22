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
