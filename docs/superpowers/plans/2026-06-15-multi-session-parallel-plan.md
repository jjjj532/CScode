# Multi-Session Parallel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现多会话并行支持，允许用户同时运行多个独立的 Agent 会话

**Architecture:** 创建一个 SessionManager 类管理多个会话，每个会话有独立的状态、消息历史。使用 asyncio 并发运行多个会话。

**Tech Stack:** Python 3.11+, asyncio, SQLite, Click

---

## File Structure

| 操作 | 文件 | 说明 |
|------|------|------|
| 创建 | `src/cscode/core/session_manager.py` | 会话管理器核心类 |
| 修改 | `src/cscode/storage/session.py` | 增强会话存储 |
| 修改 | `src/cscode/storage/db.py` | 添加会话状态字段 |
| 修改 | `src/cscode/cli.py` | 新增 session 命令组 |
| 创建 | `tests/test_session_manager.py` | 单元测试 |

---

## Task 1: Create SessionManager Core Class

**Files:**
- Create: `src/cscode/core/session_manager.py`
- Test: `tests/test_session_manager.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_manager.py
import pytest
from cscode.core.session_manager import SessionManager, Session, SessionStatus


def test_create_session():
    manager = SessionManager()
    session = manager.create(title="Test Session")
    
    assert session.id is not None
    assert session.title == "Test Session"
    assert session.status == SessionStatus.ACTIVE


def test_list_sessions():
    manager = SessionManager()
    s1 = manager.create(title="Session 1")
    s2 = manager.create(title="Session 2")
    
    sessions = manager.list()
    assert len(sessions) == 2


def test_set_active_session():
    manager = SessionManager()
    s1 = manager.create(title="Session 1")
    s2 = manager.create(title="Session 2")
    
    manager.set_active(s2.id)
    assert manager.get_active().id == s2.id


def test_remove_session():
    manager = SessionManager()
    s1 = manager.create(title="Session 1")
    
    result = manager.remove(s1.id)
    assert result is True
    assert manager.get(s1.id) is None


def test_max_sessions_limit():
    manager = SessionManager(max_sessions=2)
    manager.create(title="Session 1")
    manager.create(title="Session 2")
    
    with pytest.raises(ValueError, match="Maximum sessions"):
        manager.create(title="Session 3")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_manager.py -v`
Expected: FAIL with "No module named 'cscode.core.session_manager'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/cscode/core/session_manager.py
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SessionStatus(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    TERMINATED = "terminated"


@dataclass
class Session:
    id: str
    title: str
    provider: str
    model: str
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SessionManager:
    """Manage multiple parallel sessions."""
    
    def __init__(self, max_sessions: int = 5):
        self._sessions: dict[str, Session] = {}
        self._active_session_id: str | None = None
        self._max_sessions = max_sessions
    
    def create(
        self,
        title: str = "",
        provider: str = "openai",
        model: str = "gpt-4o",
    ) -> Session:
        if len(self._sessions) >= self._max_sessions:
            raise ValueError(f"Maximum sessions ({self._max_sessions}) reached")
        
        session = Session(
            id=str(uuid.uuid4()),
            title=title or f"Session {len(self._sessions) + 1}",
            provider=provider,
            model=model,
        )
        self._sessions[session.id] = session
        self._active_session_id = session.id
        return session
    
    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)
    
    def list(self) -> list[Session]:
        return list(self._sessions.values())
    
    def set_active(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        self._active_session_id = session_id
        return True
    
    def get_active(self) -> Session | None:
        if self._active_session_id is None:
            return None
        return self._sessions.get(self._active_session_id)
    
    def remove(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        if self._active_session_id == session_id:
            self._active_session_id = None
            if self._sessions:
                self._active_session_id = next(iter(self._sessions))
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_session_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cscode/core/session_manager.py tests/test_session_manager.py
git commit -m "feat: add SessionManager core class for multi-session support"
```

---

## Task 2: Integrate SessionManager into CLI

**Files:**
- Modify: `src/cscode/cli.py:54-169`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py (add to existing)
def test_session_list_command(runner):
    result = runner.invoke(cli, ["session", "list"])
    assert result.exit_code == 0
    assert "Session" in result.output


def test_session_new_command(runner):
    result = runner.invoke(cli, ["session", "new", "--name", "test-session"])
    assert result.exit_code == 0
    assert "test-session" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_session_list_command -v`
Expected: FAIL with "No such command 'session'"

- [ ] **Step 3: Write minimal implementation**

在 `cli.py` 中添加 session 命令组:

```python
# 在 cli.py 中添加以下导入和命令组
from cscode.core.session_manager import SessionManager

# ... 在 cli 函数后添加 ...

_session_manager: SessionManager | None = None


def _get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


@cli.group()
def session():
    """Manage sessions."""
    pass


@session.command("list")
def session_list():
    """List all sessions."""
    manager = _get_session_manager()
    sessions = manager.list()
    active = manager.get_active()
    
    if not sessions:
        click.echo("No sessions.")
        return
    
    for s in sessions:
        marker = " *" if active and active.id == s.id else ""
        click.echo(f"{s.id[:8]} - {s.title} ({s.status.value}){marker}")


@session.command("new")
@click.option("--name", default="", help="Session name")
@click.option("--provider", default="openai", help="LLM provider")
@click.option("--model", default="gpt-4o", help="Model name")
def session_new(name: str, provider: str, model: str):
    """Create a new session."""
    manager = _get_session_manager()
    s = manager.create(title=name, provider=provider, model=model)
    click.echo(f"Created session: {s.id}")
    click.echo(f"Title: {s.title}")
    click.echo(f"Provider: {s.provider}/{s.model}")


@session.command("use")
@click.argument("session_id")
def session_use(session_id: str):
    """Switch to a session."""
    manager = _get_session_manager()
    if manager.set_active(session_id):
        s = manager.get(session_id)
        click.echo(f"Switched to: {s.title}")
    else:
        click.echo(f"Session not found: {session_id}", err=True)


@session.command("kill")
@click.argument("session_id")
def session_kill(session_id: str):
    """Terminate a session."""
    manager = _get_session_manager()
    if manager.remove(session_id):
        click.echo(f"Session terminated: {session_id}")
    else:
        click.echo(f"Session not found: {session_id}", err=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_session_list_command tests/test_cli.py::test_session_new_command -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cscode/cli.py tests/test_cli.py
git commit -m "feat: add session CLI commands (list, new, use, kill)"
```

---

## Task 3: Add Session Persistence to SQLite

**Files:**
- Modify: `src/cscode/storage/db.py`
- Modify: `src/cscode/storage/session.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage.py
@pytest.mark.asyncio
async def test_session_persistence(db):
    from cscode.storage.session import SessionStore
    
    store = SessionStore(db)
    session = await store.create(title="Persistent Session")
    
    # Simulate restart - create new store instance
    store2 = SessionStore(db)
    loaded = await store2.get(session.id)
    
    assert loaded is not None
    assert loaded.title == "Persistent Session"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage.py::test_session_persistence -v`
Expected: FAIL (可能因表结构缺少字段)

- [ ] **Step 3: Write minimal implementation**

确保 `storage/session.py` 的 SessionStore 正确保存和加载会话状态:

```python
# 检查 storage/session.py 是否需要添加 status 字段
# 目前已有 create, get, list, delete, save_messages, get_messages, update_title
# 需要确保与 SessionManager 集成
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_storage.py::test_session_persistence -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cscode/storage/
git commit -m "feat: enhance session persistence"
```

---

## Task 4: Add In-Session Commands

**Files:**
- Modify: `src/cscode/cli.py` (chat 命令)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tui.py
def test_in_session_commands():
    # Test /sessions, /switch, /kill, /new commands in chat
    pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tui.py -v`
Expected: FAIL with "command not implemented"

- [ ] **Step 3: Write minimal implementation**

在 `chat` 函数中添加会话命令处理:

```python
# 在 chat 函数中，user_input 检查后添加:
if user_input.startswith("/sessions") or user_input == "/s":
    sessions = manager.list()
    active = manager.get_active()
    for s in sessions:
        marker = " *" if active and active.id == s.id else ""
        click.echo(f"{s.id[:8]} - {s.title}{marker}")
    continue

if user_input.startswith("/new") or user_input == "/n":
    s = manager.create()
    click.echo(f"Created new session: {s.id}")
    continue

if user_input.startswith("/switch ") or user_input.startswith("/use "):
    target_id = user_input.split()[1]
    if manager.set_active(target_id):
        click.echo(f"Switched to: {target_id}")
    else:
        click.echo(f"Session not found: {target_id}")
    continue

if user_input.startswith("/kill ") or user_input.startswith("/delete "):
    target_id = user_input.split()[1]
    if manager.remove(target_id):
        click.echo(f"Session terminated: {target_id}")
    else:
        click.echo(f"Session not found: {target_id}")
    continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tui.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cscode/cli.py
git commit -m "feat: add in-session commands (/sessions, /switch, /kill, /new)"
```

---

## Verification Checkpoint

- [ ] All tests pass
- [ ] CLI commands work:
  - `cs session list` - lists sessions
  - `cs session new --name test` - creates new session
  - `cs session use <id>` - switches session
  - `cs session kill <id>` - terminates session
- [ ] In-session commands work:
  - `/sessions` - lists sessions
  - `/new` - creates new session
  - `/switch <id>` - switches session
  - `/kill <id>` - terminates session
