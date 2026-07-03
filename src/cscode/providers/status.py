"""Provider Model Status — Check LLM provider availability.

P0-8 alignment: detect whether a provider is online, offline, or in error.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum


class ProviderStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


@dataclass
class StatusInfo:
    status: ProviderStatus
    message: str = ""


# ── Known providers & whether they require an API key ──────────
_KEYLESS_PROVIDERS: frozenset[str] = frozenset({"ollama"})

# ── Default base URLs ──────────────────────────────────────────
_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "azure": "https://api.azure.com/openai/v1",
    "ollama": "http://localhost:11434",
    "openrouter": "https://openrouter.ai/api/v1",
}


@dataclass
class ProviderStatusChecker:
    """Check the status of an LLM provider."""

    cache_ttl: int = 120
    _cache: dict[str, tuple[float, StatusInfo]] = field(default_factory=dict)

    def check(
        self,
        provider: str,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> StatusInfo:
        """Check the status of *provider*.

        Results are cached for ``cache_ttl`` seconds.
        """
        cache_key = self._make_cache_key(provider, api_key, base_url)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        result = self._do_check(provider, api_key, base_url)
        self._set_cache(cache_key, result)
        return result

    # ── Internal ──────────────────────────────────────────────────

    def _make_cache_key(self, provider: str, api_key: str | None, base_url: str | None) -> str:
        return f"{provider}:{api_key or ''}:{base_url or ''}"

    def _get_cached(self, key: str) -> StatusInfo | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, result = entry
        if time.monotonic() - ts > self.cache_ttl:
            del self._cache[key]
            return None
        return result

    def _set_cache(self, key: str, result: StatusInfo) -> None:
        self._cache[key] = (time.monotonic(), result)

    def _do_check(self, provider: str, api_key: str | None, base_url: str | None) -> StatusInfo:
        provider_name = provider.lower()

        # Unknown provider
        known = set(_DEFAULT_BASE_URLS.keys())
        if provider_name not in known:
            return StatusInfo(ProviderStatus.ERROR, f"Unknown provider: {provider}")

        # API key check
        if provider_name not in _KEYLESS_PROVIDERS:
            if not api_key:
                return StatusInfo(ProviderStatus.OFFLINE, f"No API key configured for {provider}")

        # For non-Ollama providers with a key, try a lightweight API call
        # If base_url is custom, it's an ERROR if unreachable (not OFFLINE)
        effective_url = base_url or _DEFAULT_BASE_URLS[provider_name]
        if base_url or provider_name not in _KEYLESS_PROVIDERS:
            return self._try_connect(provider_name, api_key or "", effective_url)

        # Ollama or keyless — no key needed, local by default
        return self._try_connect(provider_name, "", effective_url)

    def _try_connect(self, provider: str, api_key: str, url: str) -> StatusInfo:
        """Try a lightweight HTTP call to the provider.

        This is intentionally simple and uses only stdlib to avoid
        async complications. In production, a HEAD or models list
        request gives more accurate results.
        """
        try:
            import urllib.error
            import urllib.request

            req = urllib.request.Request(url)
            if api_key:
                if provider == "anthropic":
                    req.add_header("x-api-key", api_key)
                elif provider == "gemini":
                    req.add_header("x-goog-api-key", api_key)
                else:
                    req.add_header("Authorization", f"Bearer {api_key}")

            req.add_header("User-Agent", "CScode/1.0")
            req.method = "HEAD"

            try:
                urllib.request.urlopen(req, timeout=5)
                return StatusInfo(ProviderStatus.ONLINE)
            except urllib.error.HTTPError as e:
                # 401/403 means the endpoint is reachable but auth failed
                # → the provider IS online
                if e.code in (401, 403):
                    return StatusInfo(ProviderStatus.ONLINE, "Endpoint reachable")
                return StatusInfo(ProviderStatus.ERROR, f"HTTP {e.code}: {e.reason}")
            except (urllib.error.URLError, OSError) as e:
                return StatusInfo(ProviderStatus.ERROR, f"Connection failed: {e}")

        except Exception as exc:
            return StatusInfo(ProviderStatus.ERROR, str(exc))
