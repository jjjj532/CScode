# Round 2 Fixes: GUI Test Report Remaining Issues

## Problem Summary

FINAL_TEST_REPORT.md identified 6 remaining issues after initial P0/P1 fixes.

## Issues

### Issue 1 (P0): LLM Error Truncation
- **Symptom**: LLM errors shown as truncated `"Error: [Transport] — LLMClient.stream — "` instead of full message
- **Root Cause**: Backend error content in SSE `error` event loses detail from LLM client chain
- **Fix**: Add detailed error formatting in `_handle_chat` / `chat_stream` for agent/LLM errors
- **Backend**: app.py `event_stream()` error handler

### Issue 2 (P1): setMessages Empty Array Overwrite
- **Symptom**: Switching sessions during streaming can overwrite in-flight messages with empty server data
- **Root Cause**: `setMessages([], id)` discards local messages when server has nothing persisted yet
- **Fix**: Add `mergeLocal` guard in `setMessages` for the case where `prev` exists but `filtered` is empty
- **Frontend**: stores/useSessionStore.ts `setMessages`

### Issue 3 (P1): Stream Controller Superseded
- **Symptom**: `"controller superseded"` log when user sends messages rapidly — old stream finishes after being replaced
- **Root Cause**: `streamControllers[sid] = controller` overwrites without waiting for old stream to finish
- **Fix**: Sequential per-session queue; reject new send if session is already streaming
- **Frontend**: hooks/useChat.ts `sendMessage`

### Issue 4 (P1): Frontend Store Not Exposed
- **Symptom**: `window.__STORE_STATE__` undefined — test scripts can't inspect store state
- **Fix**: Expose Zustand store to `window` in store creation
- **Frontend**: stores/useSessionStore.ts

### Issue 5 (P2): Password Field Accessibility Warning
- **Symptom**: `[DOM] Password field is not contained in a form`
- **Fix**: Wrap API Key input in `<form>` element
- **Frontend**: components/ui/SettingsPanel.tsx

### Issue 6 (P2): Missing API Endpoints
- **Symptom**: `GET /api/tools` → 404, `GET /api/version` → 404
- **Fix**: Add `/api/tools` alias and `/api/version` endpoint
- **Backend**: server/app.py

## Acceptance Criteria
1. LLM errors show full detail (no truncation)
2. setMessages preserves in-flight streaming messages even when server returns empty
3. Rapid sendMessage to same session is rejected with user-visible feedback
4. `window.__STORE_STATE__` exposes Zustand store state
5. No DOM "Password field not in form" warning
6. `GET /api/tools` returns tool list; `GET /api/version` returns version string

## Verification
- pytest tests/ (no regressions)
- mypy src/ (no new errors)
- ruff check src/ (clean)
- Playwright E2E: verify API endpoints + store exposure
