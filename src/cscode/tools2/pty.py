"""PTY Tool — persistent interactive shell sessions via pseudoterminal.

Provides a stateful PTY session manager and Tool wrapper for interactive
shell sessions that persist across multiple LLM tool calls.

Usage:
    tool = PTYTool()
    result = await tool.execute(PTYInput(action=PTYAction.CREATE))
    session_id = result.data.session_id
    result = await tool.execute(
        PTYInput(action=PTYAction.EXEC, session_id=sid, command="pwd")
    )
"""

from __future__ import annotations

import asyncio
import os
import platform
import secrets
import signal
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

_CMD_DONE = "__PTY_DONE__"
_PROMPT_MARKER = "__PTY_READY__"

# ── Platform guard ─────────────────────────────────────────────────
_UNIX = platform.system() in ("Darwin", "Linux", "FreeBSD")


# ═══════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════


class PTYAction(StrEnum):
    CREATE = "create"
    EXEC = "exec"
    READ = "read"
    CLOSE = "close"
    LIST = "list"


class PTYInput(BaseModel):
    action: PTYAction
    session_id: str | None = None
    shell: str = "/bin/bash"
    cwd: str | None = None
    command: str | None = None
    timeout: int = 30_000
    env: dict[str, str] | None = None


class PTYCreateOutput(BaseModel):
    session_id: str
    shell: str
    cwd: str
    created_at: float


class PTYWriteOutput(BaseModel):
    output: str
    exit_code: int


class PTYReadOutput(BaseModel):
    output: str
    buffer_size: int


class PTYCloseOutput(BaseModel):
    session_id: str
    closed: bool


class PTYListOutput(BaseModel):
    sessions: list[PTYCreateOutput]


# Use PTYWriteOutput for all exec/read returns
PTYOutput = PTYCreateOutput | PTYWriteOutput | PTYReadOutput | PTYCloseOutput | PTYListOutput


# ═══════════════════════════════════════════════════════════════════
# Session management
# ═══════════════════════════════════════════════════════════════════


@dataclass
class PTYSession:
    """A persistent PTY shell session."""
    session_id: str
    shell: str
    master_fd: int
    proc: asyncio.subprocess.Process
    cwd: str
    env: dict[str, str]
    created_at: float
    last_active: float
    _buffer: bytearray = field(default_factory=bytearray)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _closed: bool = False


class PTYSessionManager:
    """Manages all active PTY sessions.

    Provides create/exec/read/close/list operations on shell sessions
    running under pseudoterminals.
    """

    def __init__(
        self,
        max_sessions: int = 10,
        session_timeout: int = 600,  # 10 min
    ) -> None:
        self._sessions: dict[str, PTYSession] = {}
        self._max_sessions = max_sessions
        self._session_timeout = session_timeout

    # ── Public API ────────────────────────────────────────────────

    async def create(
        self,
        shell: str = "/bin/bash",
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> PTYSession:
        """Create a new PTY session.

        Args:
            shell: Path to shell binary (e.g. /bin/bash).
            cwd: Working directory (defaults to current).
            env: Additional environment variables.

        Returns:
            A new PTYSession instance.

        Raises:
            RuntimeError: If max sessions reached or PTY allocation fails.
        """
        if len(self._sessions) >= self._max_sessions:
            msg = f"Max sessions ({self._max_sessions}) reached"
            raise RuntimeError(msg)

        if not _UNIX:
            msg = "PTY is not supported on this platform"
            raise RuntimeError(msg)

        # Allocate PTY
        try:
            master_fd, slave_fd = os.openpty()
        except OSError as e:
            msg = f"Failed to allocate PTY: {e}"
            raise RuntimeError(msg) from e

        # Configure slave
        os.set_blocking(master_fd, False)

        # Build env
        proc_env = dict(os.environ)
        if env:
            proc_env.update(env)
        proc_env.pop("PS1", None)

        # Resolve cwd
        workdir = cwd or os.getcwd()

        # Start shell process
        try:
            proc = await asyncio.create_subprocess_exec(
                shell,
                "-i",  # interactive mode
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=workdir,
                env=proc_env,
                preexec_fn=_prepty,  # setsid + termios
            )
        except FileNotFoundError as e:
            os.close(master_fd)
            os.close(slave_fd)
            msg = f"Shell not found: {shell}"
            raise RuntimeError(msg) from e

        # Close slave in parent (child has the only reference)
        os.close(slave_fd)

        # Generate session id
        session_id = secrets.token_hex(12)

        session = PTYSession(
            session_id=session_id,
            shell=shell,
            master_fd=master_fd,
            proc=proc,
            cwd=workdir,
            env=env or {},
            created_at=time.time(),
            last_active=time.time(),
        )

        self._sessions[session_id] = session
        logger.debug("PTY session created: id=%s shell=%s", session_id, shell)
        return session

    async def exec(
        self,
        session_id: str,
        command: str,
        timeout: int = 30_000,
    ) -> PTYExecResult:
        """Execute a command in a PTY session.

        Writes the command to the PTY, then reads the output until
        a completion marker is found or timeout.

        Args:
            session_id: Target session ID.
            command: Shell command to execute.
            timeout: Timeout in milliseconds.

        Returns:
            PTYExecResult with output text and exit code.

        Raises:
            KeyError: If session_id not found.
            TimeoutError: If command times out.
        """
        session = self._sessions.get(session_id)
        if session is None:
            msg = f"Session not found: {session_id}"
            raise KeyError(msg)

        if session._closed:
            msg = f"Session is closed: {session_id}"
            raise KeyError(msg)

        async with session._lock:
            session.last_active = time.time()
            timeout_s = timeout / 1000

            # Write command wrapped with marker echo for output detection
            marker_cmd = f"{command}\necho {_CMD_DONE}:$?\n"
            data = marker_cmd.encode("utf-8", errors="replace")

            try:
                await asyncio.wait_for(
                    asyncio.to_thread(os.write, session.master_fd, data),
                    timeout=timeout_s,
                )
            except asyncio.TimeoutError:
                msg = f"Command timed out after {timeout_s}s"
                raise TimeoutError(msg) from None
            except OSError as e:
                msg = f"PTY write failed: {e}"
                raise RuntimeError(msg) from e

            # Read until marker (search for marker on its own line)
            # We search for \nMARKER or \r\nMARKER to avoid matching
            # the shell's echo of the "echo __PTY_DONE__:$?" command line.
            marker_line = f"\n{_CMD_DONE}:".encode("utf-8")
            marker_line_cr = f"\r\n{_CMD_DONE}:".encode("utf-8")
            deadline = time.time() + timeout_s
            output_bytes = bytearray()
            backoff = 0.02  # 20ms initial backoff
            found_marker = False

            while time.time() < deadline:
                try:
                    chunk = os.read(session.master_fd, 4096)
                    if not chunk:
                        break  # EOF
                    output_bytes.extend(chunk)
                    backoff = 0.02  # reset on success
                    # Check for marker on its own line
                    if marker_line_cr in output_bytes or marker_line in output_bytes:
                        found_marker = True
                        break
                except BlockingIOError:
                    # No data yet — wait briefly then retry
                    await asyncio.sleep(min(backoff, 0.5))
                    backoff = min(backoff * 1.5, 0.2)
                    continue
                except OSError:
                    break

            if not found_marker:
                msg = f"Command timed out after {timeout_s}s"
                raise TimeoutError(msg)

            # Parse output
            output_text = output_bytes.decode("utf-8", errors="replace")

            # Strip ANSI escape sequences for cleaner output
            import re
            output_text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", output_text)
            output_text = re.sub(r"\x1b\][0-9;]*[^\x1b]*(\x1b\\)?", "", output_text)
            # Strip carriage returns
            output_text = output_text.replace("\r\n", "\n").replace("\r", "\n")

            # Extract exit code from marker line
            exit_code = 0
            lines = output_text.split("\n")
            cleaned_lines = []
            for line in lines:
                if f"{_CMD_DONE}:" in line:
                    try:
                        exit_str = line.split(f"{_CMD_DONE}:")[-1].strip()
                        exit_code = int(exit_str)
                    except ValueError:
                        exit_code = -1
                    continue
                # Skip empty shell prompt lines (bare $ or %)
                if line.strip() in ("$", "%", "#", "bash-"):
                    continue
                cleaned_lines.append(line)

            # Remove leading empty lines and the first echoed command line
            output_text = "\n".join(cleaned_lines).strip()

            return PTYExecResult(output=output_text, exit_code=exit_code)

    async def read(self, session_id: str) -> str:
        """Read any pending output from a session without sending input.

        Args:
            session_id: Target session ID.

        Returns:
            Pending output text.
        """
        session = self._sessions.get(session_id)
        if session is None:
            msg = f"Session not found: {session_id}"
            raise KeyError(msg)

        output_bytes = bytearray()
        try:
            while True:
                chunk = await asyncio.wait_for(
                    asyncio.to_thread(os.read, session.master_fd, 4096),
                    timeout=0.2,
                )
                if not chunk:
                    break
                output_bytes.extend(chunk)
        except (asyncio.TimeoutError, TimeoutError, OSError):
            pass

        output_text = output_bytes.decode("utf-8", errors="replace")

        # Clean ANSI escapes
        import re
        output_text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", output_text)
        output_text = output_text.replace("\r\n", "\n").replace("\r", "\n")

        return output_text.strip()

    async def close(self, session_id: str) -> bool:
        """Close and clean up a PTY session.

        Args:
            session_id: Session to close.

        Returns:
            True if session was closed, False if not found.
        """
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False

        session._closed = True

        # Send exit to shell
        try:
            os.write(session.master_fd, b"exit\n")
            await asyncio.sleep(0.1)
        except OSError:
            pass

        # Terminate process
        try:
            session.proc.terminate()
            try:
                await asyncio.wait_for(session.proc.wait(), timeout=2.0)
            except (asyncio.TimeoutError, TimeoutError):
                session.proc.kill()
                await session.proc.wait()
        except ProcessLookupError:
            pass

        # Close PTY fd
        try:
            os.close(session.master_fd)
        except OSError:
            pass

        logger.debug("PTY session closed: id=%s", session_id)
        return True

    def list_sessions(self) -> list[PTYSession]:
        """Return all active sessions."""
        return list(self._sessions.values())

    async def _cleanup_stale(self) -> None:
        """Close sessions that have exceeded the timeout."""
        now = time.time()
        stale = [
            sid
            for sid, session in self._sessions.items()
            if now - session.last_active > self._session_timeout
        ]
        for sid in stale:
            logger.debug("Cleaning up stale PTY session: id=%s", sid)
            await self.close(sid)

    async def shutdown(self) -> None:
        """Close all sessions."""
        sids = list(self._sessions.keys())
        for sid in sids:
            await self.close(sid)


@dataclass
class PTYExecResult:
    """Result of a PTY exec operation."""
    output: str
    exit_code: int


def _prepty() -> None:
    """Preexec function for PTY child process.

    Creates a new session and configures the terminal.
    """
    # Create new session (process group leader)
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError):
        pass


# ═══════════════════════════════════════════════════════════════════
# Tool
# ═══════════════════════════════════════════════════════════════════


class PTYTool(Tool[PTYInput, Any]):
    """Tool for managing persistent PTY shell sessions.

    Supports create/exec/read/close/list actions for interactive
    shell sessions that maintain state across calls.
    """

    name = "pty"
    description = "Manage persistent shell sessions via PTY. Use action=create to start a session, action=exec to run commands, action=read to get pending output, action=close to end a session, action=list to see all sessions. Sessions preserve state (cwd, env) across exec calls."
    input_schema = PTYInput
    output_schema = PTYOutput  # type: ignore[assignment]

    def __init__(self, manager: PTYSessionManager | None = None) -> None:
        super().__init__()
        self._manager = manager or PTYSessionManager()

    async def execute(self, input: PTYInput) -> ToolResult[Any]:
        """Execute a PTY action."""
        try:
            match input.action:
                case PTYAction.CREATE:
                    return await self._handle_create(input)
                case PTYAction.EXEC:
                    return await self._handle_exec(input)
                case PTYAction.READ:
                    return await self._handle_read(input)
                case PTYAction.CLOSE:
                    return await self._handle_close(input)
                case PTYAction.LIST:
                    return await self._handle_list()
        except (KeyError, RuntimeError, TimeoutError, OSError) as e:
            return ToolResult(
                success=False,
                error=str(e),
            )

    async def _handle_create(self, input: PTYInput) -> ToolResult[PTYCreateOutput]:
        session = await self._manager.create(
            shell=input.shell or "/bin/bash",
            cwd=input.cwd,
            env=input.env,
        )
        return ToolResult(
            success=True,
            data=PTYCreateOutput(
                session_id=session.session_id,
                shell=session.shell,
                cwd=session.cwd,
                created_at=session.created_at,
            ),
        )

    async def _handle_exec(self, input: PTYInput) -> ToolResult[PTYWriteOutput]:
        if not input.session_id:
            return ToolResult(success=False, error="session_id is required for exec")
        if not input.command:
            return ToolResult(success=False, error="command is required for exec")

        result = await self._manager.exec(
            session_id=input.session_id,
            command=input.command,
            timeout=input.timeout or 30_000,
        )
        return ToolResult(
            success=result.exit_code == 0,
            data=PTYWriteOutput(
                output=result.output,
                exit_code=result.exit_code,
            ),
        )

    async def _handle_read(self, input: PTYInput) -> ToolResult[PTYReadOutput]:
        if not input.session_id:
            return ToolResult(success=False, error="session_id is required for read")

        output = await self._manager.read(input.session_id)
        return ToolResult(
            success=True,
            data=PTYReadOutput(output=output, buffer_size=len(output)),
        )

    async def _handle_close(self, input: PTYInput) -> ToolResult[PTYCloseOutput]:
        if not input.session_id:
            return ToolResult(success=False, error="session_id is required for close")

        closed = await self._manager.close(input.session_id)
        return ToolResult(
            success=True,
            data=PTYCloseOutput(
                session_id=input.session_id,
                closed=closed,
            ),
        )

    async def _handle_list(self) -> ToolResult[PTYListOutput]:
        sessions = self._manager.list_sessions()
        return ToolResult(
            success=True,
            data=PTYListOutput(
                sessions=[
                    PTYCreateOutput(
                        session_id=s.session_id,
                        shell=s.shell,
                        cwd=s.cwd,
                        created_at=s.created_at,
                    )
                    for s in sessions
                ],
            ),
        )
