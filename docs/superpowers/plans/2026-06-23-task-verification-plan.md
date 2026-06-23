# Task Verification & Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add task tracking, evidence verification, and anti-inference mechanisms to CScode for enterprise-grade test reliability.

**Architecture:** LLM calls tools with task_id → tools inject evidence into metadata → engine emits enriched events → TaskTracker writes to task_verifications projection table → report API queries database (not LLM text).

**Tech Stack:** Python 3.12+, aiosqlite, FastAPI, Playwright, TypeScript/React

---

### Task 1: Fix session content leaking (P0)

**Files:**
- Modify: `src/cscode/web/src/hooks/useChat.ts:137`

- [ ] **Step 1: Add activeSessionId check to isCurrent()**

```typescript
// Line 137, change:
const isCurrent = () => streamControllers[sid] === controller;

// To:
const isCurrent = () => {
  const activeId = useSessionStore.getState().activeSessionId;
  return streamControllers[sid] === controller && activeId === sid;
};
```

- [ ] **Step 2: Verify frontend builds**

Run: `cd src/cscode/web && npm run build`
Expected: Build succeeds without errors.

- [ ] **Step 3: Commit**

```bash
git add src/cscode/web/src/hooks/useChat.ts
git commit -m "fix: prevent SSE events from stale sessions leaking to active session"
```

---

### Task 2: Add database migration v005 (P1)

**Files:**
- Modify: `src/cscode/storage/db.py:32,109-120`

- [ ] **Step 1: Add migration_005 function**

Add after `_migration_004` (line 119):

```python
async def _migration_005(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS expected_tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            task_id     TEXT NOT NULL,
            description TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(session_id, task_id)
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS task_verifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            task_id     TEXT NOT NULL,
            tool_name   TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'UNVERIFIED',
            verified    INTEGER NOT NULL,
            evidence    TEXT NOT NULL,
            result_summary TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(session_id, task_id, tool_name)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_tv_session ON task_verifications(session_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_tv_status ON task_verifications(session_id, status)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_et_session ON expected_tasks(session_id)")
```

- [ ] **Step 2: Register migration_005 in migrations list**

Change line 32:
```python
# From:
migrations = [_migration_001, _migration_002, _migration_003, _migration_004]
# To:
migrations = [_migration_001, _migration_002, _migration_003, _migration_004, _migration_005]
```

- [ ] **Step 3: Add fetchall method to Database class**

Add after `fetchone` method (line 44):

```python
async def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
    cursor = await self.conn.execute(query, params)
    return await cursor.fetchall()
```

- [ ] **Step 4: Verify migration runs**

Run: `python3 -c "
import asyncio
from cscode.storage.db import Database
async def test():
    db = Database(db_path='/tmp/test_cscode_verify.db')
    await db.init()
    tables = await db.fetchall(\"SELECT name FROM sqlite_master WHERE type='table'\")
    print([r['name'] for r in tables])
    await db.close()
asyncio.run(test())
"`
Expected: Output includes `expected_tasks` and `task_verifications`.

- [ ] **Step 5: Commit**

```bash
git add src/cscode/storage/db.py
git commit -m "feat: add migration v005 - expected_tasks and task_verifications tables"
```

---

### Task 3: Create TaskTracker (P1)

**Files:**
- Create: `src/cscode/core/tracker.py`

- [ ] **Step 1: Write the test file**

Create `tests/test_tracker.py`:

```python
from __future__ import annotations

import asyncio
import json
import os
import tempfile

import pytest
from cscode.core.tracker import TaskTracker
from cscode.storage.db import Database


@pytest.fixture
async def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(db_path=path)
    await database.init()
    yield database
    await database.close()
    os.unlink(path)


@pytest.mark.asyncio
async def test_tracker_handles_tool_success_with_evidence(db):
    tracker = TaskTracker(db)
    event = {
        "type": "tool.success",
        "data": {
            "name": "browser",
            "result": "Screenshot saved",
            "args": {"task_id": "TC-001", "action": "screenshot"},
            "metadata": {
                "task_id": "TC-001",
                "evidence": json.dumps({"screenshot_path": "/tmp/ss.png", "html": True, "html_length": 100, "content_length": 500}),
                "verified": "True",
            },
        },
    }
    await tracker.handle_event("session-1", event)

    rows = await db.fetchall(
        "SELECT * FROM task_verifications WHERE session_id = ? AND task_id = ?",
        ("session-1", "TC-001"),
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "EXECUTED"
    assert rows[0]["verified"] == 1


@pytest.mark.asyncio
async def test_tracker_handles_tool_failed(db):
    tracker = TaskTracker(db)
    event = {
        "type": "tool.failed",
        "data": {
            "name": "browser",
            "error": "Timeout",
            "args": {"task_id": "TC-002"},
            "metadata": {"task_id": "TC-002"},
        },
    }
    await tracker.handle_event("session-1", event)

    rows = await db.fetchall(
        "SELECT * FROM task_verifications WHERE session_id = ? AND task_id = ?",
        ("session-1", "TC-002"),
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["verified"] == 0


@pytest.mark.asyncio
async def test_tracker_skips_events_without_task_id(db):
    tracker = TaskTracker(db)
    event = {
        "type": "tool.success",
        "data": {
            "name": "read",
            "result": "file content",
            "args": {"file_path": "/tmp/test.txt"},
            "metadata": {},
        },
    }
    await tracker.handle_event("session-1", event)

    rows = await db.fetchall("SELECT * FROM task_verifications")
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_tracker_unverified_when_no_evidence(db):
    tracker = TaskTracker(db)
    event = {
        "type": "tool.success",
        "data": {
            "name": "browser",
            "result": "",
            "args": {"task_id": "TC-003", "action": "get_text"},
            "metadata": {
                "task_id": "TC-003",
                "evidence": json.dumps({"screenshot_path": "", "html": False, "html_length": 0, "content_length": 0}),
                "verified": "False",
            },
        },
    }
    await tracker.handle_event("session-1", event)

    rows = await db.fetchall(
        "SELECT * FROM task_verifications WHERE session_id = ? AND task_id = ?",
        ("session-1", "TC-003"),
    )
    assert rows[0]["status"] == "UNVERIFIED"


@pytest.mark.asyncio
async def test_get_execution_report(db):
    tracker = TaskTracker(db)
    await db.execute(
        "INSERT INTO task_verifications (session_id, task_id, tool_name, status, verified, evidence, result_summary) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("session-1", "TC-001", "browser", "EXECUTED", 1, '{"html":true}', "ok"),
    )
    await db.execute(
        "INSERT INTO task_verifications (session_id, task_id, tool_name, status, verified, evidence, result_summary) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("session-1", "TC-002", "browser", "UNVERIFIED", 0, '{}', ""),
    )

    report = await tracker.get_execution_report("session-1")
    assert report["summary"]["executed"] == 1
    assert report["summary"]["unverified"] == 1
    assert len(report["details"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tracker.py -v`
Expected: All 5 tests FAIL (TaskTracker not defined).

- [ ] **Step 3: Write TaskTracker implementation**

Create `src/cscode/core/tracker.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from cscode.storage.db import Database


@dataclass
class TaskStatus:
    session_id: str
    task_id: str
    tool_name: str
    status: str
    evidence: dict = field(default_factory=dict)
    result_summary: str = ""
    timestamp: str = ""


class TaskTracker:
    """Receives tool events via handle_event callback, writes to task_verifications projection table."""

    def __init__(self, db: Database):
        self.db = db

    async def handle_event(self, session_id: str, event: dict[str, Any]) -> None:
        evt_type = event.get("type", "")
        if evt_type not in ("tool.success", "tool.failed"):
            return

        data = event.get("data", {})
        args = data.get("args", {})
        metadata = data.get("metadata", {})

        task_id = args.get("task_id") or metadata.get("task_id", "")
        if not task_id:
            return

        tool_name = data.get("name", "unknown")

        if evt_type == "tool.success":
            evidence_raw = metadata.get("evidence", "{}")
            evidence = json.loads(evidence_raw) if isinstance(evidence_raw, str) else evidence_raw
            verified = self._verify_evidence(tool_name, evidence)
            status = "EXECUTED" if verified else "UNVERIFIED"
            result_summary = data.get("result", "")[:500]
        else:
            evidence = {}
            verified = False
            status = "FAILED"
            result_summary = data.get("error", "")[:500]

        await self.db.execute(
            """INSERT OR REPLACE INTO task_verifications
               (session_id, task_id, tool_name, status, verified, evidence, result_summary)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [session_id, task_id, tool_name, status, int(verified),
             json.dumps(evidence), result_summary],
        )

    def _verify_evidence(self, tool: str, evidence: dict) -> bool:
        if tool == "browser":
            return bool(evidence.get("screenshot_path")) or evidence.get("html", False)
        if tool == "bash":
            return evidence.get("content_length", 0) > 0
        return bool(evidence)

    async def get_execution_report(self, session_id: str) -> dict:
        rows = await self.db.fetchall(
            "SELECT task_id, status, verified, evidence, result_summary, created_at "
            "FROM task_verifications WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        executed = [r for r in rows if r["status"] == "EXECUTED"]
        failed = [r for r in rows if r["status"] == "FAILED"]
        unverified = [r for r in rows if r["status"] == "UNVERIFIED"]

        return {
            "summary": {
                "executed": len(executed),
                "failed": len(failed),
                "unverified": len(unverified),
                "skipped": 0,
            },
            "details": [
                {
                    "task_id": r["task_id"],
                    "status": r["status"],
                    "evidence": json.loads(r["evidence"]) if r["evidence"] else {},
                    "result_summary": r["result_summary"],
                    "timestamp": r["created_at"],
                }
                for r in rows
            ],
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tracker.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cscode/core/tracker.py tests/test_tracker.py
git commit -m "feat: add TaskTracker with event handling and execution report"
```

---

### Task 4: Add ToolRegistry context support (P1)

**Files:**
- Modify: `src/cscode/tools/base.py:59-83`

- [ ] **Step 1: Add context parameter to execute_tool_call**

Change `execute_tool_call` in `ToolRegistry` class (line 59):

```python
async def execute_tool_call(self, tool_call: dict[str, Any], context: dict | None = None) -> ToolResult:
    fn_info = tool_call.get("function", {})
    name = fn_info.get("name", "")
    raw_args = fn_info.get("arguments", "{}")
    if isinstance(raw_args, str):
        import json
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError as e:
            return ToolResult(
                success=False,
                data="",
                error=f"Failed to parse arguments for tool '{name}': {e}",
            )
    else:
        args = raw_args

    tool = self.get(name)
    if tool is None:
        return ToolResult(
            success=False,
            data="",
            error=f"Unknown tool: {name}",
        )
    import inspect
    sig = inspect.signature(tool.execute)
    if "context" in sig.parameters:
        return await tool.execute(args, context=context)
    return await tool.execute(args)
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `pytest tests/ -v -k "not test_tracker" --timeout=60`
Expected: All existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/cscode/tools/base.py
git commit -m "feat: add context parameter to ToolRegistry.execute_tool_call"
```

---

### Task 5: Add session_id to Agent and pass context in engine (P1)

**Files:**
- Modify: `src/cscode/core/engine.py:29-41,414`

- [ ] **Step 1: Add session_id attribute to Agent**

Add after `self.options = options or AgentOptions()` (line 41):

```python
self.session_id: str = ""
```

- [ ] **Step 2: Pass context to execute_tool_call in run_loop_events**

Change line 414 in `run_loop_events`:
```python
# From:
tool_result = await self.registry.execute_tool_call(tool_call)
# To:
context = {"session_id": self.session_id}
tool_result = await self.registry.execute_tool_call(tool_call, context=context)
```

- [ ] **Step 3: Also update _run_loop (line 230)**

Change line 230 in `_run_loop`:
```python
# From:
tool_result = await self.registry.execute_tool_call(tool_call)
# To:
context = {"session_id": self.session_id}
tool_result = await self.registry.execute_tool_call(tool_call, context=context)
```

- [ ] **Step 4: Verify existing tests still pass**

Run: `pytest tests/ -v -k "not test_tracker" --timeout=60`
Expected: All existing tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cscode/core/engine.py
git commit -m "feat: add session_id to Agent and pass context to tool calls"
```

---

### Task 6: Update TodoWriteTool with db injection and expected_tasks sync (P1)

**Files:**
- Modify: `src/cscode/tools/todowrite.py:1-40`

- [ ] **Step 1: Add id field to parameters schema and db injection**

Replace entire file:

```python
from __future__ import annotations

from typing import Any

from cscode.storage.db import Database
from cscode.tools.base import BaseTool, ToolResult


class TodoWriteTool(BaseTool):
    name = "todowrite"
    description = "Create and manage a task list for the current coding session. Use id field with format TC-XXX for test case tracking."
    requires_permission = False
    permission_default = "allow"
    parameters = {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Task ID (format: TC-XXX for test cases)"},
                        "content": {"type": "string", "description": "Task description"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["content", "status", "priority"],
                },
                "description": "List of tasks to track",
            },
        },
        "required": ["todos"],
    }

    def __init__(self, db: Database | None = None):
        super().__init__()
        self._db = db

    async def execute(self, args: dict[str, Any], context: dict | None = None) -> ToolResult:
        todos = args["todos"]
        session_id = context.get("session_id", "") if context else ""

        if self._db and session_id:
            for t in todos:
                task_id = t.get("id", "")
                if task_id:
                    await self._db.execute(
                        "INSERT OR IGNORE INTO expected_tasks (session_id, task_id, description) "
                        "VALUES (?, ?, ?)",
                        (session_id, task_id, t["content"]),
                    )

        lines = []
        for t in todos:
            status_map = {"pending": " ", "in_progress": "●", "completed": "✓", "cancelled": "✗"}
            marker = status_map.get(t.get("status", "pending"), " ")
            task_id = t.get("id", "")
            id_prefix = f"[{task_id}] " if task_id else ""
            lines.append(f"[{marker}] {t.get('priority', 'medium').upper()} {id_prefix}{t['content']}")
        return ToolResult(success=True, data="\n".join(lines) if lines else "No todos.")
```

- [ ] **Step 2: Update app.py to inject db into TodoWriteTool**

In `src/cscode/server/app.py`, change line 172:
```python
# From:
registry.register(TodoWriteTool())
# To:
registry.register(TodoWriteTool(db=_db))
```

- [ ] **Step 3: Set session_id on agent before each run**

In `src/cscode/server/app.py`, after `_agent = Agent(...)` block (around line 178), add before the `process()` call in the chat stream handler (around line 482):

```python
# Before process() call, add:
_agent.session_id = session_id
```

- [ ] **Step 4: Verify existing tests still pass**

Run: `pytest tests/ -v --timeout=60`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cscode/tools/todowrite.py src/cscode/server/app.py
git commit -m "feat: add db injection to TodoWriteTool, sync to expected_tasks, set session_id on agent"
```

---

### Task 7: Enhance system prompt with CRITICAL RULES (P1)

**Files:**
- Modify: `src/cscode/server/app.py:184-230`

- [ ] **Step 1: Append CRITICAL RULES to system prompt**

After the existing system prompt (around line 230, before the closing `"""`), append:

```python

CRITICAL RULES FOR TESTING — VIOLATION WILL BE DETECTED:
1. Every test case MUST be executed through real tool calls (browser, bash, etc.).
   Each tool call is recorded and verified. You CANNOT fake execution.
2. NEVER infer or guess test results from documentation, code, or prior knowledge.
   If you did not call a tool, the result does not exist.
3. If a test cannot be executed (no credentials, blocked URL, timeout):
   Mark it "SKIPPED: <reason>" — do NOT mark it as passed or failed.
4. For browser tests, you MUST capture BOTH screenshot AND HTML content.
   A test without both is UNVERIFIED and will not count as executed.
5. task_id format MUST be: TC-XXX (XXX is 3-digit number, e.g. TC-001, TC-002).
   Use this format consistently in todowrite and all tool calls.
6. In your final response, use this format for each test case:
   [EXECUTED]   TC-001 — Login success — evidence: screenshot + HTML
   [FAILED]     TC-002 — Login failure — error: timeout
   [SKIPPED]    TC-003 — Payment test — reason: no test credentials
   [UNVERIFIED] TC-004 — Empty page — re-run needed
7. The verification report is generated from the database, not from your text.
   You cannot "convince" the system — only real tool calls count.""",
```

- [ ] **Step 2: Verify server starts**

Run: `python3 -c "from cscode.server.app import app; print('OK')"`
Expected: Prints "OK" without errors.

- [ ] **Step 3: Commit**

```bash
git add src/cscode/server/app.py
git commit -m "feat: add CRITICAL RULES to system prompt - anti-inference, evidence enforcement"
```

---

### Task 8: Add evidence injection to Browser tool (P2)

**Files:**
- Modify: `src/cscode/tools/browser.py:24-175`

- [ ] **Step 1: Add task_id to parameters schema**

Change the parameters dict (line 27), add after `"action"` property:

```python
"task_id": {"type": "string", "description": "Test case ID (format: TC-XXX) for tracking"},
```

- [ ] **Step 2: Add evidence injection to execute method**

Add imports at top:
```python
import json
from datetime import datetime, timezone
```

Add constant after imports:
```python
EVIDENCE_DIR = "/tmp/cscode-outputs/evidence"
```

Modify the `execute` method to inject evidence. Replace the entire method body with context-aware evidence injection. Add `context` parameter to `execute`:

```python
async def execute(self, args: dict[str, Any], context: dict | None = None) -> ToolResult:
    session_id = context.get("session_id", "") if context else ""
```

Then before each `return ToolResult(...)`, add:

```python
task_id = args.get("task_id", "")
evidence = {
    "screenshot_path": "",
    "html": False,
    "html_length": 0,
    "content_length": 0,
    "timestamp": datetime.now(timezone.utc).isoformat(),
}
verified = bool(evidence["screenshot_path"]) or evidence["html"]
```

Then for specific actions, set evidence fields:

For `screenshot` action (around line 93-102):
```python
elif action == "screenshot":
    path = args.get("path", "/tmp/cscode-outputs/screenshot.png")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if task_id:
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        path = os.path.join(EVIDENCE_DIR, f"{session_id}_{task_id}_screenshot.png")
    assert _page is not None
    await _page.screenshot(path=path, full_page=True)
    evidence["screenshot_path"] = path
    evidence["content_length"] = os.path.getsize(path) if os.path.exists(path) else 0
    verified = bool(evidence["screenshot_path"])
    result = ToolResult(
        success=True,
        data=f"Screenshot saved to {path}",
        metadata={"task_id": task_id, "evidence": json.dumps(evidence), "verified": str(verified)},
    )
    return result
```

For `get_text` action (around line 104-110):
```python
elif action == "get_text":
    selector = args.get("selector")
    if not selector:
        return ToolResult(success=False, data="", error="selector is required for get_text action")
    assert _page is not None
    text = await _page.locator(selector).text_content()
    evidence["html"] = bool(text)
    evidence["html_length"] = len(text) if text else 0
    evidence["content_length"] = len(text) if text else 0
    # get_text 单独不满足验证（缺 screenshot_path），必须配合 screenshot 调用
    verified = bool(evidence["screenshot_path"]) or evidence["html"]
    return ToolResult(
        success=True,
        data=text or "",
        metadata={"selector": selector, "task_id": task_id, "evidence": json.dumps(evidence), "verified": str(verified)},
    )
```

For `get_html` action (around line 112-127):
```python
elif action == "get_html":
    selector = args.get("selector")
    assert _page is not None
    if selector:
        html = await _page.locator(selector).inner_html()
    else:
        html = await _page.content()
    import re
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    html = re.sub(r'<svg[^>]*>.*?</svg>', '', html, flags=re.DOTALL)
    html = re.sub(r'\s+', ' ', html).strip()
    truncated = html[:8000]
    if len(html) > 8000:
        truncated += "\n\n[truncated: output too long]"
    evidence["html"] = bool(html)
    evidence["html_length"] = len(html)
    evidence["content_length"] = len(html)
    # get_html 单独不满足验证（缺 screenshot_path），必须配合 screenshot 调用
    verified = bool(evidence["screenshot_path"]) or evidence["html"]
    return ToolResult(
        success=True,
        data=truncated,
        metadata={"task_id": task_id, "evidence": json.dumps(evidence), "verified": str(verified)},
    )
```

For all other actions (open, click, type, press, wait, scroll, close, status), add metadata to existing returns:
```python
result = ToolResult(success=True, data="...", metadata={"task_id": task_id})
```

For the error catch at the end (line 174-175):
```python
except Exception as e:
    return ToolResult(
        success=False,
        data="",
        error=str(e),
        metadata={"task_id": task_id, "evidence": json.dumps(evidence), "verified": "False"},
    )
```

- [ ] **Step 3: Verify existing tests still pass**

Run: `pytest tests/ -v --timeout=60`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/cscode/tools/browser.py
git commit -m "feat: add task_id and evidence injection to Browser tool"
```

---

### Task 9: Add evidence injection to Bash tool (P2)

**Files:**
- Modify: `src/cscode/tools/bash.py:9-70`

- [ ] **Step 1: Add task_id to parameters and evidence injection**

Add import:
```python
import json
from datetime import datetime, timezone
```

Add `task_id` to parameters schema (line 12):
```python
"task_id": {"type": "string", "description": "Test case ID (format: TC-XXX) for tracking"},
```

Modify execute method to inject evidence. After computing `output` and before each `return ToolResult(...)`, add:

```python
task_id = args.get("task_id", "")
evidence = {
    "content_length": len(stdout) + len(stderr) if exit_code == 0 else 0,
    "exit_code": exit_code,
    "timestamp": datetime.now(timezone.utc).isoformat(),
}
verified = evidence["content_length"] > 0
```

Then update all `ToolResult(...)` returns to include metadata. For the success case (line 60-64):
```python
return ToolResult(
    success=True,
    data=output,
    metadata={"exit_code": "0", "task_id": task_id, "evidence": json.dumps(evidence), "verified": str(verified)},
)
```

For the failure case (line 54-59):
```python
return ToolResult(
    success=False,
    data=output,
    error=f"Exit code {exit_code}",
    metadata={"exit_code": str(exit_code), "task_id": task_id, "evidence": json.dumps(evidence), "verified": str(verified)},
)
```

For timeout (line 42-46):
```python
return ToolResult(
    success=False,
    data="",
    error=f"Command timed out after {timeout_s}s",
    metadata={"task_id": task_id, "evidence": json.dumps({"content_length": 0, "exit_code": -1, "timestamp": datetime.now(timezone.utc).isoformat()}), "verified": "False"},
)
```

For FileNotFoundError (line 66-70):
```python
return ToolResult(
    success=False,
    data="",
    error=f"Command not found: {e}",
    metadata={"task_id": task_id, "evidence": json.dumps({"content_length": 0, "exit_code": -1, "timestamp": datetime.now(timezone.utc).isoformat()}), "verified": "False"},
)
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `pytest tests/ -v --timeout=60`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/cscode/tools/bash.py
git commit -m "feat: add task_id and evidence injection to Bash tool"
```

---

### Task 10: Extend engine events with args and metadata (P2)

**Files:**
- Modify: `src/cscode/core/engine.py:415-418`

- [ ] **Step 1: Extend tool.success and tool.failed events in run_loop_events**

Change lines 415-418:
```python
# From:
if tool_result.success:
    await _emit({"type": "tool.success", "data": {"name": func_name, "result": (tool_result.data or "")[:200]}})
else:
    await _emit({"type": "tool.failed", "data": {"name": func_name, "error": (tool_result.error or "")[:200]}})

# To:
if tool_result.success:
    await _emit({"type": "tool.success", "data": {
        "name": func_name,
        "result": (tool_result.data or "")[:200],
        "args": fn_args,
        "metadata": tool_result.metadata,
    }})
else:
    await _emit({"type": "tool.failed", "data": {
        "name": func_name,
        "error": (tool_result.error or "")[:200],
        "args": fn_args,
        "metadata": tool_result.metadata,
    }})
```

- [ ] **Step 2: Also update _run_loop (line 232-233)**

Change lines 232-233 in `_run_loop`:
```python
# From:
await _emit({"type": "tool:complete", "name": func_name, "success": tool_result.success, "content": result_preview})

# To:
await _emit({"type": "tool:complete", "name": func_name, "success": tool_result.success, "content": result_preview, "args": fn_args, "metadata": tool_result.metadata})
```

- [ ] **Step 3: Verify existing tests still pass**

Run: `pytest tests/ -v --timeout=60`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/cscode/core/engine.py
git commit -m "feat: extend tool events with args and metadata for TaskTracker"
```

---

### Task 11: Integrate TaskTracker into app.py and add report API (P2)

**Files:**
- Modify: `src/cscode/server/app.py:149,461-477`

- [ ] **Step 1: Initialize TaskTracker in app startup**

After `_compactor = Compactor(...)` (line 152), add:
```python
from cscode.core.tracker import TaskTracker
_tracker = TaskTracker(_db)

# 证据目录预创建
EVIDENCE_DIR = "/tmp/cscode-outputs/evidence"
os.makedirs(EVIDENCE_DIR, exist_ok=True)
```

- [ ] **Step 2: Add tracker.handle_event call in on_event callback**

In the `on_event` function (around line 461), after the EventStore.append block (line 477), add:
```python
# Notify TaskTracker
if _tracker is not None:
    await _tracker.handle_event(session_id, event)
```

- [ ] **Step 3: Add verification report API endpoint**

Add new route after existing routes (before `if __name__ == "__main__"`):

```python
@app.get("/sessions/{session_id}/verification-report")
async def get_verification_report(session_id: str):
    """Return database-backed verification report, not LLM-generated text."""
    if _tracker is None:
        return {"error": "TaskTracker not initialized"}

    report = await _tracker.get_execution_report(session_id)

    # Calculate SKIPPED: expected tasks not in verification table
    all_expected = await _db.fetchall(
        "SELECT task_id FROM expected_tasks WHERE session_id = ?",
        (session_id,),
    )
    expected_ids = {r["task_id"] for r in all_expected}
    recorded_ids = {d["task_id"] for d in report["details"]}
    skipped = expected_ids - recorded_ids

    report["summary"]["skipped"] = len(skipped)
    report["details"].extend([
        {"task_id": tid, "status": "SKIPPED", "evidence": {}, "result_summary": "", "timestamp": None}
        for tid in skipped
    ])

    return report
```

- [ ] **Step 4: Verify server starts**

Run: `python3 -c "from cscode.server.app import app; print('OK')"`
Expected: Prints "OK" without errors.

- [ ] **Step 5: Commit**

```bash
git add src/cscode/server/app.py
git commit -m "feat: integrate TaskTracker into app.py, add verification report API"
```

---

### Task 12: Final verification (P2)

**Files:**
- None (verification only)

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v --timeout=60`
Expected: All tests PASS.

- [ ] **Step 2: Run linting**

Run: `cd src/cscode/web && npm run lint 2>/dev/null || echo "No lint script"`
Expected: No errors.

- [ ] **Step 3: Verify frontend builds**

Run: `cd src/cscode/web && npm run build`
Expected: Build succeeds.

- [ ] **Step 4: Verify server imports cleanly**

Run: `python3 -c "
from cscode.core.tracker import TaskTracker
from cscode.storage.db import Database
from cscode.tools.todowrite import TodoWriteTool
from cscode.tools.browser import BrowserTool
from cscode.tools.bash import BashTool
print('All imports OK')
"`
Expected: Prints "All imports OK".

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final verification - all tests pass, imports clean"
```
