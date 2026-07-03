"""LSPTool v2 — expose LSP capabilities to the LLM.

Wraps LSPManager (from lsp/manager.py) into the typed Tool[I, O] interface,
providing hover, goto-definition, find-references, completion, diagnostics,
and document-symbols as a single command-discriminated tool.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from cscode.lsp.manager import LSPManager
from cscode.tools2.base import Tool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class LSPInput(BaseModel):
    """Input schema for LSPTool.

    Attributes:
        command: The LSP operation to perform.
        file_path: Absolute path to the file.
        line: 0-based line number (required for hover/definition/references/completion).
        character: 0-based character offset (required for hover/definition/references/completion).
    """

    command: Literal["hover", "definition", "references", "completion", "diagnostics", "symbols"]
    file_path: str
    line: int = 0
    character: int = 0


class LSPOutput(BaseModel):
    """Output schema — normalized list of LSP results."""

    results: list[dict[str, Any]]


# LSP method name → LSP protocol method
_LSP_METHODS: dict[str, str] = {
    "hover": "textDocument/hover",
    "definition": "textDocument/definition",
    "references": "textDocument/references",
    "completion": "textDocument/completion",
    "diagnostics": "textDocument/diagnostic",
    "symbols": "textDocument/documentSymbol",
}

# Commands that require a position parameter
_POSITION_COMMANDS = frozenset({"hover", "definition", "references", "completion"})


class LSPTool(Tool[LSPInput, LSPOutput]):
    """Tool that delegates to LSPManager for code intelligence.

    Accepts an optional manager for dependency injection (testing).
    """

    name = "lsp"
    description = (
        "Get LSP (Language Server Protocol) information for code files. "
        "Use this to get hover documentation, go-to-definition locations, "
        "find references, get code completions, check diagnostics, or "
        "list document symbols."
    )
    input_schema = LSPInput
    output_schema = LSPOutput

    def __init__(self, manager: LSPManager | None = None) -> None:
        self._manager = manager or LSPManager()

    async def execute(self, input: LSPInput) -> ToolResult[LSPOutput]:
        """Execute an LSP command against the file.

        Steps:
          1. Validate file exists
          2. Get LSP client for the file's language
          3. Build LSP params from input
          4. Call the LSP method
          5. Normalize and return results
        """
        file_path = Path(input.file_path)
        if not file_path.exists():
            return ToolResult(
                success=False,
                error=f"File not found: {input.file_path}",
            )

        client = await self._manager.get_client(str(file_path))
        if client is None:
            return ToolResult(
                success=False,
                error=f"Unsupported language or no LSP server available for: {input.file_path}",
            )

        method = _LSP_METHODS.get(input.command)
        if method is None:
            return ToolResult(
                success=False,
                error=f"Unknown LSP command: {input.command}",
            )

        # Build LSP params
        uri = file_path.resolve().as_uri()
        params: dict[str, Any] = {
            "textDocument": {"uri": uri},
        }
        if input.command in _POSITION_COMMANDS:
            params["position"] = {"line": input.line, "character": input.character}

        logger.debug(
            "LSPTool.execute: command=%s file=%s method=%s line=%d char=%d",
            input.command, input.file_path, method, input.line, input.character,
        )

        try:
            raw = await client.request(method, params)
        except Exception as e:
            logger.exception("LSPTool: request failed command=%s file=%s", input.command, input.file_path)
            return ToolResult(
                success=False,
                error=f"LSP request failed: {e}",
            )

        results = _normalize_results(raw)
        logger.debug("LSPTool.execute: done command=%s results=%d", input.command, len(results))
        return ToolResult(
            success=True,
            data=LSPOutput(results=results),
            metadata={"command": input.command, "file": input.file_path},
        )


def _normalize_results(raw: Any) -> list[dict[str, Any]]:
    """Normalize LSP responses into a uniform list-of-dicts format.

    LSP responses vary: some return a single dict, some a list,
    some None. This normalizes them all to a list of dicts.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [r if isinstance(r, dict) else {"value": str(r)} for r in raw]
    if isinstance(raw, dict):
        return [raw]
    return [{"value": str(raw)}]
