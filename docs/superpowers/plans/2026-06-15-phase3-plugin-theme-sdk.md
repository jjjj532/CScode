# Phase 3: 功能补齐 II — Plugin System, Theme, SDK

**Build Order:** Tasks 3.1–3.3 are independent and can be parallelized.

---

### Task 3.1: 插件系统增强 — Event hooks, manifest, SDK

**Files:**
- Create: `src/cscode/plugins/manifest.py` — `PluginManifest` dataclass + loader
- Create: `src/cscode/plugins/hooks.py` — `PluginHook` system integrated with EventBus
- Create: `src/cscode/plugins/sdk.py` — `PluginSDK` helper class
- Modify: `src/cscode/plugins/__init__.py` — export public API
- Modify: `src/cscode/plugins/loader.py` — add manifest support
- Create: `tests/test_plugin_manifest.py`
- Create: `tests/test_plugin_hooks.py`
- Create: `tests/test_plugin_sdk.py`

**Dependency:** Phase 1 (EventBus)

---

### Task 3.2: 主题系统 — TUI themes + config persistence

**Files:**
- Create: `src/cscode/tui/themes.py` — `Theme` dataclass, preset themes
- Modify: `src/cscode/tui/app.py` — apply theme on startup
- Modify: `src/cscode/core/config.py` — add `theme` field
- Create: `tests/test_themes.py`

**Dependency:** None (standalone)

---

### Task 3.3: SDK 包 — `create_cscode()`, `CScodeClient()`

**Files:**
- Create: `packages/sdk/pyproject.toml`
- Create: `packages/sdk/src/cscode_sdk/__init__.py`
- Create: `packages/sdk/src/cscode_sdk/client.py`
- Create: `packages/sdk/src/cscode_sdk/factory.py`
- Create: `packages/sdk/tests/test_sdk.py`
- Create: `packages/sdk/README.md`

**Dependency:** Phase 1, Phase 2 (uses ServiceContainer, providers, tools)

---

### Task 3.4: Phase 3 最终验证

- [ ] Full test suite: `python3 -m pytest tests/ -q --tb=short`
- [ ] mypy: `python3 -m mypy src/cscode/ --ignore-missing-imports`
- [ ] ruff: `python3 -m ruff check src/cscode/`
- [ ] SDK package install test: `pip install -e packages/sdk && python3 -c "from cscode_sdk import create_cscode; print('OK')"`
- [ ] Final commit
