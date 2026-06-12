from __future__ import annotations

import shutil
from pathlib import Path

from cscode.lsp.client import LSPClient


_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
}

_SERVER_COMMANDS: dict[str, list[str] | None] = {
    "python": ["pylsp"],
    "typescript": ["typescript-language-server", "--stdio"],
    "javascript": ["typescript-language-server", "--stdio"],
    "go": ["gopls"],
    "rust": ["rust-analyzer"],
    "java": None,
    "ruby": ["solargraph"],
    "php": None,
}


class LSPManager:
    def __init__(self) -> None:
        self._clients: dict[str, LSPClient] = {}

    def detect_language(self, file_path: str) -> str:
        ext = Path(file_path).suffix.lower()
        return _LANGUAGE_MAP.get(ext, "unknown")

    def get_server_command(self, language: str) -> list[str] | None:
        cmd = _SERVER_COMMANDS.get(language)
        if cmd is None:
            return None
        cmd_name = cmd[0]
        if not shutil.which(cmd_name):
            return None
        return cmd

    async def get_client(self, file_path: str) -> LSPClient | None:
        lang = self.detect_language(file_path)
        if lang == "unknown":
            return None

        if lang in self._clients:
            return self._clients[lang]

        cmd = self.get_server_command(lang)
        if cmd is None:
            return None

        client = LSPClient(server_command=cmd)
        try:
            await client.start()
        except Exception:
            return None

        self._clients[lang] = client
        return client

    async def close_all(self) -> None:
        for client in self._clients.values():
            await client.stop()
        self._clients.clear()

    def supported_languages(self) -> list[str]:
        return list(set(_LANGUAGE_MAP.values()))
