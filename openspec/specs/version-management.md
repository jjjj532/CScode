# Spec: Version Management & Release Automation

## Objective

当前 CScode 的版本号散落在 7 处（`__init__.py`、`app.py`、`client.py`、`server.py`、`tauri.conf.json`、`Cargo.toml`、`build.sh`），每次发布需手动同步。目标是：

1. 建立单一版本权威来源（`src/cscode/__init__.py`）
2. 提供 `cs version` CLI 命令——显示版本、检查各副本一致性
3. 提供 `cs version --check` 验证命令（CI 中可用）
4. 集成到构建脚本，发布前自动验证
5. 所有测试通过

## Success Criteria

- `cs version` 输出当前版本号（来自 `__init__.py`）
- `cs version --check` 扫描 7 处版本号，全部一致返回 exit 0，不匹配返回 exit 1 + 报告差异
- `cs version --check` 通过时 stdout 包含 `OK`，失败时列出不一致的文件及期望/实际值
- 构建脚本 `scripts/build_desktop.sh` 在构建前调用 `cs version --check`
- `pytest tests/test_version.py` 全部通过（≥ 8 个测试）
- 验证命令可用于 CI（无网络依赖，纯文件扫描）

## Commands

```
pip install -e .              # 安装
pytest tests/test_version.py  # 运行版本测试
cs version                    # 显示版本
cs version --check            # 验证所有版本号一致
python -m cscore version --check  # 同上，模块方式
```

## Project Structure

```
src/cscode/core/version.py    ← 新文件：版本管理模块
src/cscode/cli.py             ← 修改：添加 version 命令组
tests/test_version.py         ← 新文件：版本管理测试
scripts/build_desktop.sh      ← 修改：构建前调用 --check
```

版本权威来源保持 `src/cscode/__init__.py` 中的 `__version__`。

## Code Style

```python
# version.py — 纯函数式，无副作用，文件扫描匹配已有 error.py 风格
# cli.py 中版本命令组匹配已有 @cli.group() 模式
```

## Testing Strategy

| 测试 | 验证内容 |
|------|---------|
| `test_version_string_format` | `__version__` 是 `MAJOR.MINOR.PATCH` 格式 |
| `test_version_consistency_core` | `__init__.py` == `app.py` FastAPI version |
| `test_version_consistency_mcp_client` | `__init__.py` == `client.py` version |
| `test_version_consistency_mcp_server` | `__init__.py` == `server.py` version |
| `test_version_consistency_tauri_conf` | `__init__.py` == `tauri.conf.json` version |
| `test_version_consistency_cargo` | `__init__.py` == `Cargo.toml` version |
| `test_version_consistency_build_sh` | `__init__.py` == `build.sh` version |
| `test_cli_version_command` | `cs version` 输出包含当前版本 |
| `test_cli_version_check_ok` | `cs version --check` 全部一致时 exit 0 |
| `test_cli_version_check_fail` | `cs version --check` 不匹配时 exit 1 |

## Boundaries

- Always: 版本号只改 `__init__.py`，其他文件通过 `--check` 发现不一致后自动同步
- Ask first: 修改版本格式（当前 `MAJOR.MINOR.PATCH`）
- Never: 跳过测试直接发布

## Open Questions

- 是否需要 `cs version --sync`（自动同步所有文件）？ 当前只做 `--check`，同步留到后续。

## 文件清单

### 新建文件
1. `src/cscode/core/version.py` — 版本读取 + 一致性验证逻辑
2. `tests/test_version.py` — 全部测试

### 修改文件
3. `src/cscode/cli.py` — 添加 `version` 命令组
4. `scripts/build_desktop.sh` — 构建前调用 `cs version --check`
