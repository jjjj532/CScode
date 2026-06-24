from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from cscode.tools.base import BaseTool, ToolResult


class BashTool(BaseTool):
    name = "bash"
    description = "Execute a shell command and return the output"
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds (default: 30000)",
            },
            "task_id": {"type": "string", "description": "Test case ID (format: TC-XXX) for tracking"},
        },
        "required": ["command"],
    }

    async def execute(self, args: dict[str, Any], context: dict | None = None) -> ToolResult:
        command = args["command"]
        timeout_ms = args.get("timeout", 30000)
        timeout_s = timeout_ms / 1000
        task_id = args.get("task_id", "")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            except asyncio.TimeoutError:
                proc.kill()
                evidence = json.dumps({
                    "content_length": 0,
                    "error": "timeout",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                return ToolResult(
                    success=False,
                    data="",
                    error=f"Command timed out after {timeout_s}s",
                    metadata={"task_id": task_id, "evidence": evidence, "verified": "False"},
                )

            exit_code = proc.returncode or 0
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n--- stderr ---\n" + stderr.decode("utf-8", errors="replace")

            if exit_code != 0:
                evidence = json.dumps({
                    "content_length": len(output) if output else 0,
                    "exit_code": str(exit_code),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                return ToolResult(
                    success=False,
                    data=output,
                    error=f"Exit code {exit_code}",
                    metadata={"exit_code": str(exit_code), "task_id": task_id, "evidence": evidence, "verified": "False"},
                )
            evidence = json.dumps({
                "content_length": len(output) if output else 0,
                "exit_code": "0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return ToolResult(
                success=True,
                data=output,
                metadata={"exit_code": "0", "task_id": task_id, "evidence": evidence, "verified": str(len(output) > 0)},
            )
        except FileNotFoundError as e:
            evidence = json.dumps({
                "content_length": 0,
                "error": "not_found",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return ToolResult(
                success=False,
                data="",
                error=f"Command not found: {e}",
                metadata={"task_id": task_id, "evidence": evidence, "verified": "False"},
            )
