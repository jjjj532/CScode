from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cscode.tools2.lsp import LSPInput, LSPTool


class TestLSPDiagnosticsTool:
    async def _make_manager(self, client: Any = None) -> MagicMock:
        """Helper to create a mock LSPManager."""
        mock_manager = MagicMock()
        if client is not None:
            mock_manager.get_client = AsyncMock(return_value=client)
        else:
            mock_manager.get_client = AsyncMock(return_value=None)
        return mock_manager

    async def test_diagnostics_success(self) -> None:
        """Test that the LSP tool returns diagnostics results."""
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=[
            {
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 5},
                },
                "severity": 1,
                "message": "Test diagnostic",
                "source": "test",
            }
        ])
        mock_manager = await self._make_manager(mock_client)

        tool = LSPTool(mock_manager)
        result = await tool.execute(LSPInput(
            command="diagnostics",
            file_path=str(Path(__file__)),
        ))

        assert result.success is True
        assert result.data is not None
        assert len(result.data.results) == 1
        assert result.data.results[0]["message"] == "Test diagnostic"
        assert result.data.results[0]["severity"] == 1

    async def test_diagnostics_empty(self) -> None:
        """Test diagnostics with no results."""
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=None)
        mock_manager = await self._make_manager(mock_client)

        tool = LSPTool(mock_manager)
        result = await tool.execute(LSPInput(
            command="diagnostics",
            file_path=str(Path(__file__)),
        ))

        assert result.success is True
        assert result.data is not None
        assert len(result.data.results) == 0

    async def test_diagnostics_file_not_found(self) -> None:
        """Test diagnostics for a non-existent file."""
        mock_manager = MagicMock()
        tool = LSPTool(mock_manager)
        result = await tool.execute(LSPInput(
            command="diagnostics",
            file_path="/nonexistent/file.py",
        ))

        assert result.success is False
        assert "not found" in (result.error or "").lower()

    async def test_diagnostics_no_lsp_client(self) -> None:
        """Test diagnostics when no LSP client is available."""
        mock_manager = await self._make_manager(None)

        tool = LSPTool(mock_manager)
        result = await tool.execute(LSPInput(
            command="diagnostics",
            file_path=str(Path(__file__)),
        ))

        assert result.success is False
        assert "Unsupported" in (result.error or "") or "no LSP" in (result.error or "").lower()

    async def test_diagnostics_normalizes_single_result(self) -> None:
        """Test that single dict results are normalized to list."""
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value={"message": "single", "range": {}})
        mock_manager = await self._make_manager(mock_client)

        tool = LSPTool(mock_manager)
        result = await tool.execute(LSPInput(
            command="diagnostics",
            file_path=str(Path(__file__)),
        ))

        assert result.success is True
        assert result.data is not None
        assert len(result.data.results) == 1


class TestLSPDiagnosticsAPI:
    def test_api_endpoint_exists(self) -> None:
        """Verify the LSP diagnostics route is registered on the server app."""
        from cscode.server.app import api_router
        routes = [r.path for r in api_router.routes]
        matching = [p for p in routes if "diagnostic" in p.lower()]
        assert len(matching) > 0, f"No diagnostic routes found in {routes}"
