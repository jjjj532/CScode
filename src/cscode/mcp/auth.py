from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

import httpx

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class OAuthToken:
    """OAuth 2.0 token response."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None
    acquired_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        if self.expires_in is None:
            return False
        return time.time() >= self.acquired_at + self.expires_in - 60  # 60s buffer

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OAuthToken:
        return cls(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in"),
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope"),
            acquired_at=data.get("acquired_at", time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
            "acquired_at": self.acquired_at,
        }


class OAuthTokenStore(Protocol):
    """Protocol for token storage."""

    async def get_token(self) -> OAuthToken | None: ...
    async def set_token(self, token: OAuthToken) -> None: ...
    async def clear_token(self) -> None: ...


class InMemoryTokenStore:
    """In-memory token storage."""

    def __init__(self) -> None:
        self._token: OAuthToken | None = None

    async def get_token(self) -> OAuthToken | None:
        return self._token

    async def set_token(self, token: OAuthToken) -> None:
        self._token = token

    async def clear_token(self) -> None:
        self._token = None


class FileTokenStore:
    """File-based token storage for persistence across restarts."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    async def get_token(self) -> OAuthToken | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text())
            return OAuthToken.from_dict(data)
        except (json.JSONDecodeError, KeyError, OSError):
            logger.exception("Failed to read token from %s", self._path)
            return None

    async def set_token(self, token: OAuthToken) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(token.to_dict(), indent=2))

    async def clear_token(self) -> None:
        if self._path.exists():
            self._path.unlink()


@dataclass
class OAuthServerMetadata:
    """OAuth authorization server metadata."""

    authorization_endpoint: str
    token_endpoint: str
    issuer: str | None = None
    introspection_endpoint: str | None = None
    revocation_endpoint: str | None = None


@dataclass
class OAuthClientConfig:
    """Configuration for an OAuth-enabled MCP client."""

    server_url: str
    client_id: str | None = None
    client_secret: str | None = None
    scopes: str | None = None
    redirect_uri: str = "http://127.0.0.1:8080/callback"
    token_store: OAuthTokenStore | None = None

    def __post_init__(self) -> None:
        if self.token_store is None:
            self.token_store = InMemoryTokenStore()


class OAuthClientProvider:
    """Handles OAuth 2.0 authorization code flow for MCP servers.

    Supports both authorization code (browser-based) and client credentials
    (machine-to-machine) grants. Integrates with httpx as an auth hook.
    """

    def __init__(
        self,
        config: OAuthClientConfig,
        metadata: OAuthServerMetadata,
        redirect_handler: Callable[[str], None] | None = None,
        callback_handler: Callable[[], Awaitable[dict[str, str]]] | None = None,
    ) -> None:
        self.config = config
        self.metadata = metadata
        self._redirect_handler = redirect_handler or self._default_redirect_handler
        self._callback_handler = callback_handler
        self._token: OAuthToken | None = None
        self._lock = asyncio.Lock()

    async def get_token(self) -> OAuthToken:
        """Get a valid token, refreshing or acquiring if needed."""
        async with self._lock:
            # Check stored token
            assert self.config.token_store is not None
            stored = await self.config.token_store.get_token()
            if stored is not None and not stored.is_expired:
                self._token = stored
                return stored

            # Try refresh
            if stored is not None and stored.refresh_token:
                try:
                    token = await self._refresh_token(stored.refresh_token)
                    await self.config.token_store.set_token(token)
                    self._token = token
                    return token
                except Exception:
                    logger.warning("Token refresh failed, re-authorizing")

            # Perform authorization
            token = await self._authorize()
            await self.config.token_store.set_token(token)
            self._token = token
            return token

    async def clear_auth(self) -> None:
        """Clear stored tokens."""
        async with self._lock:
            self._token = None
            assert self.config.token_store is not None
            await self.config.token_store.clear_token()

    async def _authorize(self) -> OAuthToken:
        """Perform OAuth authorization code flow."""
        # Try client credentials if we have a client_secret
        if self.config.client_secret:
            return await self._client_credentials_grant()

        # Authorization code flow (browser-based)
        return await self._authorization_code_grant()

    async def _client_credentials_grant(self) -> OAuthToken:
        """Perform client credentials grant."""
        data: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": self.config.client_id or "",
            "client_secret": self.config.client_secret or "",
        }
        if self.config.scopes:
            data["scope"] = self.config.scopes

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.metadata.token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            return OAuthToken.from_dict(resp.json())

    async def _authorization_code_grant(self) -> OAuthToken:
        """Perform authorization code grant (browser-based)."""
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = self._sha256_b64(code_verifier)

        params = {
            "response_type": "code",
            "client_id": self.config.client_id or "mcp-client",
            "redirect_uri": self.config.redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if self.config.scopes:
            params["scope"] = self.config.scopes

        auth_url = f"{self.metadata.authorization_endpoint}?{urllib.parse.urlencode(params)}"
        self._redirect_handler(auth_url)

        if self._callback_handler is not None:
            callback = await self._callback_handler()
        else:
            callback = await self._default_callback_handler()

        if callback.get("state") != state:
            raise ValueError("State mismatch in OAuth callback")

        code = callback["code"]
        token_data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id or "mcp-client",
            "code_verifier": code_verifier,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.metadata.token_endpoint,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            return OAuthToken.from_dict(resp.json())

    async def _refresh_token(self, refresh_token: str) -> OAuthToken:
        """Refresh an expired token."""
        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.config.client_id or "mcp-client",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.metadata.token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            return OAuthToken.from_dict(resp.json())

    @staticmethod
    def _sha256_b64(value: str) -> str:
        digest = hashlib.sha256(value.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    @staticmethod
    def _default_redirect_handler(url: str) -> None:
        print(f"Open this URL in your browser:\n{url}")
        webbrowser.open(url)

    @staticmethod
    async def _default_callback_handler() -> dict[str, str]:
        """Read callback from stdin (fallback)."""
        code = input("Enter authorization code from redirect URL: ").strip()
        state = input("Enter state from redirect URL: ").strip()
        return {"code": code, "state": state}


class MCPOAuthClient:
    """MCP client with OAuth support for HTTP transport.

    Wraps httpx.AsyncClient with OAuth token handling for MCP Streamable HTTP.
    """

    def __init__(
        self,
        server_url: str,
        auth_provider: OAuthClientProvider,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.auth_provider = auth_provider
        self._http_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> MCPOAuthClient:
        token = await self.auth_provider.get_token()
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "Content-Type": "application/json",
        }
        self._http_client = httpx.AsyncClient(headers=headers)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def request(self, body: dict[str, Any]) -> dict[str, Any]:
        """Send an MCP request with OAuth authentication."""
        assert self._http_client is not None
        resp = await self._http_client.post(
            self.server_url,
            json=body,
        )

        if resp.status_code == 401:
            # Token expired, refresh and retry
            token = await self.auth_provider.get_token()
            headers = {
                "Authorization": f"{token.token_type} {token.access_token}",
                "Content-Type": "application/json",
            }
            self._http_client = httpx.AsyncClient(headers=headers)
            resp = await self._http_client.post(self.server_url, json=body)

        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self.request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        })
        return result.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self.request({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        return result.get("result", {})


async def discover_oauth_metadata(server_url: str) -> OAuthServerMetadata | None:
    """Discover OAuth metadata from an MCP server.

    Follows the MCP authorization spec: fetches protected resource metadata
    and discovers authorization server endpoints.
    """
    metadata_url = f"{server_url.rstrip('/')}/.well-known/oauth-protected-resource"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(metadata_url, timeout=10)
            resp.raise_for_status()
            meta = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError):
            logger.debug("No OAuth protected resource metadata at %s", metadata_url)
            return None

    auth_servers = meta.get("authorization_servers", [])
    if not auth_servers:
        return None

    # Try OAuth 2.0 discovery on the first authorization server
    issuer = auth_servers[0].rstrip("/")
    discovery_urls = [
        f"{issuer}/.well-known/oauth-authorization-server",
        f"{issuer}/.well-known/openid-configuration",
    ]

    for disc_url in discovery_urls:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(disc_url, timeout=10)
                resp.raise_for_status()
                disc = resp.json()
                return OAuthServerMetadata(
                    authorization_endpoint=disc.get("authorization_endpoint", ""),
                    token_endpoint=disc.get("token_endpoint", ""),
                    issuer=disc.get("issuer"),
                    introspection_endpoint=disc.get("introspection_endpoint"),
                    revocation_endpoint=disc.get("revocation_endpoint"),
                )
            except (httpx.HTTPError, json.JSONDecodeError):
                continue

    return None
