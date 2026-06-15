from __future__ import annotations

import pytest
from cscode.tools.websearch import WebSearchTool


class TestWebSearchTool:
    def test_tool_properties(self) -> None:
        tool = WebSearchTool()
        assert tool.name == "websearch"
        assert "query" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_search_no_query(self) -> None:
        tool = WebSearchTool()
        with pytest.raises(KeyError):
            await tool.execute({})
