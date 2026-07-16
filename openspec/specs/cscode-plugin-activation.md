# PluginHost 激活管线 — 完整插件生命周期

> 基于现有 PluginHost/PluginAPI/Discovery 基础，补齐 load→activate→deactivate 管线

---

## 1. 问题定义

### 1.1 当前状态

PluginHost 已有 skeleton：
- `discover()` — 发现本地/pip 插件目录 ✅
- `install()` — 注册 PluginManifest ✅
- `activate()` — 只创建空 PluginAPI，**不加载插件模块** ❌
- `deactivate()` — 只移除 API，**不通知插件** ❌
- `uninstall()` — 从 registry 删除 ✅

### 1.2 根因

`activate()` 的当前实现：
```python
async def activate(self, plugin_id: str) -> PluginAPI:
    api = PluginAPI()                          # 空 API
    self._plugin_apis[plugin_id] = api
    self._registry.update_state(plugin_id, PluginState.ACTIVE)
    return api
```

缺少：
1. **插件模块加载** — 未 `import` 插件的 Python 包
2. **插件激活回调** — 未调用 `plugin.activate(api)`
3. **EventBus 注入** — PluginAPI 内有 `_hook_registry` 但从未接入 EventBus
4. **插件停用回调** — 未调用 `plugin.deactivate()`
5. **load 步骤** — 缺少 DISCOVERED → LOADED 中间状态

### 1.3 范围

| 包括 | 不包括 |
|------|--------|
| Plugin 模块加载 (`importlib`) | pip 包自动安装 |
| `activate(api)` / `deactivate()` 回调约定 | npm/git 插件发现 |
| EventBus 注入到 PluginAPI | TUI/CLI/Web 三层集成 |
| 测试覆盖全部管线 | 插件市场 UI |

---

## 2. 插件规范

### 2.1 插件包结构

```python
my_cscode_plugin/
    __init__.py
    plugin.json      # 可选，元数据
```

### 2.2 插件入口函数

插件通过 `__init__.py` 导出两个可选的入口函数：

```python
"""my_cscode_plugin/__init__.py"""

__plugin_name__ = "My Plugin"

def activate(api: PluginAPI) -> None:
    """Called when plugin is activated.
    
    Args:
        api: PluginAPI instance for registering tools, commands, hooks, etc.
    """
    api.register_tool(MyTool)
    api.register_command(CommandDef(name="mycmd", description="..."))
    api.on_session_start(my_handler)

def deactivate() -> None:
    """Called when plugin is deactivated. Optional."""
    pass
```

### 2.3 生命周期状态机

```
                     load()            activate()
DISCOVERED ──────────────────→ LOADED ──────────→ ACTIVE
                              ↑                     │
                              │            deactivate()
                              │                     │
                              └─────────────────────▼
                                                  INACTIVE
```

| 状态 | 含义 |
|------|------|
| `DISCOVERED` | 文件系统找到，已注册 |
| `LOADED` | 模块已 import，`activate()` 尚未调用 |
| `ACTIVE` | `activate(api)` 已调用，工具/命令已注册 |
| `INACTIVE` | `deactivate()` 已调用，注册项已清理 |

---

## 3. 实现方案

### 3.1 `PluginHost.load(plugin_id)` — 新增

```python
async def load(self, plugin_id: str) -> ModuleType:
    """Import the plugin's Python module.
    
    Raises:
        ValueError: plugin not found or already loaded.
        ImportError: module import failed.
    """
    manifest = self._registry.get(plugin_id)
    if manifest is None:
        raise ValueError(f"Plugin '{plugin_id}' not found")
    if manifest.state >= PluginState.LOADED:
        raise ValueError(f"Plugin '{plugin_id}' already loaded")
    
    # Import from source path or package name
    module = _import_plugin(manifest)
    self._registry.update_state(plugin_id, PluginState.LOADED)
    return module
```

### 3.2 `PluginHost.activate()` — 增强

在现有基础上增加：
1. 自动调用 `load()`（如果未加载）
2. 创建 PluginAPI 并注入 EventBus
3. 调用 `module.activate(api)`（如果存在）
4. 更新状态

```python
async def activate(self, plugin_id: str) -> PluginAPI:
    manifest = self._registry.get(plugin_id)
    if manifest is None:
        raise ValueError(...)
    if manifest.state == PluginState.ACTIVE:
        raise ValueError(...)
    
    # Load if not already loaded
    if manifest.state < PluginState.LOADED:
        await self.load(plugin_id)
    
    # Create API with EventBus
    api = PluginAPI(event_bus=self._event_bus)
    
    # Call plugin's activate function
    module = self._loaded_modules[plugin_id]
    if hasattr(module, "activate"):
        module.activate(api)
    
    self._plugin_apis[plugin_id] = api
    self._registry.update_state(plugin_id, PluginState.ACTIVE)
    return api
```

### 3.3 `PluginHost.deactivate()` — 增强

```python
async def deactivate(self, plugin_id: str) -> None:
    """Notify plugin and clean up."""
    module = self._loaded_modules.get(plugin_id)
    if module is not None and hasattr(module, "deactivate"):
        module.deactivate()
    
    self._plugin_apis.pop(plugin_id, None)
    self._loaded_modules.pop(plugin_id, None)
    self._registry.update_state(plugin_id, PluginState.INACTIVE)
```

### 3.4 `_import_plugin()` — 辅助函数

```python
def _import_plugin(manifest: PluginManifest) -> ModuleType:
    """Import a plugin module from its source path."""
    source = manifest.source
    if source.startswith("pip:"):
        pkg_name = source[4:]
        return importlib.import_module(pkg_name)
    else:
        # Local path: add to sys.path and import
        path = Path(source).resolve()
        if path.is_dir():
            sys.path.insert(0, str(path.parent))
            return importlib.import_module(path.name)
        sys.path.insert(0, str(path.parent))
        return importlib.import_module(path.stem)
```

---

## 4. EventBus 集成

### 4.1 PluginHost 接收 EventBus

```python
class PluginHost:
    def __init__(self, ..., event_bus: EventBus | None = None):
        self._event_bus = event_bus
```

### 4.2 PluginAPI HookRegistry 自动连接

```python
api = PluginAPI(event_bus=self._event_bus)
# 如果 event_bus 提供，PluginAPI 内部创建 HookRegistry
# 插件调用 api.on_session_start(handler) 时自动注册到 EventBus
```

---

## 5. 验收标准

1. **load()**: 本地插件目录导入成功/失败处理
2. **activate()**: 插件 `activate(api)` 回调被调用，工具可注册
3. **deactivate()**: 插件 `deactivate()` 被调用，API 清理
4. **state 流转**: DISCOVERED→LOADED→ACTIVE→INACTIVE 正确
5. **EventBus 集成**: `on_session_start` 等 hook 注册生效
6. **错误处理**: 无效模块、导入失败、重复操作等异常情况
7. **兼容性**: 已有 21 个 test_plugin_host.py 测试继续通过

---

## 6. 不做的

- pip 包自动下载安装（只 import 已安装的）
- 插件版本冲突检测
- 插件热重载
- UI 层面的插件管理器
- npm/git 插件发现
