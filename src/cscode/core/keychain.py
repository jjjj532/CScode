"""Keychain integration for secure API key storage.

P0-3: Store API key in macOS Keychain (via keyring lib) instead of
plaintext config. Falls back gracefully when keyring is not available.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _get_keyring() -> Any | None:
    """Try to import keyring; return the module or None."""
    try:
        import keyring  # type: ignore[import-not-found]

        return keyring
    except ImportError:
        logger.debug("keyring library not available — API keys stored in plaintext config")
        return None


class KeychainStore:
    """Store/retrieve API keys from the system keychain.

    Uses the ``keyring`` library internally. On macOS this stores
    passwords in the login keychain. In environments where keyring is
    not installed or has no backend, all methods safely no-op.

    Service name is ``cscode``; usernames are provider names such as
    ``openai``, ``anthropic``, or ``default`` for the top-level key.

    Usage::

        store = KeychainStore()
        store.set_api_key("openai", "sk-...")
        key = store.get_api_key("openai")   # "sk-..." | None
        store.delete_api_key("openai")
    """

    def __init__(self, service_name: str = "cscode") -> None:
        self.service_name = service_name
        # Lazily resolve keyring to allow test patching between
        # construction and the first API call.
        self._kr: Any | None = None

    # ── Public API — sync (keyring is a sync library) ───────────────

    def set_api_key(self, username: str, key: str) -> None:
        """Store *key* under *username* (provider name) in the keychain.

        No-ops when keyring is not available.
        """
        kr = self._resolve_keyring()
        if kr is None:
            return None
        cleaned = key.strip()
        if not cleaned:
            return None
        try:
            kr.set_password(self.service_name, username, cleaned)
            logger.debug("API key for %s stored in keychain", username)
        except Exception:
            logger.exception("Failed to store API key in keychain for %s", username)

    def get_api_key(self, username: str) -> str | None:
        """Retrieve an API key from the keychain, or *None* if missing.

        Also returns *None* when keyring is not available.
        """
        kr = self._resolve_keyring()
        if kr is None:
            return None
        try:
            val = kr.get_password(self.service_name, username)
            return str(val) if val is not None else None
        except Exception:
            logger.debug("Failed to read API key from keychain for %s", username)
            return None

    def delete_api_key(self, username: str) -> None:
        """Delete a stored API key.

        Safe to call for keys that do not exist.
        """
        kr = self._resolve_keyring()
        if kr is None:
            return None
        try:
            kr.delete_password(self.service_name, username)
            logger.debug("API key for %s deleted from keychain", username)
        except Exception:
            logger.debug("No API key to delete for %s from keychain", username)

    # ── Internal ────────────────────────────────────────────────────

    def _resolve_keyring(self) -> Any | None:
        """Return the keyring module, resolving on first call.

        Separating resolution from construction allows test code to
        patch ``_get_keyring`` *after* creating a KeychainStore.
        """
        if self._kr is None:
            self._kr = _get_keyring()
        return self._kr

    # ── Convenience helpers ─────────────────────────────────────────

    @staticmethod
    def is_api_key_configured(configured_providers: list[str]) -> bool:
        """Return *True* if any provider has been configured."""
        return len(configured_providers) > 0

    @staticmethod
    def parse_provider_api_keys(config: dict[str, Any]) -> dict[str, str]:
        """Extract API keys from a config dict.

        Returns a mapping of ``{provider_name: key}`` suitable for
        passing to ``set_api_key``. Includes the top-level ``api_key``
        (mapped to ``"default"``) if present, plus per-provider keys
        from the ``provider`` sub-dict.
        """
        keys: dict[str, str] = {}

        # Top-level key (provider-agnostic)
        top = config.get("api_key")
        if top and isinstance(top, str):
            keys["default"] = top.strip()

        # Per-provider keys from provider dict
        providers = config.get("provider")
        if isinstance(providers, dict):
            for name, pd in providers.items():
                if isinstance(pd, dict):
                    pk = pd.get("api_key")
                    if pk and isinstance(pk, str):
                        keys[name] = pk.strip()

        return keys
