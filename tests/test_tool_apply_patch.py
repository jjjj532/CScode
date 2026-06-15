from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from cscode.tools.apply_patch import ApplyPatchTool


class TestApplyPatchTool:
    def test_tool_properties(self) -> None:
        tool = ApplyPatchTool()
        assert tool.name == "apply_patch"
        assert "patch_content" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_apply_patch_no_file(self) -> None:
        tool = ApplyPatchTool()
        result = await tool.execute({
            "path": "/nonexistent/path/file.txt",
            "patch_content": "--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-old\n+new\n",
        })
        assert not result.success
