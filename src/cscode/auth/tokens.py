from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TokenEntry:
    provider: str
    token: str
    refresh_token: str | None = None
    expires_at: float | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class TokenStore:
    def __init__(self, storage_path: str | None = None) -> None:
        if storage_path is None:
            storage_path = str(Path.home() / ".config" / "cscode" / "tokens.json")
        self._path = Path(storage_path)
        self._tokens: dict[str, TokenEntry] = {}
        self._load()

    def set(self, provider: str, entry: TokenEntry) -> None:
        self._tokens[provider] = entry
        self._save()

    def get(self, provider: str) -> TokenEntry | None:
        return self._tokens.get(provider)

    def delete(self, provider: str) -> None:
        self._tokens.pop(provider, None)
        self._save()

    def list_providers(self) -> list[str]:
        return list(self._tokens.keys())

    def _load(self) -> None:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text())
                for provider, entry_data in data.items():
                    self._tokens[provider] = TokenEntry(
                        provider=provider,
                        token=entry_data.get("token", ""),
                        refresh_token=entry_data.get("refresh_token"),
                        expires_at=entry_data.get("expires_at"),
                        metadata=entry_data.get("metadata", {}),
                    )
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            for provider, entry in self._tokens.items():
                data[provider] = {
                    "token": entry.token,
                    "refresh_token": entry.refresh_token,
                    "expires_at": entry.expires_at,
                    "metadata": entry.metadata,
                }
            self._path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning("Failed to save tokens: %s", e)
