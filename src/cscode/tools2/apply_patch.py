"""ApplyPatchTool v2 — apply unified diff patches with typed output."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult


class ApplyPatchInput(BaseModel):
    path: str
    patch_content: str
    strip: int = 1


class ApplyPatchOutput(BaseModel):
    stdout: str


class ApplyPatchTool(Tool[ApplyPatchInput, ApplyPatchOutput]):
    name = "apply_patch"
    description = "Apply a unified diff patch to a file"
    input_schema = ApplyPatchInput
    output_schema = ApplyPatchOutput

    async def execute(self, input: ApplyPatchInput) -> ToolResult[ApplyPatchOutput]:
        path = Path(input.path)
        if not path.exists():
            return ToolResult(
                success=False,
                error=f"File not found: {path}",
            )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
            f.write(input.patch_content)
            patch_file = f.name

        try:
            result = subprocess.run(
                ["patch", f"-p{input.strip}", str(path), patch_file],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return ToolResult(
                    success=True,
                    data=ApplyPatchOutput(stdout=result.stdout or "Patch applied successfully."),
                )
            return ToolResult(
                success=False,
                data=ApplyPatchOutput(stdout=result.stdout),
                error=result.stderr or f"Patch failed with exit code {result.returncode}",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error="Patch timed out after 30s",
            )
        finally:
            Path(patch_file).unlink(missing_ok=True)
