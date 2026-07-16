# Implementation Plan: PluginHost Activation Pipeline

## Overview
Complete the PluginHost lifecycle by adding plugin module loading (import), plugin activation/deactivation callbacks, and EventBus hook integration. Current `activate()` creates an empty PluginAPI without loading the plugin module or calling its registration hooks.

## Architecture Decisions
- **Plugin convention**: plugins expose `activate(api)` and optional `deactivate()` in their `__init__.py`
- **State machine**: DISCOVERED → LOADED → ACTIVE → INACTIVE (new LOADED state)
- **EventBus injection**: PluginHost holds optional EventBus reference; passed to PluginAPI on activate

## Task List

### Phase 1: EventBus + Module Loading (parallelizable)

- [ ] **Task 1**: EventBus injection into PluginHost
  - Add `event_bus: EventBus | None = None` to `PluginHost.__init__`
  - Pass to `PluginAPI(event_bus=...)` during `activate()`
  - Existing tests must pass (event_bus is optional)

- [ ] **Task 2**: Plugin module loading infrastructure
  - Add `_import_plugin(manifest) → ModuleType` helper
  - Add `PluginHost.load(plugin_id) → ModuleType` method
  - Handle: ImportError, state preconditions, source resolution

### Phase 2: Activation Callbacks

- [ ] **Task 3**: Enhance activate/deactivate with callbacks
  - `activate()` calls `load()` then `module.activate(api)` if exists
  - `deactivate()` calls `module.deactivate()` if exists
  - Track loaded modules in `self._loaded_modules: dict[str, ModuleType]`

### Phase 3: Tests + Verification

- [ ] **Task 4**: Comprehensive tests
  - `load()` with local plugin dir (valid module)
  - `load()` with ImportError
  - `load()` already loaded → raises ValueError
  - `activate()` calls `module.activate(api)` — verify tools registered
  - `deactivate()` calls `module.deactivate()`
  - EventBus: `on_session_start` hook wired via PluginAPI
  - Existing 21 tests still pass

## Dependency Graph
```
Task 1 (EventBus) ──┐
                    ├──→ Task 3 (callbacks) ──→ Task 4 (tests)
Task 2 (loading) ───┘
```

## Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Module import side effects | Med | Use `importlib` with isolated namespace; document convention |
| Circular imports | Low | PluginHost imports via `importlib` not direct import |
| Existing test breakage | Low | EventBus is optional — default None preserves API compatibility |
