"""BashTool v2 — execute shell commands with typed output."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult


class BashInput(BaseModel):
    command: str
    timeout: int = 30_000
    task_id: str = ""


class BashOutput(BaseModel):
    output: str
    exit_code: int


class BashTool(Tool[BashInput, BashOutput]):
    name = "bash"
    description = "Execute a shell command and return the output"
    input_schema = BashInput
    output_schema = BashOutput

    async def execute(self, input: BashInput) -> ToolResult[BashOutput]:
        timeout_s = input.timeout / 1000

        try:
            proc = await asyncio.create_subprocess_shell(
                input.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            except asyncio.TimeoutError:
                proc.kill()
                ts = datetime.now(timezone.utc).isoformat()
                evidence_str = json.dumps({"content_length": 0, "exit_code": -1, "timestamp": ts})
                return ToolResult(
                    success=False,
                    error=f"Command timed out after {timeout_s}s",
                    metadata={
                        "task_id": input.task_id,
                        "evidence": evidence_str,
                        "timestamp": ts,
                    },
                )

            exit_code = proc.returncode or 0
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""
            output = stdout_text
            if stderr_text:
                output += "\n--- stderr ---\n" + stderr_text

            content_length = len(stdout_text) + len(stderr_text)
            ts = datetime.now(timezone.utc).isoformat()
            evidence_str = json.dumps({"content_length": content_length, "exit_code": exit_code, "timestamp": ts})
            success = exit_code == 0
            return ToolResult(
                success=success,
                data=BashOutput(output=output, exit_code=exit_code) if success else None,
                error=None if success else f"Exit code {exit_code}",
                metadata={
                    "exit_code": str(exit_code),
                    "task_id": input.task_id,
                    "evidence": evidence_str,
                    "timestamp": ts,
                },
            )
        except FileNotFoundError as e:
            ts = datetime.now(timezone.utc).isoformat()
            evidence_str = json.dumps({"content_length": 0, "exit_code": -1, "timestamp": ts})
            return ToolResult(
                success=False,
                error=f"Command not found: {e}",
                metadata={
                    "task_id": input.task_id,
                    "evidence": evidence_str,
                    "timestamp": ts,
                },
            )
