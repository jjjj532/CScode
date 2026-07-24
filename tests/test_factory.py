"""Tests for agent factory (src/cscode/app/factory.py).

P2-1: _resolve_api_key() should check keychain before env fallback.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from cscode.app.factory import _resolve_api_key
from cscode.core.config import Config


def test_resolve_api_key_uses_config_value() -> None:
    """_resolve_api_key should return config.api_key when set."""
    config = Config(api_key="sk-from-config")
    result = _resolve_api_key(config)
    assert result == "sk-from-config"


@patch.dict(os.environ, {"OPENAI_API_KEY": "sk-from-env"}, clear=True)
def test_resolve_api_key_falls_back_to_env_var() -> None:
    """_resolve_api_key should fall back to env var when config has no key."""
    config = Config(api_key="", provider="openai")
    result = _resolve_api_key(config)
    assert result == "sk-from-env"


@patch.dict(os.environ, {}, clear=True)
def test_resolve_api_key_returns_empty_when_unavailable() -> None:
    """_resolve_api_key should return '' when no key found anywhere."""
    config = Config(api_key="", provider="openai")
    result = _resolve_api_key(config)
    assert result == ""


@patch("cscode.core.keychain.KeychainStore")
@patch.dict(os.environ, {"OPENAI_API_KEY": "sk-from-env"}, clear=True)
def test_resolve_api_key_checks_keychain_before_env(
    mock_keychain_cls: MagicMock,
) -> None:
    """_resolve_api_key should check keychain before falling back to env vars."""
    mock_store = mock_keychain_cls.return_value
    mock_store.get_api_key.return_value = "sk-from-keychain"

    config = Config(api_key="", provider="openai")
    result = _resolve_api_key(config)

    assert result == "sk-from-keychain", (
        "Should prefer keychain key over env var"
    )
    mock_store.get_api_key.assert_called_once_with("default")


@patch("cscode.core.keychain.KeychainStore")
@patch.dict(os.environ, {}, clear=True)
def test_resolve_api_key_keychain_returns_none_falls_to_env(
    mock_keychain_cls: MagicMock,
) -> None:
    """_resolve_api_key should fall through to env when keychain returns None."""
    mock_store = mock_keychain_cls.return_value
    mock_store.get_api_key.return_value = None

    config = Config(api_key="", provider="openai")
    result = _resolve_api_key(config)

    assert result == "", "Should return '' when no key found anywhere"
