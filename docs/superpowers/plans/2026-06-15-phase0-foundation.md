# Phase 0: 地基加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all code quality issues, deprecation warnings, test gaps, and add missing test dependencies to create a stable foundation for Phase 1-4.

**Architecture:** This phase touches every existing module without changing its semantics. Tasks are: (1) add test deps to pyproject.toml, (2) fix all 90 mypy errors across 20 files, (3) fix 24 ruff errors, (4) migrate FastAPI `on_event` to lifespan, (5) fix test code quality. Each task is independent enough to parallelize.

**Tech Stack:** Python 3.11+, mypy strict, ruff, FastAPI, pytest, Click, httpx, aiosqlite, Textual, Tauri

---

### Task 0.1: Add test dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Add `[project.optional-dependencies]` group**

`respx` is used by `tests/test_providers.py` but not declared. Add an optional test group so the project properly documents its test toolchain.

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
test = [
    "respx>=0.23.0",
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
]
```

- [ ] **Verify the change**

Run:
```bash
cd /Users/mac/AI/CScode && python3 -c "import respx; print('ok')"
```
Expected: `ok`

- [ ] **Commit**

```bash
git add pyproject.toml
git commit -m "chore: add test dependency group to pyproject.toml"
```

---

### Task 0.2: Fix ruff E402 — Move server/app.py imports to top

**Files:**
- Modify: `src/cscode/server/app.py`

**Problem:** Lines 16-30 have module-level imports after `api_router = APIRouter(prefix="/api")` on line 14. This causes 14 ruff E402 errors. The fix is to move the imports before the `api_router` line.

- [ ] **Edit server/app.py — move imports before APIRouter creation**

Replace lines 1-16 to reorder: imports first, then APIRouter.

Current structure (simplified):
```python
from __future__ import annotations
import json, os, uuid
from pathlib import Path
from typing import Any
import fastapi
from fastapi import FastAPI, APIRouter, ...

app = FastAPI()
api_router = APIRouter(prefix="/api")

from cscode.core.config import load_config  # E402
...
```

Move all `from cscode.*` imports above the `api_router` line so they sit with the other imports.

After fix, the top of the file should look like:

```python
from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import fastapi
from fastapi import APIRouter, Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from cscode.core.config import ConfigStore, load_config
from cscode.core.engine import Agent, AgentOptions
from cscode.core.messages import Message, MessageRole
from cscode.providers import create_provider
from cscode.storage.db import Database
from cscode.storage.session import SessionStore
from cscode.tools.base import ToolRegistry
from cscode.tools.bash import BashTool
from cscode.tools.browser import BrowserTool
from cscode.tools.edit import EditTool
from cscode.tools.glob import GlobTool
from cscode.tools.grep import GrepTool
from cscode.tools.ls import LsTool
from cscode.tools.read import ReadTool
from cscode.tools.write import WriteTool

app = FastAPI()
api_router = APIRouter(prefix="/api")
```

- [ ] **Run ruff to verify E402 fixed**

```bash
cd /Users/mac/AI/CScode && python3 -m ruff check src/cscode/server/app.py --select E402
```
Expected: 0 errors

- [ ] **Run tests to verify nothing broke**

```bash
cd /Users/mac/AI/CScode && python3 -m pytest tests/test_api.py -q --tb=short
```
Expected: all pass

- [ ] **Commit**

```bash
git add src/cscode/server/app.py
git commit -m "fix: move imports to top of server/app.py to fix E402"
```

---

### Task 0.3: Fix ruff F401/F541/F841 — Remove unused imports/variables

**Files:**
- Modify: `src/cscode/server/app.py`
- Modify: `src/cscode/tools/browser.py`
- Modify: `src/cscode/utils/file_parser.py`

**Problem:** 8 fixable ruff errors (6 auto-fixable, 2 unsafe):
- `server/app.py`: unused `t0`, unused `load_config` (2x), f-string without placeholders
- `tools/browser.py`: unused `base64`, unused `Path`
- `utils/file_parser.py`: unused `ns`, unused `e`, unused `olefile`

- [ ] **Auto-fix ruff issues**

```bash
cd /Users/mac/AI/CScode && python3 -m ruff check --fix src/cscode/
```

- [ ] **Verify remaining errors are 0**

```bash
cd /Users/mac/AI/CScode && python3 -m ruff check src/cscode/
```
Expected: 0 errors

- [ ] **Run tests to verify nothing broke**

```bash
cd /Users/mac/AI/CScode && python3 -m pytest tests/ -q --tb=short
```
Expected: 135 passed

- [ ] **Commit**

```bash
git add src/cscode/server/app.py src/cscode/tools/browser.py src/cscode/utils/file_parser.py
git commit -m "fix: remove unused imports and variables"
```

---

### Task 0.4: Fix mypy errors in cli.py

**Files:**
- Modify: `src/cscode/cli.py`

**Problem:** 8 mypy errors in cli.py:
- Line 253: `persist_delete` has no type annotation
- Lines 262, 268, 287, 298, 310: Functions missing return type annotation
- Line 303: `Session | None` has no attribute `title` (need narrowing)
- Line 303 also needs `-> None` return annotation

- [ ] **Read current cli.py to understand the affected functions**

```bash
cd /Users/mac/AI/CScode && python3 -m mypy src/cscode/cli.py --ignore-missing-imports
```

- [ ] **Fix each error by adding type annotations**

For `persist_delete` (line 253) — add return type `-> None`:
```python
async def persist_delete(session_id: str) -> None:
```

For `cmd_cs_chat` (line 262) — add return type:
```python
def cmd_cs_chat() -> None:
```

For `cmd_cs_review` (line 268):
```python
def cmd_cs_review() -> None:
```

For `cmd_cs_config_get` (line 287):
```python
def cmd_cs_config_get() -> None:
```

For `cmd_cs_config_set` (line 298):
```python
def cmd_cs_config_set() -> None:
```

For the `Session | None` issue (line 303) — add narrowing:
```python
active = manager.get_active()
if active is not None:
    click.echo(f"  Active: {active.title}")
```

For `cmd_cs_config_list` (line 310):
```python
def cmd_cs_config_list() -> None:
```

- [ ] **Verify mypy passes for cli.py**

```bash
cd /Users/mac/AI/CScode && python3 -m mypy src/cscode/cli.py --ignore-missing-imports
```
Expected: 0 errors

- [ ] **Run tests**

```bash
cd /Users/mac/AI/CScode && python3 -m pytest tests/test_cli.py -q --tb=short
```
Expected: all pass

- [ ] **Commit**

```bash
git add src/cscode/cli.py
git commit -m "fix: add type annotations to cli.py"
```

---

### Task 0.5: Fix mypy errors in server/app.py (part 1 — type narrowing for UploadFile)

**Files:**
- Modify: `src/cscode/server/app.py`

**Problem:** Multiple mypy errors where `UploadFile | str` is used as `str` without narrowing. The server has a pattern like `file: UploadFile | None = None` and then uses `file` as `str`. Also many `no-untyped-def` errors for missing return types.

- [ ] **Fix `_handle_chat` and `_handle_chat_stream` UploadFile type errors**

The core problem: `form_file: UploadFile | None = None` is passed through code that expects `str`. Fix by ensuring the file is read into a string early, and the downstream functions take only `str`.

In `_handle_chat` and `_handle_chat_stream`, change the file parameter handling:

After extracting `form_file`, immediately read the content:
```python
attached_content: str | None = None
if form_file is not None:
    attached_content = (await form_file.read()).decode("utf-8", errors="replace")
```

Then pass `attached_content` (not `form_file`) downstream. This eliminates all the `UploadFile | str` type confusion.

Add proper return type annotations to all helper functions:
- `event_stream` → `async def event_stream(...) -> AsyncIterator[str]:`
- `_detect_timeout` → `def _detect_timeout(...) -> float:`
- `_build_initial_messages` → `def _build_initial_messages(...) -> list[Message]:`
- `_handle_chat` → `async def _handle_chat(...) -> ...:`

- [ ] **Verify mypy errors reduced**

```bash
cd /Users/mac/AI/CScode && python3 -m mypy src/cscode/server/app.py --ignore-missing-imports
```
Expected: count drops from ~40 to ~15 (remaining are `_db`, `_session_store`, `_agent` module-level vars)

- [ ] **Run API tests**

```bash
cd /Users/mac/AI/CScode && python3 -m pytest tests/test_api.py -q --tb=short
```
Expected: all pass

- [ ] **Commit**

```bash
git add src/cscode/server/app.py
git commit -m "fix: add type annotations and fix UploadFile type narrowing in server"
```

---

### Task 0.6: Fix mypy errors in server/app.py (part 2 — module-level globals + remaining)

**Files:**
- Modify: `src/cscode/server/app.py`

**Problem:** Remaining mypy errors are:
- `_db`, `_session_store`, `_agent` module-level vars without type annotation
- Various `Incompatible types` errors from the prior fix's ripple effects
- Missing type args for `dict`, `list`
- `Call to untyped function "event_stream"` (after fixing 0.5)

- [ ] **Add explicit type annotations for module-level globals**

```python
_db: Database | None = None
_session_store: SessionStore | None = None
_agent: Agent | None = None
```

- [ ] **Fix remaining `Incompatible types` errors**

The session_id parameter comes from `form_session_id: UploadFile | None = None`. After the fix in 0.5, ensure session_id is properly typed as `str | None`:

```python
session_id: str | None = str(form_session_id) if form_session_id else form_session_id  # type: ignore[assignment]
```

Add `list[Any]` / `dict[str, Any]` type arguments where needed.

- [ ] **Verify 0 mypy errors in server/app.py**

```bash
cd /Users/mac/AI/CScode && python3 -m mypy src/cscode/server/app.py --ignore-missing-imports
```
Expected: 0 errors

- [ ] **Run all tests**

```bash
cd /Users/mac/AI/CScode && python3 -m pytest tests/ -q --tb=short
```
Expected: 135 passed

- [ ] **Commit**

```bash
git add src/cscode/server/app.py
git commit -m "fix: add module-level type annotations in server"
```

---

### Task 0.7: Migrate FastAPI `on_event` to lifespan

**Files:**
- Modify: `src/cscode/server/app.py`

**Problem:** `@app.on_event("startup")` and `@app.on_event("shutdown")` are deprecated in FastAPI. Replace with the `lifespan` async context manager pattern.

- [ ] **Replace `on_event` startup/shutdown with lifespan**

Remove:
```python
@app.on_event("startup")
async def startup() -> None:
    ...

@app.on_event("shutdown")
async def shutdown() -> None:
    ...
```

Add at module level (near `app = FastAPI()`):
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # startup
    global _db, _session_store, _agent
    resource_dir = os.environ.get("CSCORE_RESOURCE_DIR", "")
    if resource_dir:
        python_dir = os.path.join(resource_dir, "python")
        if os.path.isdir(python_dir):
            existing = os.environ.get("PYTHONPATH", "")
            os.environ["PYTHONPATH"] = f"{python_dir}{os.pathsep}{existing}" if existing else python_dir

    _db = Database()
    await _db.init()
    _session_store = SessionStore(_db)

    os.makedirs("/tmp/cscode-outputs", exist_ok=True)
    template_path = "/tmp/cscode-outputs/xlsx_template.py"
    if not os.path.exists(template_path):
        with open(template_path, "w") as f:
            f.write(_XLSX_TEMPLATE)
        os.chmod(template_path, 0o755)

    config = load_config()
    provider = create_provider(config)
    registry = ToolRegistry()
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(BashTool())
    registry.register(GrepTool())
    registry.register(GlobTool())
    registry.register(LsTool())
    registry.register(BrowserTool())
    _agent = Agent(
        config=config,
        provider=provider,
        registry=registry,
        options=AgentOptions(
            max_tool_rounds=15,
            timeout=600.0,
            system_prompt=SYSTEM_PROMPT,  # keep existing content from current file
        ),
    )

    yield  # app runs here

    # shutdown
    if _db is not None:
        await _db.close()
```

Then update the `FastAPI()` instantiation:
```python
app = FastAPI(lifespan=lifespan)
```

- [ ] **Verify tests pass**

```bash
cd /Users/mac/AI/CScode && python3 -m pytest tests/ -q --tb=short
```
Expected: 135 passed, 0 deprecation warnings for `on_event`

- [ ] **Commit**

```bash
git add src/cscode/server/app.py
git commit -m "fix: migrate FastAPI from on_event to lifespan"
```

---

### Task 0.8: Fix mypy errors — remaining files (tui, storage, utils, tools)

**Files:**
- Modify: `src/cscode/tui/app.py`
- Modify: `src/cscode/storage/session.py`
- Modify: `src/cscode/storage/db.py`
- Modify: `src/cscode/utils/file_parser.py`
- Modify: `src/cscode/core/session_manager.py`
- Modify: `src/cscode/providers/openai.py`
- Modify: `src/cscode/providers/anthropic.py`
- Modify: `src/cscode/providers/ollama.py`

- [ ] **Run mypy to see remaining errors**

```bash
cd /Users/mac/AI/CScode && python3 -m mypy src/cscode/ --ignore-missing-imports | grep -v "test_" | grep "error:"
```

- [ ] **Fix `tui/app.py:33` — Missing type arguments for `App`**

```python
class CScodeApp(App[None]):  # Add [None] type arg
```

- [ ] **Fix storage module errors**

Add proper type annotations to all public methods in `session.py` and `db.py`.

- [ ] **Fix remaining errors in providers**

Ensure provider methods have return type annotations.

- [ ] **Final mypy check — 0 errors**

```bash
cd /Users/mac/AI/CScode && python3 -m mypy src/cscode/ --ignore-missing-imports
```
Expected: 0 errors

- [ ] **Run all tests**

```bash
cd /Users/mac/AI/CScode && python3 -m pytest tests/ -q --tb=short
```
Expected: 135 passed

- [ ] **Commit**

```bash
git add src/cscode/
git commit -m "fix: resolve all mypy type errors across codebase"
```

---

### Task 0.9: Add ruff to pyproject.toml config

**Files:**
- Modify: `pyproject.toml`

- [ ] **Add ruff lint configuration**

The current ruff config only has `target-version` and `line-length`. Add explicit lint rules to prevent regression:

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I"]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]

[tool.ruff.lint.isort]
known-first-party = ["cscode"]
```

- [ ] **Commit**

```bash
git add pyproject.toml
git commit -m "chore: add ruff lint rules to pyproject.toml"
```

---

### Task 0.10: Add structured logging

**Files:**
- Create: `src/cscode/utils/logging.py`
- Modify: `src/cscode/core/engine.py`

**Problem:** Current code uses `print()` for debug output and has no structured logging.

- [ ] **Create `utils/logging.py`**

```python
from __future__ import annotations

import logging
import sys
from typing import Any


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
```

- [ ] **Replace `print()` calls in engine.py with logger**

In `engine.py`, replace:
```python
print(f"  FILE_GUARD: blocked {func_name} (files attached)")
```
with:
```python
logger.warning("FILE_GUARD: blocked %s (files attached)", func_name)
```
And import logger:
```python
from cscode.utils.logging import get_logger
logger = get_logger(__name__)
```

Replace all `print(f"TOOL: ...")` and `print(f"  FILE_GUARD: ...")` calls with appropriate `logger.info()` / `logger.warning()` calls.

- [ ] **Run tests to verify**

```bash
cd /Users/mac/AI/CScode && python3 -m pytest tests/ -q --tb=short
```
Expected: 135 passed

- [ ] **Commit**

```bash
git add src/cscode/utils/logging.py src/cscode/core/engine.py
git commit -m "feat: add structured logging, replace print() in engine"
```


### Task 0.11: Standardize error handling patterns

**Files:**
- Create: `src/cscode/core/errors.py`
- Modify: `src/cscode/core/engine.py`
- Modify: `src/cscode/server/app.py`

**Problem:** Error handling is ad-hoc — some places raise generic `Exception`, others return error strings, others silently swallow errors.

- [ ] **Create `core/errors.py` with typed error hierarchy**

```python
from __future__ import annotations


class CScodeError(Exception):
    """Base exception for all CScode errors."""


class ConfigError(CScodeError):
    """Configuration related errors."""


class ProviderError(CScodeError):
    """LLM provider errors."""


class ToolError(CScodeError):
    """Tool execution errors."""


class SessionError(CScodeError):
    """Session management errors."""


class PermissionDenied(CScodeError):
    """User denied a permission request."""
```

- [ ] **Migrate existing error classes**

Update `config.py` to import `ConfigError` from new module instead of defining its own.

- [ ] **Update provider base to use ProviderError**

Update `providers/base.py`:
```python
from cscode.core.errors import ProviderError
```
Remove the duplicate `class ProviderError(Exception):` definition.

- [ ] **Run tests**

```bash
cd /Users/mac/AI/CScode && python3 -m pytest tests/ -q --tb=short
```
Expected: 135 passed

- [ ] **Commit**

```bash
git add src/cscode/core/errors.py src/cscode/core/config.py src/cscode/providers/base.py
git commit -m "refactor: standardize error hierarchy with CScodeError base"
```


### Task 0.12: Run full verification — the "Green Check"

- [ ] **Final full test run**

```bash
cd /Users/mac/AI/CScode && python3 -m pytest tests/ -v --tb=short 2>&1
```
Expected: 135 passed, 0 failed

- [ ] **Final ruff check**

```bash
cd /Users/mac/AI/CScode && python3 -m ruff check src/cscode/
```
Expected: 0 errors

- [ ] **Final mypy check**

```bash
cd /Users/mac/AI/CScode && python3 -m mypy src/cscode/ --ignore-missing-imports
```
Expected: 0 errors

- [ ] **Final deprecation warning check**

```bash
cd /Users/mac/AI/CScode && python3 -m pytest tests/ -q -W error::DeprecationWarning 2>&1 | tail -5
```
Expected: no deprecation warnings from our code (stdlib deprecations ok)

- [ ] **Final commit with Phase 0 completion marker**

```bash
git add -A
git commit -m "chore: complete Phase 0 foundation hardening

- Fix all 90 mypy errors
- Fix all 24 ruff errors
- Migrate FastAPI to lifespan pattern
- Add test dependency declarations
- Add ruff lint configuration"
```
