# Batch 2: Agent System (代理系统)

## Overview
Implement the 4 missing agent system features to reach OpenCode parity:
1. Sub-agent dispatch for `@tool` mentions
2. `@mention` autocomplete UI in the composer
3. Session compression (wire existing `ContextCompressor`)
4. AI-based session title generation

## Tasks

### Task 2.1: Sub-agent dispatch
**Description:** Implement `SubAgentOrchestrator.process_mentions()` to recognize `@tool` patterns and dispatch sub-agent tasks. Currently returns input unchanged.

**Acceptance criteria:**
- `@tool:ReadTool path=foo.py` triggers a sub-agent that executes the tool
- `@tool:BashTool command=ls` triggers a sub-agent that executes the command
- Results from sub-agent execution are injected back into the input
- Unknown/unrecognized `@` mentions are left as-is
- Proper error handling for failed sub-agent execution

**Files:** `src/cscode/core/sub_agent.py`, `tests/test_sub_agent.py`

### Task 2.2: @mention autocomplete UI
**Description:** Create an autocomplete dropup that appears when typing `@` in the Composer textarea. Shows matching files from `/api/files/search` and known tools.

**Acceptance criteria:**
- Typing `@` opens a dropup showing file/tool suggestions
- Typing more characters filters suggestions (fuzzy match)
- Clicking or pressing Enter inserts the selected `@mention`
- Backend `/api/files/search` is queried with debounce
- Known tool names are also suggested (ReadTool, BashTool, etc.)
- Styled consistently with the OpenCode theme

**Files:** `src/cscode/web/src/components/ui/AutocompletePopup.tsx`, `src/cscode/web/src/components/chat/Composer.tsx`, `tests/test_autocomplete.py`

### Task 2.3: Session compression wiring
**Description:** Wire the existing `ContextCompressor` into the chat stream handler so that long sessions are automatically compressed.

**Acceptance criteria:**
- `ContextCompressor` is instantiated in the chat stream handler
- Compression is applied when message history exceeds threshold
- Compression produces a summary note and keeps recent messages
- All existing tests still pass

**Files:** `src/cscode/server/app.py`, `tests/test_compression_integration.py`

### Task 2.4: Session title generation
**Description:** After the first assistant response, generate a concise title via LLM call and update the session in the database.

**Acceptance criteria:**
- After the first exchange, a background LLM call generates a 3-6 word title
- Title is updated in the database via `SessionStore.update_title()`
- The frontend sidebar reflects the updated title
- Error in title generation doesn't break the chat flow

**Files:** `src/cscode/server/app.py`, `src/cscode/web/src/hooks/useChat.ts`

## Architecture Decisions
- Sub-agent dispatch uses the existing `LLMProvider` and `ToolRegistry` (already passed to `SubAgentOrchestrator`)
- Autocomplete uses the existing `/api/files/search` endpoint + a hardcoded tool list
- Session compression keeps the existing `MAX_MESSAGES=20` as a safety net
- Title generation is async non-blocking (fire-and-forget after response)

## Order
1. Task 2.3 (compression) - smallest, cleanest, quick win
2. Task 2.1 (sub-agent dispatch) - core backend feature
3. Task 2.2 (@mention UI) - depends on understanding tools list
4. Task 2.4 (title generation) - depends on stable chat flow
