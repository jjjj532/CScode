# Security Hardening — Remaining Items

## Problem
5 P1/P2 security items were marked done but never implemented:
- P1-1a: CLI missing key detection on startup
- P1-3: Server log security tip
- P2-1: Graceful shutdown (SIGINT/SIGTERM)
- P2-2: EventStore structured logging with timing
- P2-3: Rate limiting on /api/chat

Plus 2 review findings:
- Runtime keychain integration gap in `factory.py`
- CONFIG_KEY_META api_key documentation outdated

## Item Details

### 1. CLI Missing Key Detection
**File**: `src/cscode/cli.py`, function `server()`
**Behavior**: When `cs server` starts, check if any API key is configured (via keychain or env). If not, print a yellow warning but continue starting.
**Acceptance**: Running `cs server` without any API key configured prints `WARNING: No API key configured. Set via Settings panel or `cs config set --global api_key <key>``

### 2. Server Log Security Tip
**File**: `src/cscode/server/app.py`, lifespan startup
**Behavior**: After startup complete, log: `Security: API endpoint restricted to localhost (use --host 0.0.0.0 to expose)`
**Acceptance**: Server log contains a security tip line during startup.

### 3. Graceful Shutdown
**File**: `src/cscode/server/app.py`, lifespan shutdown
**Behavior**: Handle SIGINT/SIGTERM to ensure DB close + cleanup happens. Currently the lifespan `yield` already handles shutdown cleanup. The gap is that uvicorn may not trigger it on SIGKILL. This is adequately handled by the lifespan protocol — no change needed beyond verifying the existing shutdown path works.
**Note**: After investigation, this is already handled by FastAPI lifespan protocol + existing `_db.close()` in shutdown. **No code change needed.** Just verify.

### 4. EventStore Structured Logging with Timing
**File**: `src/cscode/storage/event_store.py`
**Behavior**: Log timing for append/read operations at INFO level with duration_ms.
**Acceptance**: EventStore.append and EventStore.read log `event_store.append aggregate=%s events=%d duration_ms=%.0f`

### 5. Rate Limiting on /api/chat
**File**: `src/cscode/server/app.py`
**Behavior**: Apply simple in-memory rate limiting to POST /api/chat: max 60 requests per minute per IP. Return 429 when exceeded.
**Acceptance**: 61st request from same IP within 60s returns HTTP 429.

### 6. Runtime Keychain Integration
**File**: `src/cscode/app/factory.py`, function `_resolve_api_key()`
**Behavior**: Before falling back to env vars, check KeychainStore for the "default" API key.
**Priority**: Check order: config.api_key > keychain > env var > empty string
**Acceptance**: When API key is stored via POST /api/config (which saves to keychain), `create_agent_v2()` resolves it for LLM calls.

### 7. CONFIG_KEY_META Documentation Update
**File**: `src/cscode/core/config.py`
**Behavior**: Update the `api_key` entry in CONFIG_KEY_META to mention keychain storage.
**Acceptance**: CONFIG_KEY_META["api_key"]["description"] includes "stored in system keychain when set via API".

## Acceptance Criteria (All Items)
- All existing tests pass
- New tests cover each new behavior
- ruff clean
- mypy clean (no new errors)
