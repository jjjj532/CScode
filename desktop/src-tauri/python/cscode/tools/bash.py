from __future__ import annotations

import asyncio

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
        },
        "required": ["command"],
    }

    async def execute(self, args: dict) -> ToolResult:
        command = args["command"]
        timeout_ms = args.get("timeout", 30000)
        timeout_s = timeout_ms / 1000

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
                return ToolResult(
                    success=False,
                    data="",
                    error=f"Command timed out after {timeout_s}s",
                )

            exit_code = proc.returncode or 0
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n--- stderr ---\n" + stderr.decode("utf-8", errors="replace")

            if exit_code != 0:
                return ToolResult(
                    success=False,
                    data=output,
                    error=f"Exit code {exit_code}",
                    metadata={"exit_code": str(exit_code)},
                )
            return ToolResult(
                success=True,
                data=output,
                metadata={"exit_code": "0"},
            )
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                data="",
                error=f"Command not found: {e}",
            )
