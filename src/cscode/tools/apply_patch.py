from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from cscode.tools.base import BaseTool, ToolResult


class ApplyPatchTool(BaseTool):
    name = "apply_patch"
    description = "Apply a unified diff patch to a file"
    requires_permission = True
    permission_default = "ask"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the target file",
            },
            "patch_content": {
                "type": "string",
                "description": "Unified diff patch content",
            },
            "strip": {
                "type": "integer",
                "description": "Number of leading path components to strip (default: 1)",
            },
        },
        "required": ["path", "patch_content"],
    }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        path = Path(args["path"])
        patch_content = args["patch_content"]
        strip = args.get("strip", 1)

        if not path.exists():
            return ToolResult(success=False, data="", error=f"File not found: {path}")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
            f.write(patch_content)
            patch_file = f.name

        try:
            result = subprocess.run(
                ["patch", f"-p{strip}", path, patch_file],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return ToolResult(success=True, data=result.stdout or "Patch applied successfully.")
            return ToolResult(
                success=False,
                data=result.stdout,
                error=result.stderr or f"Patch failed with exit code {result.returncode}",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, data="", error="Patch timed out after 30s")
        finally:
            Path(patch_file).unlink(missing_ok=True)
