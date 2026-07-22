# Permission Enforcement Bridge

## Problem
`factory.load_permission_rules()` loads rules from `SavedRules` but is never called in the server path. Agents are created with `permissions=None`, meaning tool settlement never filters by saved rules. Permission rules stored via the API or auto-save feature exist in the DB but are never enforced.

## Solution
Load permission rules from `SavedRules` in `_handle_chat()` before creating agents, and pass them to `create_agent_v2()`. This is the minimal change that enables enforcement: rules stored via `SavedRules` will automatically restrict available tools during agent execution.

## Acceptance Criteria
1. `_handle_chat()` calls `load_permission_rules()` and passes permissions to `create_agent_v2()`
2. When no rules exist, `permissions=None` (all tools allowed) — backward compatible
3. When DENY rules exist, matching tools are excluded from materialized definitions
4. All existing tests continue to pass
