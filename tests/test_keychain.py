"""Tests for KeychainStore — API key storage in system keychain.

P0-3: Store API key in macOS Keychain instead of plaintext config.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cscode.core.keychain import KeychainStore


def test_keychain_store_default_service_name() -> None:
    """KeychainStore should default to service name 'cscode'."""
    store = KeychainStore()
    assert store.service_name == "cscode"


def test_set_get_api_key() -> None:
    """set_api_key should store and get_api_key should retrieve."""
    store = KeychainStore()
    mock_keyring = MagicMock()
    mock_keyring.get_password.return_value = "sk-test123"
    mock_keyring.set_password.return_value = None

    with patch("cscode.core.keychain._get_keyring", return_value=mock_keyring):
        store.set_api_key("openai", "sk-test123")
        mock_keyring.set_password.assert_called_once_with("cscode", "openai", "sk-test123")

        val = store.get_api_key("openai")
        assert val == "sk-test123"
        mock_keyring.get_password.assert_called_once_with("cscode", "openai")


def test_delete_api_key() -> None:
    """delete_api_key should remove a stored key."""
    store = KeychainStore()
    mock_keyring = MagicMock()

    with patch("cscode.core.keychain._get_keyring", return_value=mock_keyring):
        store.delete_api_key("openai")
        mock_keyring.delete_password.assert_called_once_with("cscode", "openai")


def test_get_api_key_returns_none_when_missing() -> None:
    """get_api_key should return None when no key is stored."""
    store = KeychainStore()
    mock_keyring = MagicMock()
    mock_keyring.get_password.return_value = None

    with patch("cscode.core.keychain._get_keyring", return_value=mock_keyring):
        val = store.get_api_key("openai")
        assert val is None


def test_set_api_key_strips_whitespace() -> None:
    """set_api_key should strip leading/trailing whitespace."""
    store = KeychainStore()
    mock_keyring = MagicMock()

    with patch("cscode.core.keychain._get_keyring", return_value=mock_keyring):
        store.set_api_key("openai", "  sk-test123  ")
        mock_keyring.set_password.assert_called_once_with("cscode", "openai", "sk-test123")


def test_delete_api_key_does_not_raise_on_missing() -> None:
    """delete_api_key should not raise if the key doesn't exist."""
    store = KeychainStore()
    mock_keyring = MagicMock()
    mock_keyring.delete_password.side_effect = Exception("not found")

    with patch("cscode.core.keychain._get_keyring", return_value=mock_keyring):
        # Should not raise
        store.delete_api_key("nonexistent")


def test_fallback_when_keyring_not_available() -> None:
    """When keyring module is not available, all operations should return None/False."""
    with patch("cscode.core.keychain._get_keyring", return_value=None):
        store = KeychainStore()
        assert store.get_api_key("openai") is None
        assert store.set_api_key("openai", "sk-test") is None
        assert store.delete_api_key("openai") is None


def test_is_api_key_configured_empty() -> None:
    """is_api_key_configured returns False when no key stored."""
    store = KeychainStore()
    assert not store.is_api_key_configured([])


def test_is_api_key_configured_with_keys() -> None:
    """is_api_key_configured returns True when configured keys exist."""
    store = KeychainStore()
    assert store.is_api_key_configured(["openai"])
    assert not store.is_api_key_configured([])


def test_parse_provider_api_keys_none() -> None:
    """parse_provider_api_keys returns empty dict when no config."""
    store = KeychainStore()
    keys = store.parse_provider_api_keys({})
    assert keys == {}


def test_parse_provider_api_keys_with_provider_dict() -> None:
    """parse_provider_api_keys extracts provider keys from provider dict."""
    store = KeychainStore()
    config = {
        "provider": {
            "openai": {"api_key": "sk-1"},
            "anthropic": {"api_key": "sk-ant-2"},
        }
    }
    keys = store.parse_provider_api_keys(config)
    assert "openai" in keys
    assert "anthropic" in keys
    assert keys["openai"] == "sk-1"
    assert keys["anthropic"] == "sk-ant-2"


def test_parse_provider_api_keys_with_top_level() -> None:
    """parse_provider_api_keys extracts the top-level api_key too."""
    store = KeychainStore()
    config = {"api_key": "sk-top", "provider": "openai"}
    keys = store.parse_provider_api_keys(config)
    assert "default" in keys
    assert keys["default"] == "sk-top"
