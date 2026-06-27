# Phase 2 Completion: Wire new core/ into server/app

## Goal
Replace old `session_store.save_messages` + global `_agent` with new `SessionV2` + `EventStore` + `SessionCoordinator` in `server/app.py`.

## Current State
- New core/ exists: `SessionV2`, `EventStore`, `SessionCoordinator`, `SessionProjector`
- `server/app.py` still uses:
  - Global `_agent` singleton
  - `_session_store.save_messages()` (delete+reinsert)
  - No per-session locking
  - System messages persisted

## Plan

### Phase 1: Infrastructure
1. Add `EventStore` initialization in lifespan (already done)
2. Remove `_session_store` global, replace with `EventStore`
3. Remove `_agent` global, create `AgentV2` per-request via factory

### Phase 2: Chat stream handler rewrite
1. `/api/chat/stream`: Use `SessionV2` + `EventStore` instead of `save_messages`
2. Integrate `SessionCoordinator` for per-session serialization
3. Remove `save_messages` calls entirely (EventStore is append-only)

### Phase 3: Cleanup
1. Remove `_session_store.save_messages` helper `_new_to_old_messages`
2. Remove old `session_manager.py` if unused
3. Verify no references to old session store remain

## Verification
- pytest 525 passed
- mypy clean
- ruff clean
- Manual test: concurrent requests to same session don't lose messages

## Files to Modify
- `src/cscode/server/app.py` (primary)
- `src/cscode/server/session_store.py` (deprecate/remove)
- `src/cscode/core/session_manager.py` (deprecate/remove)