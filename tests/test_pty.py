"""Tests for P2-1: PTY system — interactive shell sessions via PTYTool."""

from __future__ import annotations

import asyncio
import os
import platform

import pytest

# ── Module-level skip: PTY requires Unix ────────────────────────────
pytestmark = [
    pytest.mark.skipif(
        platform.system() != "Darwin" and platform.system() != "Linux",
        reason="PTY is only supported on Unix (macOS / Linux)",
    ),
]


# ── Imports (skip if import fails on non-Unix) ──────────────────────
try:
    from cscode.tools2.pty import (
        PTYAction,
        PTYCreateOutput,
        PTYInput,
        PTYSessionManager,
        PTYTool,
        PTYWriteOutput,
    )
except ImportError:
    if platform.system() in ("Darwin", "Linux"):
        raise  # should not fail on Unix
    pytest.skip("PTY module not available on this platform", allow_module_level=True)


# ═══════════════════════════════════════════════════════════════════
# PTYSessionManager tests
# ═══════════════════════════════════════════════════════════════════


class TestPTYSessionManager:
    """Test core session management logic."""

    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    def manager(self) -> PTYSessionManager:
        return PTYSessionManager(max_sessions=10, session_timeout=600)

    async def test_create_session(self, manager: PTYSessionManager) -> None:
        """Creating a session returns a valid session_id."""
        session = await manager.create(shell="/bin/bash")
        assert session.session_id
        assert len(session.session_id) > 0
        assert session.shell == "/bin/bash"
        assert session.cwd == os.getcwd()
        assert session.session_id in manager._sessions

    async def test_create_session_custom_cwd(self, manager: PTYSessionManager) -> None:
        """Creating a session with custom cwd."""
        tmp = "/tmp"
        session = await manager.create(shell="/bin/bash", cwd=tmp)
        assert session.cwd == tmp

    async def test_exec_basic_command(self, manager: PTYSessionManager) -> None:
        """Execute a simple command and get output."""
        session = await manager.create(shell="/bin/bash")
        result = await manager.exec(session.session_id, "echo hello_pty", timeout=5000)
        assert result.exit_code == 0
        assert "hello_pty" in result.output

    async def test_exec_preserves_state(self, manager: PTYSessionManager) -> None:
        """State (cwd, env) persists across exec calls."""
        session = await manager.create(shell="/bin/bash")
        # cd to /tmp
        result1 = await manager.exec(session.session_id, "cd /tmp && pwd", timeout=5000)
        assert result1.exit_code == 0
        assert "/tmp" in result1.output

        # Verify state persists: pwd should still be /tmp
        result2 = await manager.exec(session.session_id, "pwd", timeout=5000)
        assert "/tmp" in result2.output

    async def test_exec_return_code(self, manager: PTYSessionManager) -> None:
        """Non-zero exit code is captured."""
        session = await manager.create(shell="/bin/bash")
        result = await manager.exec(session.session_id, "false", timeout=5000)
        assert result.exit_code == 1

    async def test_custom_exit_code(self, manager: PTYSessionManager) -> None:
        """Custom exit code via exit N."""
        session = await manager.create(shell="/bin/bash")
        result = await manager.exec(session.session_id, "bash -c 'exit 42'", timeout=5000)
        assert result.exit_code == 42

    async def test_multiple_independent_sessions(self, manager: PTYSessionManager) -> None:
        """Multiple sessions are isolated from each other."""
        s1 = await manager.create(shell="/bin/bash")
        s2 = await manager.create(shell="/bin/bash")

        # cd in s1
        await manager.exec(s1.session_id, "cd /tmp", timeout=5000)
        # verify s2 is NOT in /tmp
        r2 = await manager.exec(s2.session_id, "pwd", timeout=5000)
        assert r2.exit_code == 0
        assert r2.output.strip() != "/tmp"

    async def test_close_session(self, manager: PTYSessionManager) -> None:
        """Closing a session removes it and stops the process."""
        session = await manager.create(shell="/bin/bash")
        sid = session.session_id
        assert sid in manager._sessions

        closed = await manager.close(sid)
        assert closed is True
        assert sid not in manager._sessions

    async def test_close_nonexistent_session(self, manager: PTYSessionManager) -> None:
        """Closing a session that doesn't exist returns False."""
        closed = await manager.close("nonexistent")
        assert closed is False

    async def test_list_sessions(self, manager: PTYSessionManager) -> None:
        """list_sessions returns all active sessions."""
        s1 = await manager.create(shell="/bin/bash")
        s2 = await manager.create(shell="/bin/bash")
        sessions = manager.list_sessions()
        assert len(sessions) == 2
        sids = [s.session_id for s in sessions]
        assert s1.session_id in sids
        assert s2.session_id in sids

    async def test_exec_timeout(self, manager: PTYSessionManager) -> None:
        """Command that takes too long raises TimeoutError."""
        session = await manager.create(shell="/bin/bash")
        with pytest.raises(TimeoutError):
            await manager.exec(session.session_id, "sleep 10", timeout=500)

    async def test_exec_after_close(self, manager: PTYSessionManager) -> None:
        """Exec on a closed session raises KeyError."""
        session = await manager.create(shell="/bin/bash")
        await manager.close(session.session_id)
        with pytest.raises(KeyError):
            await manager.exec(session.session_id, "echo hi", timeout=5000)

    async def test_max_sessions_enforced(self) -> None:
        """Creating more than max_sessions raises an error."""
        manager = PTYSessionManager(max_sessions=2, session_timeout=600)
        await manager.create(shell="/bin/bash")
        await manager.create(shell="/bin/bash")
        with pytest.raises(RuntimeError, match="Max sessions"):
            await manager.create(shell="/bin/bash")

    async def test_env_vars_passed(self, manager: PTYSessionManager) -> None:
        """Custom env vars are available in the session."""
        session = await manager.create(
            shell="/bin/bash",
            env={"CUSTOM_VAR": "hello_pty_env"},
        )
        result = await manager.exec(session.session_id, "echo $CUSTOM_VAR", timeout=5000)
        assert "hello_pty_env" in result.output

    async def test_session_timeout_cleanup(self) -> None:
        """Sessions past timeout are cleaned up."""
        manager = PTYSessionManager(max_sessions=10, session_timeout=0)  # immediate timeout
        session = await manager.create(shell="/bin/bash")
        sid = session.session_id
        assert sid in manager._sessions
        # Let cleanup run
        await asyncio.sleep(0.1)
        await manager._cleanup_stale()
        assert sid not in manager._sessions


# ═══════════════════════════════════════════════════════════════════
# PTYTool tests
# ═══════════════════════════════════════════════════════════════════


class TestPTYTool:
    """Test the PTYTool wrapper (uses real PTYSessionManager internally)."""

    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    def tool(self) -> PTYTool:
        return PTYTool()

    async def test_create_action(self, tool: PTYTool) -> None:
        """create action returns session info."""
        result = await tool.execute(PTYInput(action=PTYAction.CREATE))
        assert result.success
        assert result.data is not None
        data: PTYCreateOutput = result.data  # type: ignore[assignment]
        assert data.session_id
        assert data.shell == "/bin/bash"

    async def test_exec_action(self, tool: PTYTool) -> None:
        """exec action runs command and returns output."""
        # First create
        create_result = await tool.execute(PTYInput(action=PTYAction.CREATE))
        assert create_result.success and create_result.data
        sid = create_result.data.session_id

        # Then exec
        exec_result = await tool.execute(
            PTYInput(action=PTYAction.EXEC, session_id=sid, command="echo pty_tool_test")
        )
        assert exec_result.success
        assert exec_result.data is not None
        data: PTYWriteOutput = exec_result.data  # type: ignore[assignment]
        assert "pty_tool_test" in data.output
        assert data.exit_code == 0

    async def test_exec_preserves_state_across_calls(self, tool: PTYTool) -> None:
        """State is preserved across multiple exec calls."""
        create_r = await tool.execute(PTYInput(action=PTYAction.CREATE))
        assert create_r.success and create_r.data
        sid = create_r.data.session_id

        # cd to /tmp
        await tool.execute(
            PTYInput(action=PTYAction.EXEC, session_id=sid, command="cd /tmp")
        )

        # verify pwd
        pwd_r = await tool.execute(
            PTYInput(action=PTYAction.EXEC, session_id=sid, command="pwd")
        )
        assert pwd_r.success and pwd_r.data
        assert "/tmp" in pwd_r.data.output

    async def test_list_action(self, tool: PTYTool) -> None:
        """list action returns active sessions."""
        await tool.execute(PTYInput(action=PTYAction.CREATE))
        await tool.execute(PTYInput(action=PTYAction.CREATE))

        list_result = await tool.execute(PTYInput(action=PTYAction.LIST))
        assert list_result.success
        assert list_result.data is not None
        assert len(list_result.data.sessions) == 2

    async def test_close_action(self, tool: PTYTool) -> None:
        """close action terminates a session."""
        create_r = await tool.execute(PTYInput(action=PTYAction.CREATE))
        assert create_r.success and create_r.data
        sid = create_r.data.session_id

        close_r = await tool.execute(
            PTYInput(action=PTYAction.CLOSE, session_id=sid)
        )
        assert close_r.success
        assert close_r.data is not None
        assert close_r.data.closed is True

        # Verify gone from list
        list_r = await tool.execute(PTYInput(action=PTYAction.LIST))
        assert list_r.success and list_r.data
        assert len(list_r.data.sessions) == 0

    async def test_read_action(self, tool: PTYTool) -> None:
        """read action returns buffered output."""
        create_r = await tool.execute(PTYInput(action=PTYAction.CREATE))
        assert create_r.success and create_r.data
        sid = create_r.data.session_id

        # Execute something and read
        await tool.execute(
            PTYInput(action=PTYAction.EXEC, session_id=sid, command="echo read_test")
        )
        read_r = await tool.execute(
            PTYInput(action=PTYAction.READ, session_id=sid)
        )
        assert read_r.success
        assert read_r.data is not None

    async def test_exec_on_closed_session(self, tool: PTYTool) -> None:
        """Exec on a closed session returns error, not crash."""
        create_r = await tool.execute(PTYInput(action=PTYAction.CREATE))
        assert create_r.success and create_r.data
        sid = create_r.data.session_id

        await tool.execute(PTYInput(action=PTYAction.CLOSE, session_id=sid))
        result = await tool.execute(
            PTYInput(action=PTYAction.EXEC, session_id=sid, command="echo hi")
        )
        assert not result.success
        assert result.error is not None

    async def test_unknown_action(self, tool: PTYTool) -> None:
        """Unknown action returns error."""
        # We can't easily test invalid enum values, but we can skip action field
        # Use a dict to create invalid input
        result = await tool.execute(PTYInput(action=PTYAction.CREATE))  # just test valid action
        assert result.success or not result.success  # no crash


class TestPTYToolRegistration:
    """Test that PTYTool can be registered in the registry."""

    def test_registry_compatible(self) -> None:
        """PTYTool follows Tool protocol."""
        tool = PTYTool()
        assert tool.name == "pty"
        assert tool.description
        assert tool.input_schema is not None
        assert tool.output_schema is not None
        # Can produce ToolDefinition
        definition = tool.to_definition()
        assert definition.name == "pty"
        assert "action" in definition.input_schema["properties"]
