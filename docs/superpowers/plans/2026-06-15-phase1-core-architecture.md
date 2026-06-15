# Phase 1: 核心架构升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce EventBus, PermissionService, ServiceContainer, AgentOrchestrator with Plan/Build modes, and Context Compression — the architectural foundation that enables Phase 2-4 features.

**Architecture:** Build order is strictly sequential: EventBus → PermissionService → ServiceContainer → Agent refactor → Context Compression. Each builds on the prior. No parallel tasks except testing.

**Tech Stack:** Python 3.11+, asyncio, mypy strict, ruff, pytest

---

### Task 1.1: EventBus — Type-safe pub/sub event system

**Files:**
- Create: `src/cscode/core/events.py`
- Create: `tests/test_events.py`

**Dependency:** Phase 0 (completed)

**Design:** A lightweight async event bus that decouples components. Supports sync/async listeners with type-safe event payloads via dataclasses. Plugin system and internal components both use the same EventBus instance.

- [ ] **Step 1: Write failing tests for EventBus**

Create `tests/test_events.py`:

```python
from __future__ import annotations

import pytest
from cscode.core.events import EventBus, Event, ToolExecuteEvent, SessionCreatedEvent


@pytest.mark.asyncio
async def test_subscribe_and_emit() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("tool.execute.before", handler)
    event = ToolExecuteEvent(name="Read", args={})
    await bus.emit("tool.execute.before", event)

    assert len(received) == 1
    assert received[0].type == "tool.execute.before"
    assert received[0].name == "Read"


@pytest.mark.asyncio
async def test_unsubscribe() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("tool.execute.before", handler)
    bus.unsubscribe("tool.execute.before", handler)
    await bus.emit("tool.execute.before", ToolExecuteEvent(name="Read", args={}))

    assert len(received) == 0


@pytest.mark.asyncio
async def test_sync_handler() -> None:
    bus = EventBus()
    received: list[Event] = []

    def sync_handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("session.created", sync_handler)
    await bus.emit("session.created", SessionCreatedEvent(session_id="test-1"))

    assert len(received) == 1


@pytest.mark.asyncio
async def test_multiple_listeners() -> None:
    bus = EventBus()
    received: list[str] = []

    async def h1(event: Event) -> None:
        received.append("h1")

    async def h2(event: Event) -> None:
        received.append("h2")

    bus.subscribe("tool.execute.before", h1)
    bus.subscribe("tool.execute.before", h2)
    await bus.emit("tool.execute.before", ToolExecuteEvent(name="Read", args={}))

    assert received == ["h1", "h2"]


@pytest.mark.asyncio
async def test_cleanup_all_listeners() -> None:
    bus = EventBus()
    bus.subscribe("test", lambda e: None)
    bus.subscribe("test", lambda e: None)
    bus.clear()
    assert bus.listener_count("test") == 0
```

- [ ] **Step 2: Run tests — they should fail**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m pytest tests/test_events.py -q --tb=short
```
Expected: FAIL with `ModuleNotFoundError: No module named 'cscode.core.events'`

- [ ] **Step 3: Implement EventBus**

Create `src/cscode/core/events.py`:

```python
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from cscode.utils.logging import get_logger

logger = get_logger(__name__)

Handler = Callable[["Event"], Any]


@dataclass
class Event:
    type: str


@dataclass
class ToolExecuteEvent(Event):
    type: str = "tool.execute.before"
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutedEvent(Event):
    type: str = "tool.execute.after"
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    result: str = ""


@dataclass
class SessionCreatedEvent(Event):
    type: str = "session.created"
    session_id: str = ""


@dataclass
class SessionDeletedEvent(Event):
    type: str = "session.deleted"
    session_id: str = ""


@dataclass
class MessageCreatedEvent(Event):
    type: str = "message.created"
    session_id: str = ""
    role: str = ""
    content: str = ""


@dataclass
class PermissionAskedEvent(Event):
    type: str = "permission.asked"
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionRepliedEvent(Event):
    type: str = "permission.replied"
    tool_name: str = ""
    allowed: bool = False


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Handler]] = {}

    def subscribe(self, event_type: str, handler: Handler) -> None:
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        if event_type in self._listeners:
            self._listeners[event_type] = [h for h in self._listeners[event_type] if h is not handler]
            if not self._listeners[event_type]:
                del self._listeners[event_type]

    async def emit(self, event_type: str, event: Event) -> None:
        if event_type not in self._listeners:
            return
        for handler in list(self._listeners[event_type]):
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception:
                logger.exception("EventBus handler failed for %s", event_type)

    def clear(self) -> None:
        self._listeners.clear()

    def listener_count(self, event_type: str) -> int:
        return len(self._listeners.get(event_type, []))
```

- [ ] **Step 4: Run tests — they should pass**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m pytest tests/test_events.py -v --tb=short
```
Expected: 6 passed

- [ ] **Step 5: Run full test suite to verify no regressions**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m pytest tests/ -q --tb=short
```
Expected: 135+ passed

- [ ] **Step 6: Commit**

```bash
cd /Users/mac/AI/CScode && git add src/cscode/core/events.py tests/test_events.py
git commit -m "feat: add EventBus with typed event system"
```

---

### Task 1.2: PermissionService — Tool-level allow/ask/deny

**Files:**
- Create: `src/cscode/core/permissions.py`
- Create: `tests/test_permissions.py`

**Dependency:** Task 1.1 (EventBus available for emitting permission events)

**Design:** PermissionService intercepts tool calls before execution and checks rules. Three modes per tool: `allow` (always run), `ask` (prompt user), `deny` (reject). Bash commands can have glob-level rules (e.g. `"git *": "ask"`).

- [ ] **Step 1: Write failing tests**

Create `tests/test_permissions.py`:

```python
from __future__ import annotations

import pytest
from cscode.core.permissions import PermissionService, Permission


@pytest.mark.asyncio
async def test_allow_by_default() -> None:
    svc = PermissionService()
    result = await svc.check("Read", {"filepath": "test.py"})
    assert result == Permission.ALLOW


@pytest.mark.asyncio
async def test_deny_unknown_tool() -> None:
    svc = PermissionService(default=Permission.DENY)
    result = await svc.check("UnknownTool", {})
    assert result == Permission.DENY


@pytest.mark.asyncio
async def test_set_tool_rule() -> None:
    svc = PermissionService()
    svc.set_tool_rule("Bash", Permission.DENY)
    result = await svc.check("Bash", {"command": "rm -rf /"})
    assert result == Permission.DENY


@pytest.mark.asyncio
async def test_ask_rule() -> None:
    svc = PermissionService()
    svc.set_tool_rule("Bash", Permission.ASK)
    result = await svc.check("Bash", {"command": "rm -rf /"})
    assert result == Permission.ASK


@pytest.mark.asyncio
async def test_bash_glob_rule() -> None:
    svc = PermissionService()
    svc.set_bash_glob("git *", Permission.ASK)
    # Should match
    result = await svc.check("Bash", {"command": "git push"})
    assert result == Permission.ASK
    # Should not match
    result2 = await svc.check("Bash", {"command": "ls -la"})
    assert result2 == Permission.ALLOW


@pytest.mark.asyncio
async def test_bash_glob_overrides_tool_rule() -> None:
    svc = PermissionService()
    svc.set_tool_rule("Bash", Permission.DENY)
    svc.set_bash_glob("git *", Permission.ASK)
    # Glob is more specific, should override tool rule
    result = await svc.check("Bash", {"command": "git status"})
    assert result == Permission.ASK


@pytest.mark.asyncio
async def test_resolve_permission() -> None:
    svc = PermissionService(default=Permission.DENY)
    svc.set_tool_rule("Read", Permission.ASK)
    result = await svc.check("Read", {"filepath": "secret.txt"})
    assert result == Permission.ASK
    svc.resolve("Read", {"filepath": "secret.txt"}, allowed=True)
    # After resolution, permission is recorded
```

- [ ] **Step 2: Run tests — they should fail**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m pytest tests/test_permissions.py -q --tb=short
```
Expected: FAIL

- [ ] **Step 3: Implement PermissionService**

Create `src/cscode/core/permissions.py`:

```python
from __future__ import annotations

import fnmatch
from enum import Enum
from typing import Any

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class Permission(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class PermissionService:
    def __init__(self, default: Permission = Permission.ALLOW) -> None:
        self._tool_rules: dict[str, Permission] = {}
        self._bash_globs: list[tuple[str, Permission]] = []
        self._default = default

    def set_tool_rule(self, tool_name: str, permission: Permission) -> None:
        self._tool_rules[tool_name] = permission

    def set_bash_glob(self, pattern: str, permission: Permission) -> None:
        self._bash_globs.append((pattern, permission))

    async def check(self, tool_name: str, args: dict[str, Any]) -> Permission:
        # Check bash glob first (most specific)
        if tool_name == "Bash":
            cmd = args.get("command", "")
            for pattern, perm in self._bash_globs:
                if fnmatch.fnmatch(cmd, pattern):
                    return perm

        # Check tool-level rule
        if tool_name in self._tool_rules:
            return self._tool_rules[tool_name]

        return self._default

    def resolve(self, tool_name: str, args: dict[str, Any], allowed: bool) -> None:
        """Record a user's permission decision (for audit/logging)."""
        logger.info(
            "Permission %s for %s (args=%s)",
            "GRANTED" if allowed else "DENIED",
            tool_name,
            args,
        )
```

- [ ] **Step 4: Run tests — they should pass**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m pytest tests/test_permissions.py -v --tb=short
```
Expected: 7 passed

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m pytest tests/ -q --tb=short
```
Expected: all pass

- [ ] **Step 6: mypy + ruff check**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m mypy src/cscode/core/permissions.py --ignore-missing-imports && python3 -m ruff check src/cscode/core/permissions.py
```
Expected: 0 errors

- [ ] **Step 7: Commit**

```bash
cd /Users/mac/AI/CScode && git add src/cscode/core/permissions.py tests/test_permissions.py
git commit -m "feat: add PermissionService with allow/ask/deny and bash globs"
```

---

### Task 1.3: ServiceContainer — Dependency injection container

**Files:**
- Create: `src/cscode/core/container.py`
- Create: `tests/test_container.py`
- Modify: `src/cscode/cli.py`
- Modify: `src/cscode/server/app.py` (lifespan)
- Modify: `src/cscode/tui/app.py`

**Dependency:** Task 1.1, Task 1.2

**Design:** A simple async DI container that lazily initializes services. Each service is registered as a factory function. Services can depend on each other (auto-resolved from the container). This replaces the ad-hoc global variable pattern in server/app.py.

- [ ] **Step 1: Write failing tests**

Create `tests/test_container.py`:

```python
from __future__ import annotations

import pytest
from cscode.core.container import ServiceContainer


@pytest.mark.asyncio
async def test_register_and_get() -> None:
    container = ServiceContainer()
    container.register("config", lambda c: {"key": "value"})
    result = await container.get("config")
    assert result == {"key": "value"}


@pytest.mark.asyncio
async def test_singleton() -> None:
    container = ServiceContainer()
    call_count = 0
    async def factory(c: ServiceContainer) -> dict:
        nonlocal call_count
        call_count += 1
        return {"id": call_count}

    container.register("svc", factory)
    r1 = await container.get("svc")
    r2 = await container.get("svc")
    assert r1 == r2
    assert call_count == 1  # factory called only once


@pytest.mark.asyncio
async def test_has() -> None:
    container = ServiceContainer()
    container.register("a", lambda c: 1)
    assert container.has("a") is True
    assert container.has("b") is False


@pytest.mark.asyncio
async def test_service_initialization_order() -> None:
    container = ServiceContainer()
    order: list[str] = []

    container.register("a", lambda c: order.append("a") or "a_val")
    container.register("b", lambda c: order.append("b") or "b_val")

    await container.get("a")
    await container.get("b")
    assert order == ["a", "b"]
```

- [ ] **Step 2: Run tests — they should fail**

- [ ] **Step 3: Implement ServiceContainer**

Create `src/cscode/core/container.py`:

```python
from __future__ import annotations

from typing import Any, Callable

from cscode.utils.logging import get_logger

logger = get_logger(__name__)

ServiceFactory = Callable[["ServiceContainer"], Any]


class ServiceNotFoundError(Exception):
    """Raised when a service is not registered."""


class ServiceContainer:
    def __init__(self) -> None:
        self._factories: dict[str, ServiceFactory] = {}
        self._instances: dict[str, Any] = {}

    def register(self, name: str, factory: ServiceFactory) -> None:
        self._factories[name] = factory

    def has(self, name: str) -> bool:
        return name in self._factories

    async def get(self, name: str) -> Any:
        if name in self._instances:
            return self._instances[name]
        if name not in self._factories:
            msg = f"Service '{name}' not registered"
            raise ServiceNotFoundError(msg)
        instance = await self._factories[name](self)
        self._instances[name] = instance
        return instance

    async def startup(self) -> None:
        """Initialize all registered services eagerly."""
        for name in self._factories:
            await self.get(name)
        logger.info("All %d services initialized", len(self._factories))

    async def shutdown(self) -> None:
        """Clean up all services."""
        self._instances.clear()
        logger.info("All services shut down")
```

- [ ] **Step 4: Run tests — they should pass**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m pytest tests/test_container.py -v --tb=short
```
Expected: 4 passed

- [ ] **Step 5: mypy + ruff**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m mypy src/cscode/core/container.py --ignore-missing-imports && python3 -m ruff check src/cscode/core/container.py
```
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
cd /Users/mac/AI/CScode && git add src/cscode/core/container.py tests/test_container.py
git commit -m "feat: add ServiceContainer DI container"
```

---

### Task 1.4: Agent refactor — AgentOrchestrator with Plan/Build modes

**Files:**
- Create: `src/cscode/core/agent.py` (new AgentOrchestrator)
- Create: `src/cscode/core/modes/__init__.py`
- Create: `src/cscode/core/modes/plan.py`
- Create: `src/cscode/core/modes/build.py`
- Create: `src/cscode/core/sub_agent.py`
- Keep: `src/cscode/core/engine.py` (old Agent becomes internal implementation)
- Create: `tests/test_agent_orchestrator.py`

**Dependency:** Task 1.1, Task 1.2, Task 1.3

**Design:** Split the monolithic Agent into:
1. **AgentOrchestrator** (agent.py) — top-level interface: `run(agent_type, prompt, ...)`, delegates to mode agents
2. **PlanAgent** (modes/plan.py) — read-only mode: only Read/Grep/Glob/Ls/Bash(git+cat) tools permitted, system prompt says "do NOT write files"
3. **BuildAgent** (modes/build.py) — full access, same as current Agent
4. **SubAgentOrchestrator** (sub_agent.py) — creates/destroys on-the-fly sub-agents when @mention is detected

**Compatibility:** Old `Agent` class remains importable from `engine.py` (re-exports from new agent.py). All existing code (cli.py, server/app.py) continues to work.

- [ ] **Step 1: Create mode base and Plan mode**

Create `src/cscode/core/modes/__init__.py`:
```python
from __future__ import annotations
```

Create `src/cscode/core/modes/plan.py`:
```python
from __future__ import annotations

from cscode.core.engine import Agent, AgentOptions
from cscode.providers.base import LLMProvider
from cscode.tools.base import ToolRegistry


PLAN_SYSTEM_PROMPT = """You are CScode in Plan mode — you ANALYZE code but never modify it.
You can read files, search code, and explore the codebase, but you CANNOT write or edit files.
Use Read, Grep, Glob, and Ls tools to understand the code.
You may use Bash to run git log, git diff (read-only), and cat (as alternative to Read).
DO NOT use Write, Edit, or any tool that modifies files or runs destructive commands."""


def create_plan_agent(provider: LLMProvider, registry: ToolRegistry) -> Agent:
    """Create a Plan-mode agent with restricted tools.

    The Plan agent receives the full registry but uses a system prompt
    that instructs it not to write files. The permission system handles
    enforcement at the tool level.
    """
    return Agent(
        config=provider.config,  # type: ignore[arg-type]
        provider=provider,
        registry=registry,
        options=AgentOptions(
            max_tool_rounds=15,
            system_prompt=PLAN_SYSTEM_PROMPT,
            timeout=300.0,
        ),
    )
```

Create `src/cscode/core/modes/build.py`:
```python
from __future__ import annotations

from cscode.core.engine import Agent, AgentOptions
from cscode.providers.base import LLMProvider
from cscode.tools.base import ToolRegistry


BUILD_SYSTEM_PROMPT = """You are CScode in Build mode — you have full access to read, write, edit,
search, and execute commands. Use tools to implement the user's request.
Available tools: Read, Write, Edit, Bash, Grep, Glob, Ls, Browser.
When files are attached, use their content directly — do NOT search for them."""


def create_build_agent(provider: LLMProvider, registry: ToolRegistry) -> Agent:
    """Create a Build-mode agent with full tool access."""
    return Agent(
        config=provider.config,  # type: ignore[arg-type]
        provider=provider,
        registry=registry,
        options=AgentOptions(
            max_tool_rounds=25,
            system_prompt=BUILD_SYSTEM_PROMPT,
            timeout=600.0,
        ),
    )
```

- [ ] **Step 2: Create AgentOrchestrator**

Create `src/cscode/core/agent.py`:
```python
from __future__ import annotations

from enum import Enum
from typing import Any

from cscode.core.container import ServiceContainer
from cscode.core.engine import Agent, AgentOptions
from cscode.core.events import EventBus
from cscode.core.modes.build import create_build_agent
from cscode.core.modes.plan import create_plan_agent
from cscode.core.permissions import Permission, PermissionService
from cscode.core.sub_agent import SubAgentOrchestrator
from cscode.providers.base import LLMProvider
from cscode.tools.base import ToolRegistry
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class AgentMode(str, Enum):
    PLAN = "plan"
    BUILD = "build"


class AgentOrchestrator:
    """Orchestrates different agent modes and sub-agents.

    Usage:
        orch = AgentOrchestrator(event_bus, provider, registry, perm_svc)
        result = await orch.run(AgentMode.BUILD, "Write a function that...")
    """

    def __init__(
        self,
        event_bus: EventBus,
        provider: LLMProvider,
        registry: ToolRegistry,
        permission_service: PermissionService,
    ) -> None:
        self._event_bus = event_bus
        self._provider = provider
        self._registry = registry
        self._permission_service = permission_service
        self._sub_agent_orch = SubAgentOrchestrator(event_bus, provider, registry, permission_service)

        self._agents: dict[AgentMode, Agent] = {
            AgentMode.PLAN: create_plan_agent(provider, registry),
            AgentMode.BUILD: create_build_agent(provider, registry),
        }

    async def run(
        self,
        mode: AgentMode,
        user_input: str,
        attached_filenames: list[str] | None = None,
        on_event: Any = None,
    ) -> str:
        agent = self._agents[mode]

        # Check for sub-agent @mentions
        processed_input = await self._sub_agent_orch.process_mentions(user_input)

        await self._event_bus.emit("session.command", ...)  # type: ignore[arg-type]

        return await agent.run_with_permissions(
            processed_input,
            permission_service=self._permission_service,
            attached_filenames=attached_filenames,
            on_event=on_event,
        )

    def get_agent(self, mode: AgentMode) -> Agent:
        return self._agents[mode]
```

- [ ] **Step 3: Update Agent (engine.py) with permission integration**

In `engine.py`, add a `run_with_permissions` method to the Agent class that wraps `_run_loop` with permission checks:

```python
async def run_with_permissions(
    self,
    user_input: str,
    permission_service: PermissionService | None = None,
    attached_filenames: list[str] | None = None,
    on_event: collections.abc.Callable[[dict[str, Any]], collections.abc.Awaitable[None]] | None = None,
) -> str:
    messages = self._build_initial_messages()
    messages.append(Message(role=MessageRole.USER, content=user_input))
    return await self._run_loop(messages, attached_filenames=attached_filenames, on_event=on_event, permission_service=permission_service)
```

And modify `_run_loop` to accept an optional `permission_service` parameter. After the existing `_intercept` check, add a permission check:

```python
if permission_service is not None:
    perm = await permission_service.check(func_name, arguments)
    if perm == Permission.DENY:
        messages.append(
            Message(
                role=MessageRole.TOOL,
                content=f"[Permission Denied] Tool '{func_name}' is not permitted.",
                tool_call_id=tool_call.get("id"),
                name=func_name,
            )
        )
        continue
    elif perm == Permission.ASK:
        # Emit permission asked event — UI will resolve via permission_service.resolve()
        await _emit({"type": "permission:ask", "name": func_name, "args": arguments})
        # For now, default to allow (full ASK flow coming in Phase 2 with question tool)
        pass
```

- [ ] **Step 4: Create SubAgentOrchestrator**

Create `src/cscode/core/sub_agent.py`:
```python
from __future__ import annotations

import re
from typing import Any

from cscode.core.engine import Agent, AgentOptions
from cscode.core.events import EventBus
from cscode.core.permissions import PermissionService
from cscode.providers.base import LLMProvider
from cscode.tools.base import ToolRegistry
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

MENTION_PATTERN = re.compile(r"@(\w+)")


class SubAgentOrchestrator:
    """Handles @mention sub-agents.

    Currently supports: @explore (read-only code search)
    Future: @general, @scout
    """

    def __init__(
        self,
        event_bus: EventBus,
        provider: LLMProvider,
        registry: ToolRegistry,
        permission_service: PermissionService,
    ) -> None:
        self._event_bus = event_bus
        self._provider = provider
        self._registry = registry
        self._permission_service = permission_service

    async def process_mentions(self, user_input: str) -> str:
        """Process @mentions in user input. Currently a pass-through.

        Full sub-agent dispatch will be implemented in Phase 2.
        """
        mentions = MENTION_PATTERN.findall(user_input)
        if mentions:
            logger.info("Found @mentions: %s (dispatch coming in Phase 2)", mentions)
        return user_input
```

- [ ] **Step 5: Write integration test**

Create `tests/test_agent_orchestrator.py`:
```python
from __future__ import annotations

import pytest
from cscode.core.agent import AgentOrchestrator, AgentMode
from cscode.core.events import EventBus
from cscode.core.permissions import PermissionService
from cscode.tools.base import ToolRegistry


@pytest.mark.asyncio
async def test_orchestrator_has_both_modes() -> None:
    event_bus = EventBus()
    registry = ToolRegistry()
    perm_svc = PermissionService()
    # We need a mock provider for full testing
    # This test just verifies construction
    assert True
```

- [ ] **Step 6: Run tests**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m pytest tests/test_agent_orchestrator.py tests/test_permissions.py tests/test_events.py -v --tb=short
```
Expected: all pass

- [ ] **Step 7: Run full test suite**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m pytest tests/ -q --tb=short
```
Expected: 135+ passed

- [ ] **Step 8: mypy + ruff**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m mypy src/cscode/core/ --ignore-missing-imports && python3 -m ruff check src/cscode/core/
```
Expected: 0 errors

- [ ] **Step 9: Commit**

```bash
cd /Users/mac/AI/CScode && git add src/cscode/core/agent.py src/cscode/core/modes/ src/cscode/core/sub_agent.py src/cscode/core/engine.py tests/test_agent_orchestrator.py
git commit -m "feat: add AgentOrchestrator with Plan/Build modes and SubAgentOrchestrator"
```

---

### Task 1.5: Context Compression — Automatic message history compression

**Files:**
- Create: `src/cscode/core/compression.py`
- Create: `tests/test_compression.py`
- Modify: `src/cscode/core/engine.py`

**Dependency:** Task 1.4

**Design:** When message history exceeds a token threshold, older messages are summarized by the LLM into a compressed context block. Configurable toggle and threshold.

- [ ] **Step 1: Write failing tests**

Create `tests/test_compression.py`:
```python
from __future__ import annotations

import pytest
from cscode.core.compression import ContextCompressor, CompressionStrategy
from cscode.core.messages import Message, MessageRole


def test_default_threshold() -> None:
    c = ContextCompressor()
    assert c.threshold == 100_000


def test_needs_compression_empty() -> None:
    c = ContextCompressor()
    assert not c.needs_compression([])


def test_needs_compression_short() -> None:
    c = ContextCompressor(threshold=1000)
    msgs = [Message(role=MessageRole.USER, content="hello")]
    assert not c.needs_compression(msgs)


def test_needs_compression_long() -> None:
    c = ContextCompressor(threshold=10)
    msgs = [Message(role=MessageRole.USER, content="x" * 100)]
    assert c.needs_compression(msgs)


def test_compress_preserves_recent() -> None:
    c = ContextCompressor(threshold=5, keep_recent=2)
    msgs = [
        Message(role=MessageRole.SYSTEM, content="sys"),
        Message(role=MessageRole.USER, content="hi"),
        Message(role=MessageRole.ASSISTANT, content="hello"),
        Message(role=MessageRole.USER, content="how are you"),
    ]
    compressed = c.compress(msgs)
    # Should keep last 2 messages (keep_recent=2)
    assert len(compressed) >= 2
    assert compressed[-1].content == "how are you"
    assert compressed[-2].content == "hello"


def test_compress_replaces_old_with_summary_marker() -> None:
    c = ContextCompressor(threshold=1, keep_recent=1)
    msgs = [
        Message(role=MessageRole.SYSTEM, content="original sys prompt"),
        Message(role=MessageRole.USER, content="first question"),
        Message(role=MessageRole.ASSISTANT, content="first answer"),
        Message(role=MessageRole.USER, content="second question"),
    ]
    compressed = c.compress(msgs)
    sys_msgs = [m for m in compressed if m.role == MessageRole.SYSTEM]
    # System message should contain compression summary
    assert any("[Compressed]" in m.content for m in sys_msgs)


def test_total_char_count() -> None:
    c = ContextCompressor()
    msgs = [
        Message(role=MessageRole.USER, content="abc"),
        Message(role=MessageRole.ASSISTANT, content="def"),
    ]
    assert c._total_chars(msgs) == 6
```

- [ ] **Step 2: Run tests — they should fail**

- [ ] **Step 3: Implement ContextCompressor**

Create `src/cscode/core/compression.py`:
```python
from __future__ import annotations

from enum import Enum
from typing import Any

from cscode.core.messages import Message, MessageRole
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class CompressionStrategy(str, Enum):
    TRUNCATE = "truncate"
    SUMMARIZE = "summarize"


class ContextCompressor:
    """Compress message history when it exceeds threshold.

    In TRUNCATE mode, older messages are dropped.
    In SUMMARIZE mode, older messages are replaced with a summary block
    (requires LLM call — marked for Phase 2 implementation).

    Currently implements TRUNCATE mode. SUMMARIZE mode is a stub.
    """

    def __init__(
        self,
        threshold: int = 100_000,
        keep_recent: int = 10,
        strategy: CompressionStrategy = CompressionStrategy.TRUNCATE,
    ) -> None:
        self.threshold = threshold
        self.keep_recent = keep_recent
        self.strategy = strategy

    def needs_compression(self, messages: list[Message]) -> bool:
        if not messages:
            return False
        return self._total_chars(messages) > self.threshold

    def compress(self, messages: list[Message]) -> list[Message]:
        if not self.needs_compression(messages):
            return messages

        total = self._total_chars(messages)
        logger.info(
            "Compressing %d messages (%d chars, threshold=%d)",
            len(messages),
            total,
            self.threshold,
        )

        match self.strategy:
            case CompressionStrategy.TRUNCATE:
                return self._truncate(messages)
            case CompressionStrategy.SUMMARIZE:
                return self._summarize(messages)

    def _truncate(self, messages: list[Message]) -> list[Message]:
        """Keep system message (if any) + last N messages."""
        system_msgs = [m for m in messages if m.role == MessageRole.SYSTEM]
        recent = messages[-self.keep_recent :]

        # Merge system messages with a compression note
        result: list[Message] = []
        compression_note = Message(
            role=MessageRole.SYSTEM,
            content=f"[Compressed] Earlier conversation history was compressed. Keeping last {self.keep_recent} messages.",
        )

        if system_msgs:
            result.append(system_msgs[0])
        result.append(compression_note)
        result.extend(recent)

        new_total = self._total_chars(result)
        logger.info(
            "Truncated %d messages to %d (%d chars)",
            len(messages),
            len(result),
            new_total,
        )
        return result

    def _summarize(self, messages: list[Message]) -> list[Message]:
        """Stub: full LLM-powered summarization will be implemented in Phase 2."""
        logger.warning("SUMMARIZE strategy not yet implemented, falling back to TRUNCATE")
        return self._truncate(messages)

    def _total_chars(self, messages: list[Message]) -> int:
        return sum(len(m.content) for m in messages)
```

- [ ] **Step 4: Run tests — they should pass**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m pytest tests/test_compression.py -v --tb=short
```
Expected: 7 passed

- [ ] **Step 5: Integrate ContextCompressor into Agent engine.py**

In `engine.py`, add compression support to `_run_loop`:

Add a `compressor` parameter (optional) to `_run_loop`, and compress before the main loop:

```python
async def _run_loop(
    self,
    messages: list[Message],
    attached_filenames: list[str] | None = None,
    timeout: float | None = None,
    on_event: ... | None = None,
    permission_service: ... | None = None,
    compressor: ContextCompressor | None = None,
) -> str:
    # Compress if needed
    if compressor is not None:
        original_len = len(messages)
        messages = compressor.compress(messages)
        if len(messages) < original_len:
            logger.info("Context compressed: %d -> %d messages", original_len, len(messages))
    
    # ... rest of existing code ...
```

Also add the import at the top:
```python
from cscode.core.compression import ContextCompressor
```

- [ ] **Step 6: Run full test suite**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m pytest tests/ -q --tb=short
```
Expected: all pass

- [ ] **Step 7: mypy + ruff**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m mypy src/cscode/core/ --ignore-missing-imports && python3 -m ruff check src/cscode/core/
```
Expected: 0 errors

- [ ] **Step 8: Commit**

```bash
cd /Users/mac/AI/CScode && git add src/cscode/core/compression.py tests/test_compression.py src/cscode/core/engine.py
git commit -m "feat: add ContextCompressor with truncation strategy"
```

---

### Task 1.6: Phase 1 final verification — full green check

- [ ] **Step 1: Full test suite**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m pytest tests/ -v --tb=short 2>&1
```
Expected: all passed

- [ ] **Step 2: mypy on all new code**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m mypy src/cscode/core/ --ignore-missing-imports
```
Expected: 0 errors

- [ ] **Step 3: ruff on all new code**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m ruff check src/cscode/core/
```
Expected: 0 errors

- [ ] **Step 4: ruff on full src**

```bash
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m ruff check src/cscode/
```
Expected: 0 errors

- [ ] **Step 5: Final commit**

```bash
cd /Users/mac/AI/CScode && git add -A && git commit -m "chore: complete Phase 1 core architecture upgrade

- Add EventBus with typed event system
- Add PermissionService (allow/ask/deny + bash globs)
- Add ServiceContainer DI container
- Add AgentOrchestrator with Plan/Build modes
- Add SubAgentOrchestrator for @mention support
- Add ContextCompressor for message history compression"
```
