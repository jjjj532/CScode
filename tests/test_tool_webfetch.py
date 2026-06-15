from __future__ import annotations

import pytest
from cscode.tools.webfetch import WebFetchTool


class TestWebFetchTool:
    def test_tool_properties(self) -> None:
        tool = WebFetchTool()
        assert tool.name == "webfetch"
        assert "url" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_fetch_invalid_url(self) -> None:
        tool = WebFetchTool()
        result = await tool.execute({"url": "not-a-valid-url"})
        assert not result.success
        assert result.error is not None
