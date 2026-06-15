# Phase 2: 功能补齐 I Implementation Plan

> **Goal:** Implement tool enhancement, provider expansion, git integration, image attachments, and structured output — the feature layer on top of Phase 1 core architecture.

**Build Order:** Tasks 2.1-2.5 are largely independent. Within each task, steps are sequential (TDD).

**Tech Stack:** Python 3.11+, asyncio, httpx, Pillow (images), gitpython or subprocess (git)

---

### Task 2.1: 工具系统增强 — New tools

**Files:**
- Create: `src/cscode/tools/webfetch.py` — `WebFetchTool`
- Create: `src/cscode/tools/websearch.py` — `WebSearchTool`
- Create: `src/cscode/tools/todowrite.py` — `TodoWriteTool`
- Create: `src/cscode/tools/question.py` — `QuestionTool`
- Create: `src/cscode/tools/skill.py` — `SkillTool`
- Create: `src/cscode/tools/apply_patch.py` — `ApplyPatchTool`
- Modify: `src/cscode/tools/base.py` — add permission metadata support
- Modify: `src/cscode/tools/__init__.py` — register new tools
- Create: `tests/test_tool_webfetch.py`
- Create: `tests/test_tool_websearch.py`
- Create: `tests/test_tool_todowrite.py`
- Create: `tests/test_tool_question.py`
- Create: `tests/test_tool_apply_patch.py`

**Dependency:** Phase 1 (BaseTool, ToolRegistry)

**Design:** Each new tool follows the existing `BaseTool` pattern (name, description, parameters, execute). Permission metadata added as optional field on BaseTool.

- [ ] **Subtask 2.1.1: Add permission metadata to BaseTool**
  - Add `requires_permission: bool = True` and `permission_default: str = "allow"` to `BaseTool`
  - Update existing tools (Read/Write/Bash that need permission)
  
- [ ] **Subtask 2.1.2: WebFetch tool**
  - `WebFetchTool` — fetches URL content, returns as markdown/text
  - Uses httpx for HTTP requests, respects robots.txt optionally
  - Parameters: `url` (required), `format` (optional, "markdown"/"text"/"html")
  
- [ ] **Subtask 2.1.3: WebSearch tool**
  - `WebSearchTool` — performs web search, returns results
  - Parameters: `query` (required), `num_results` (optional, default 8)
  - Uses configured search provider API
  
- [ ] **Subtask 2.1.4: TodoWrite tool**
  - `TodoWriteTool` — creates/manages task list
  - Parameters: `todos` (list of task objects with content/status/priority)
  
- [ ] **Subtask 2.1.5: Question tool**
  - `QuestionTool` — asks user for input/clarification
  - Parameters: `question` (required), `options` (optional list)
  
- [ ] **Subtask 2.1.6: Skill tool**
  - `SkillTool` — loads and invokes agent skills
  - Parameters: `name` (required, skill name)
  
- [ ] **Subtask 2.1.7: ApplyPatch tool**
  - `ApplyPatchTool` — applies unified diff patches to files
  - Parameters: `path` (required), `patch_content` (required), `strip` (optional, default 1)

**Verify:** `python3 -m pytest tests/test_tool_*.py -v --tb=short`

---

### Task 2.2: Provider 扩展 — New LLM providers

**Files:**
- Create: `src/cscode/providers/gemini.py` — `GeminiProvider`
- Create: `src/cscode/providers/azure.py` — `AzureProvider`
- Create: `src/cscode/providers/openrouter.py` — `OpenRouterProvider`
- Modify: `src/cscode/providers/__init__.py` — add to factory
- Modify: `src/cscode/core/config.py` — add provider-specific fields
- Create: `tests/test_providers_gemini.py`
- Create: `tests/test_providers_azure.py`
- Create: `tests/test_providers_openrouter.py`

**Dependency:** Phase 1 (LLMProvider base)

**Design:** Each provider implements `LLMProvider` ABC with `complete()`, `stream()`, `build_messages()`. All use httpx. Factory pattern in `__init__.py`.

- [ ] **Subtask 2.2.1: Gemini provider**
  - `GeminiProvider` — Google AI Gemini API
  - Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
  - Maps OpenAI message format to Gemini's `contents` format
  
- [ ] **Subtask 2.2.2: Azure OpenAI provider**
  - `AzureProvider` — Azure OpenAI Service
  - Config needs: `api_base` (Azure endpoint), `api_key`, `model` (deployment name)
  - Mostly identical to OpenAI but different endpoint pattern
  
- [ ] **Subtask 2.2.3: OpenRouter provider**
  - `OpenRouterProvider` — route to 100+ models
  - Endpoint: `https://openrouter.ai/api/v1/chat/completions`
  - Same OpenAI-compatible format, additional headers for app metadata
  
- [ ] **Subtask 2.2.4: Update factory**
  - Add cases for "gemini", "azure", "openrouter" in `create_provider()`

**Verify:** `python3 -m pytest tests/test_providers_*.py -v --tb=short`

---

### Task 2.3: Git 集成 — Snapshots, diff, review

**Files:**
- Create: `src/cscode/git/__init__.py`
- Create: `src/cscode/git/snapshot.py` — auto-snapshot on session operations
- Create: `src/cscode/git/diff.py` — diff generation and parsing
- Create: `src/cscode/git/review.py` — commit-aware code review
- Modify: `src/cscode/core/engine.py` — integrate git snapshot in _run_loop
- Create: `tests/test_git_snapshot.py`
- Create: `tests/test_git_diff.py`
- Create: `tests/test_git_review.py`

**Dependency:** Phase 1, Task 2.1 (uses BashTool internally)

**Design:** Operates via subprocess `git` commands. Snapshot captures working tree state before/after tool executions. Diff generates structured diff output. Review provides context about recent changes.

- [ ] **Subtask 2.3.1: Git snapshot**
  - `GitSnapshot` class with `snapshot()` — stashes current state
  - Auto-snapshot triggered by `_run_loop` before tool execution
  - Configurable (enable/disable, directory)
  
- [ ] **Subtask 2.3.2: Git diff**
  - `GitDiff` class with `diff()` — returns structured diff
  - `diff_files()` — per-file diff
  - `changed_files()` — list of changed files
  
- [ ] **Subtask 2.3.3: Git review**
  - `GitReview` class — commit-aware review
  - `get_head_info()` — current branch/commit
  - `get_uncommitted_changes()` — working tree status summary

**Verify:** `python3 -m pytest tests/test_git_*.py -v --tb=short`

---

### Task 2.4: 图片附件 — Image handling

**Files:**
- Create: `src/cscode/core/images.py` — image processing utilities
- Modify: `src/cscode/core/engine.py` — integrate image attachment handling
- Modify: `src/cscode/core/messages.py` — add image support to Message
- Create: `tests/test_images.py`

**Dependency:** Phase 1 (Message, engine.py)

**Design:** Auto-resize large images to fit model limits (max 20MP → 2MP). Encode as Base64 data URI for multi-modal models. Support for multiple images.

- [ ] **Subtask 2.4.1: Image processing**
  - `resize_image()` — resize if dimensions exceed threshold (max 2048px on longest side)
  - `image_to_base64()` — encode as data URI
  - `ImageAttachment` dataclass — path, mime_type, data_uri
  
- [ ] **Subtask 2.4.2: Integration with messages**
  - Add `images: list[ImageAttachment] | None = None` field to `Message`
  - Update `build_messages()` in providers to include image data URIs in content blocks
  
- [ ] **Subtask 2.4.3: Integration with engine**
  - `_run_loop` processes attached filenames for images
  - Non-image files attached as text content (existing behavior)

**Verify:** `python3 -m pytest tests/test_images.py -v --tb=short`

---

### Task 2.5: 结构化输出 — JSON Schema validation

**Files:**
- Create: `src/cscode/core/structured.py` — structured output utilities
- Create: `tests/test_structured.py`

**Dependency:** Phase 1 (LLMResult, Message)

**Design:** When tools specify `response_schema` in their definition, the LLM response is validated against a JSON Schema. Invalid responses trigger auto-retry with error message to the LLM.

- [ ] **Subtask 2.5.1: JSON Schema validation**
  - `validate_against_schema(data, schema) -> tuple[bool, str]` — validates JSON data
  - Uses Python's `jsonschema` library or manual validation
  - Returns (valid, error_message)
  
- [ ] **Subtask 2.5.2: Auto-retry integration**
  - `StructuredOutputHandler` class
  - `handle_response(content, schema, max_retries=3) -> str` — validates and retries
  - If invalid, appends error message to conversation, LLM tries again

**Verify:** `python3 -m pytest tests/test_structured.py -v --tb=short`

---

### Task 2.6: Phase 2 final verification

- [ ] Full test suite: `python3 -m pytest tests/ -q --tb=short`
- [ ] mypy on new code: `python3 -m mypy src/cscode/ --ignore-missing-imports`
- [ ] ruff on new code: `python3 -m ruff check src/cscode/`
- [ ] Final commit
