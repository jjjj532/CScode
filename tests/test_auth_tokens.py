from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from cscode.auth.tokens import TokenStore, TokenEntry


class TestTokenEntry:
    def test_create_entry(self) -> None:
        entry = TokenEntry(provider="github", token="gh_token_123", refresh_token="gh_refresh")
        assert entry.provider == "github"
        assert entry.token == "gh_token_123"
        assert entry.refresh_token == "gh_refresh"


class TestTokenStore:
    def test_store_and_get(self) -> None:
        store = TokenStore()
        store.set("github", TokenEntry(provider="github", token="abc123"))
        entry = store.get("github")
        assert entry is not None
        assert entry.token == "abc123"

    def test_get_missing(self) -> None:
        store = TokenStore()
        assert store.get("nonexistent") is None

    def test_delete(self) -> None:
        store = TokenStore()
        store.set("github", TokenEntry(provider="github", token="abc"))
        store.delete("github")
        assert store.get("github") is None

    def test_list_providers(self) -> None:
        store = TokenStore()
        store.set("github", TokenEntry(provider="github", token="a"))
        store.set("openai", TokenEntry(provider="openai", token="b"))
        providers = store.list_providers()
        assert "github" in providers
        assert "openai" in providers
