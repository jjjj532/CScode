# Spec: PluginSDK→PluginHost Bridge + CLI

## Objective

Bridge the two independent plugin layers so SDK-style plugins (using `@sdk.tool()` decorators) get full PluginHost lifecycle management. Add `cs plugin` CLI commands for basic plugin management.

## Background

Two plugin layers exist independently:

| Layer | Purpose | LOC | Tests |
|-------|---------|-----|-------|
| `core/plugin/` | Lifecycle: discover→install→load→activate→deactivate→uninstall with state tracking | 875 | 71 |
| `plugins/` | SDK: `@sdk.tool()` decorator API for plugin authors | 200 | 27 |

**Gap:** `PluginLoader` does its own importlib loading. SDK-based plugins cannot be lifecycle-managed through PluginHost. No CLI interface exists for plugin management.

## Success Criteria

1. SDK-style plugin (using `@sdk.tool()`) can be activated through PluginHost lifecycle
2. SDK tools are registered via PluginAPI during activation
3. The bridge is transparent — plugin authors don't need to know about PluginHost
4. `cs plugin list` scans directories and shows available plugins
5. `cs plugin install <path>` discovers and installs a plugin
6. `cs plugin info <id>` shows plugin details with registered tools
7. All 98 existing plugin tests continue passing

## Architecture

```
┌─────────────┐     bridge.py     ┌──────────────┐
│  PluginSDK  │ ────────────────→ │  PluginHost  │
│  @sdk.tool()│   auto-detect     │  activate()  │
│  @sdk.on()  │   + adapt SDK     │  deactivate()│
└─────────────┘                   └──────────────┘
       │                                │
       └──── SDK tools ────────────────→ PluginAPI.register_tool()
```

The bridge is in `cscode/plugins/bridge.py`:
- Scans a module for `PluginSDK` instances
- Generates an `activate(api)` function that registers SDK tools via `PluginAPI`
- PluginHost uses this when no explicit `activate()` exists in the module

## Commands

```bash
# Build & Test
pytest tests/test_plugin_bridge.py -v
pytest tests/test_plugin*.py -v        # All plugin tests
pytest tests/ && mypy src/ && ruff check src/

# CLI
cs plugin list
cs plugin install ./path/to/plugin
cs plugin info my-plugin
```

## Project Structure

```
src/cscode/
  plugins/
    bridge.py          ← NEW: SDK→Host bridge adapter
  core/plugin/
    host.py            ← MODIFIED: SDK detection in activate()
  cli.py               ← MODIFIED: cs plugin command group

tests/
  test_plugin_bridge.py ← NEW: Integration tests
```

## Testing Strategy

| Test | Type | What it verifies |
|------|------|------------------|
| `test_bridge_detects_sdk_in_module` | Unit | Bridge scans module and finds SDK instances |
| `test_bridge_generates_activate_func` | Unit | Generated `activate(api)` registers SDK tools |
| `test_host_activates_sdk_plugin` | Integration | Full flow: discover SDK plugin → activate → tools available |
| `test_host_activates_sdk_plugin_without_explicit_activate` | Integration | SDK-only plugin (no `activate` func) auto-bridged |
| `test_sdk_plugin_tools_available_after_activation` | Integration | SDK tools appear in `host.get_tool_providers()` |
| `test_explicit_activate_still_takes_priority` | Integration | Plugin with explicit `activate()` still works unchanged |
| `test_cli_plugin_list` | Integration | CLI lists discovered plugins |
| `test_cli_plugin_install` | Integration | CLI installs plugin from path |

## Boundaries

- **Always:** Use TDD, pass all existing tests, SDK tools registerable through PluginAPI
- **Ask first:** Adding new dependencies, changing existing API signatures
- **Never:** Remove existing functionality, break backward compatibility, use `Any` or `# type: ignore`

## Open Questions

(None — design is clear from existing patterns)
