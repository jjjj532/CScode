"""Tests for LSPTool v2 — P0-1.

Tests the LSP tool with mocked LSPManager to avoid needing
real LSP servers installed in CI.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from cscode.lsp.client import LSPClient
from cscode.lsp.manager import LSPManager
from cscode.tools2.lsp import LSPInput, LSPOutput, LSPTool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_py_file(tmp_path: Path) -> Path:
    """Create a temporary .py file for LSP operations."""
    f = tmp_path / "test.py"
    f.write_text("x = 1\n")
    return f


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock(spec=LSPClient)
    client.is_running = True
    client.request = AsyncMock()
    return client


@pytest.fixture
def mock_manager(mock_client: AsyncMock) -> MagicMock:
    manager = MagicMock(spec=LSPManager)
    manager.get_client = AsyncMock(return_value=mock_client)
    return manager


@pytest.fixture
def tool(mock_manager: MagicMock) -> LSPTool:
    return LSPTool(manager=mock_manager)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestLSPToolRegistration:
    def test_name(self) -> None:
        assert LSPTool.name == "lsp"

    def test_description_not_empty(self) -> None:
        assert LSPTool.description

    def test_input_schema(self) -> None:
        assert LSPTool.input_schema is LSPInput

    def test_output_schema(self) -> None:
        assert LSPTool.output_schema is LSPOutput


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestLSPInputValidation:
    def test_valid_hover(self) -> None:
        inp = LSPInput(command="hover", file_path="/tmp/test.py", line=1, character=0)
        assert inp.command == "hover"
        assert inp.file_path == "/tmp/test.py"
        assert inp.line == 1
        assert inp.character == 0

    def test_valid_diagnostics_no_position(self) -> None:
        """diagnostics doesn't require line/character."""
        inp = LSPInput(command="diagnostics", file_path="/tmp/test.py")
        assert inp.line == 0
        assert inp.character == 0

    def test_valid_symbols_no_position(self) -> None:
        inp = LSPInput(command="symbols", file_path="/tmp/test.py")
        assert inp.command == "symbols"

    @pytest.mark.parametrize("cmd", ["hover", "definition", "references", "completion", "diagnostics", "symbols"])
    def test_all_valid_commands(self, cmd: str) -> None:
        inp = LSPInput(command=cmd, file_path="/tmp/test.py")  # type: ignore[arg-type]
        assert inp.command == cmd


# ---------------------------------------------------------------------------
# Execution with mocked LSP
# ---------------------------------------------------------------------------

class TestLSPToolExecute:
    @pytest.mark.asyncio
    async def test_file_not_found(self, tool: LSPTool) -> None:
        """Non-existent file should return error."""
        result = await tool.execute(LSPInput(
            command="hover", file_path="/nonexistent/file.py",
        ))
        assert not result.success
        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_unsupported_language(
        self, tool: LSPTool, mock_manager: MagicMock, tmp_path: Path,
    ) -> None:
        """When LSPManager returns None, should report unsupported."""
        xyz_file = tmp_path / "test.xyz"
        xyz_file.write_text("unknown content")
        mock_manager.get_client.return_value = None
        result = await tool.execute(LSPInput(
            command="hover", file_path=str(xyz_file),
        ))
        assert not result.success
        assert result.error is not None
        assert "unsupported" in result.error.lower() or "server" in result.error.lower()

    @pytest.mark.asyncio
    async def test_hover(
        self, tool: LSPTool, mock_client: AsyncMock, tmp_py_file: Path,
    ) -> None:
        """Hover command should send textDocument/hover and return results."""
        mock_client.request.return_value = {
            "contents": {"kind": "markdown", "value": "**str** built-in type"},
        }
        result = await tool.execute(LSPInput(
            command="hover", file_path=str(tmp_py_file), line=1, character=0,
        ))
        assert result.success
        assert result.data is not None
        assert len(result.data.results) >= 1

        # Verify correct LSP method was called
        call_kwargs = mock_client.request.call_args
        assert call_kwargs is not None
        assert call_kwargs[0][0] == "textDocument/hover"

    @pytest.mark.asyncio
    async def test_definition(
        self, tool: LSPTool, mock_client: AsyncMock, tmp_py_file: Path,
    ) -> None:
        """Definition command should return location."""
        mock_client.request.return_value = {
            "uri": "file:///tmp/def.py",
            "range": {"start": {"line": 5, "character": 0}, "end": {"line": 5, "character": 10}},
        }
        result = await tool.execute(LSPInput(
            command="definition", file_path=str(tmp_py_file), line=1, character=0,
        ))
        assert result.success
        assert result.data is not None
        assert len(result.data.results) >= 1

    @pytest.mark.asyncio
    async def test_references(
        self, tool: LSPTool, mock_client: AsyncMock, tmp_py_file: Path,
    ) -> None:
        """References command should return list of locations."""
        mock_client.request.return_value = [
            {"uri": "file:///tmp/ref.py", "range": {"start": {"line": 10, "character": 0}}},
            {"uri": "file:///tmp/ref2.py", "range": {"start": {"line": 3, "character": 5}}},
        ]
        result = await tool.execute(LSPInput(
            command="references", file_path=str(tmp_py_file), line=1, character=0,
        ))
        assert result.success
        assert result.data is not None
        assert len(result.data.results) == 2

    @pytest.mark.asyncio
    async def test_completion(
        self, tool: LSPTool, mock_client: AsyncMock, tmp_py_file: Path,
    ) -> None:
        """Completion command should return completion items."""
        mock_client.request.return_value = [
            {"label": "print", "kind": 3},
            {"label": "len", "kind": 3},
        ]
        result = await tool.execute(LSPInput(
            command="completion", file_path=str(tmp_py_file), line=1, character=10,
        ))
        assert result.success
        assert result.data is not None
        assert len(result.data.results) >= 2

    @pytest.mark.asyncio
    async def test_diagnostics(
        self, tool: LSPTool, mock_client: AsyncMock, tmp_py_file: Path,
    ) -> None:
        """Diagnostics command should return diagnostic items."""
        mock_client.request.return_value = [
            {"range": {}, "severity": 1, "message": "unused import"},
        ]
        result = await tool.execute(LSPInput(
            command="diagnostics", file_path=str(tmp_py_file),
        ))
        assert result.success
        assert result.data is not None
        assert len(result.data.results) >= 1

    @pytest.mark.asyncio
    async def test_symbols(
        self, tool: LSPTool, mock_client: AsyncMock, tmp_py_file: Path,
    ) -> None:
        """Symbols command should return document symbols."""
        mock_client.request.return_value = [
            {"name": "my_func", "kind": 12,
             "location": {"uri": f"file://{tmp_py_file}", "range": {}}},
        ]
        result = await tool.execute(LSPInput(
            command="symbols", file_path=str(tmp_py_file),
        ))
        assert result.success
        assert result.data is not None
        assert len(result.data.results) >= 1

    @pytest.mark.asyncio
    async def test_lsp_client_error(
        self, tool: LSPTool, mock_client: AsyncMock, tmp_py_file: Path,
    ) -> None:
        """When LSP client raises, tool should return error gracefully."""
        mock_client.request.side_effect = Exception("LSP server connection lost")
        result = await tool.execute(LSPInput(
            command="hover", file_path=str(tmp_py_file), line=1, character=0,
        ))
        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_null_result(
        self, tool: LSPTool, mock_client: AsyncMock, tmp_py_file: Path,
    ) -> None:
        """Null/None result from LSP should produce empty results, not crash."""
        mock_client.request.return_value = None
        result = await tool.execute(LSPInput(
            command="hover", file_path=str(tmp_py_file), line=1, character=0,
        ))
        assert result.success
        assert result.data is not None
        assert result.data.results == []

    @pytest.mark.asyncio
    async def test_to_definition(self) -> None:
        """LSPTool should produce valid ToolDefinition."""
        tool = LSPTool()
        definition = tool.to_definition()
        assert definition.name == "lsp"
        assert definition.description
        assert "type" in definition.input_schema
