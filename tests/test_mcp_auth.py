"""Tests for MCP OAuth — OAuthToken, OAuthClientProvider, MCPOAuthClient."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cscode.mcp.auth import (
    FileTokenStore,
    InMemoryTokenStore,
    MCPOAuthClient,
    OAuthClientConfig,
    OAuthClientProvider,
    OAuthServerMetadata,
    OAuthToken,
    discover_oauth_metadata,
)

# ─── Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def token() -> OAuthToken:
    return OAuthToken(
        access_token="test_access",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="test_refresh",
        scope="read write",
        acquired_at=time.time(),
    )


@pytest.fixture
def expired_token() -> OAuthToken:
    return OAuthToken(
        access_token="expired_access",
        expires_in=3600,
        refresh_token="old_refresh",
        acquired_at=time.time() - 3700,  # expired (3600 + 60s buffer = 3660)
    )


@pytest.fixture
def config() -> OAuthClientConfig:
    return OAuthClientConfig(
        server_url="http://localhost:8080",
        client_id="test-client",
        client_secret="test-secret",
        scopes="read write",
        redirect_uri="http://localhost:8080/callback",
        token_store=InMemoryTokenStore(),
    )


@pytest.fixture
def metadata() -> OAuthServerMetadata:
    return OAuthServerMetadata(
        authorization_endpoint="http://localhost:8080/auth",
        token_endpoint="http://localhost:8080/token",
        issuer="http://localhost:8080",
    )


@pytest.fixture
def provider(config: OAuthClientConfig, metadata: OAuthServerMetadata) -> OAuthClientProvider:
    return OAuthClientProvider(config, metadata)


# ─── OAuthToken ─────────────────────────────────────────────────────

class TestOAuthToken:
    def test_create_token(self) -> None:
        t = OAuthToken(access_token="abc")
        assert t.access_token == "abc"
        assert t.token_type == "Bearer"
        assert t.expires_in is None
        assert t.refresh_token is None
        assert t.scope is None

    def test_is_expired_no_expires_in(self, token: OAuthToken) -> None:
        token.expires_in = None
        assert not token.is_expired

    def test_is_expired_false(self, token: OAuthToken) -> None:
        assert not token.is_expired  # just acquired

    def test_is_expired_true(self, expired_token: OAuthToken) -> None:
        assert expired_token.is_expired

    def test_from_dict(self) -> None:
        t = OAuthToken.from_dict({
            "access_token": "abc",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "ref",
            "scope": "read",
        })
        assert t.access_token == "abc"
        assert t.token_type == "Bearer"
        assert t.expires_in == 3600
        assert t.refresh_token == "ref"
        assert t.scope == "read"

    def test_from_dict_minimal(self) -> None:
        t = OAuthToken.from_dict({"access_token": "abc"})
        assert t.access_token == "abc"
        assert t.token_type == "Bearer"

    def test_to_dict(self, token: OAuthToken) -> None:
        d = token.to_dict()
        assert d["access_token"] == "test_access"
        assert d["token_type"] == "Bearer"
        assert d["expires_in"] == 3600
        assert d["refresh_token"] == "test_refresh"
        assert d["scope"] == "read write"
        assert "acquired_at" in d


# ─── InMemoryTokenStore ─────────────────────────────────────────────

class TestInMemoryTokenStore:
    async def test_get_token_none(self) -> None:
        store = InMemoryTokenStore()
        assert await store.get_token() is None

    async def test_set_and_get(self, token: OAuthToken) -> None:
        store = InMemoryTokenStore()
        await store.set_token(token)
        assert await store.get_token() is token

    async def test_clear(self, token: OAuthToken) -> None:
        store = InMemoryTokenStore()
        await store.set_token(token)
        await store.clear_token()
        assert await store.get_token() is None


# ─── FileTokenStore ─────────────────────────────────────────────────

class TestFileTokenStore:
    async def test_get_token_no_file(self, tmp_path: Path) -> None:
        store = FileTokenStore(tmp_path / "nonexistent.json")
        assert await store.get_token() is None

    async def test_set_and_get(self, tmp_path: Path, token: OAuthToken) -> None:
        p = tmp_path / "token.json"
        store = FileTokenStore(p)
        await store.set_token(token)
        assert p.exists()
        data = json.loads(p.read_text())
        assert data["access_token"] == "test_access"

        # Read back
        store2 = FileTokenStore(p)
        result = await store2.get_token()
        assert result is not None
        assert result.access_token == "test_access"

    async def test_clear(self, tmp_path: Path, token: OAuthToken) -> None:
        p = tmp_path / "token.json"
        store = FileTokenStore(p)
        await store.set_token(token)
        await store.clear_token()
        assert not p.exists()
        assert await store.get_token() is None

    async def test_get_token_corrupted_file(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not json")
        store = FileTokenStore(p)
        assert await store.get_token() is None

    async def test_clear_no_file(self, tmp_path: Path) -> None:
        store = FileTokenStore(tmp_path / "nonexistent.json")
        await store.clear_token()  # should not raise


# ─── OAuthClientProvider ────────────────────────────────────────────

class TestOAuthClientProvider:
    def test_init(self, config: OAuthClientConfig, metadata: OAuthServerMetadata) -> None:
        p = OAuthClientProvider(config, metadata)
        assert p.config is config
        assert p.metadata is metadata
        assert p._token is None
        assert p._redirect_handler is not None
        assert p._callback_handler is None

    def test_init_with_custom_handlers(self, config: OAuthClientConfig, metadata: OAuthServerMetadata) -> None:
        def redirect(url: str) -> None:
            pass

        async def callback() -> dict[str, str]:
            return {"code": "x", "state": "y"}

        p = OAuthClientProvider(config, metadata, redirect_handler=redirect, callback_handler=callback)
        assert p._redirect_handler is redirect
        assert p._callback_handler is callback

    async def test_get_token_stored_valid(
        self, token: OAuthToken, provider: OAuthClientProvider
    ) -> None:
        store = provider.config.token_store
        assert store is not None
        await store.set_token(token)
        result = await provider.get_token()
        assert result is token
        assert provider._token is token

    async def test_get_token_expired_refresh(
        self, expired_token: OAuthToken, provider: OAuthClientProvider
    ) -> None:
        store = provider.config.token_store
        assert store is not None
        await store.set_token(expired_token)
        new_token = OAuthToken(access_token="refreshed", expires_in=3600)

        with patch.object(provider, "_refresh_token", AsyncMock(return_value=new_token)) as mock:
            result = await provider.get_token()
            assert result.access_token == "refreshed"
            mock.assert_awaited_once_with("old_refresh")

    async def test_get_token_expired_no_refresh_token(
        self, provider: OAuthClientProvider
    ) -> None:
        stale = OAuthToken(access_token="stale", expires_in=1, acquired_at=time.time() - 100)
        store = provider.config.token_store
        assert store is not None
        await store.set_token(stale)
        new_token = OAuthToken(access_token="reauthorized")

        with patch.object(provider, "_authorize", AsyncMock(return_value=new_token)):
            result = await provider.get_token()
            assert result.access_token == "reauthorized"

    async def test_get_token_no_stored(
        self, provider: OAuthClientProvider
    ) -> None:
        new_token = OAuthToken(access_token="new")
        with patch.object(provider, "_authorize", AsyncMock(return_value=new_token)):
            result = await provider.get_token()
            assert result.access_token == "new"

    async def test_clear_auth(
        self, token: OAuthToken, provider: OAuthClientProvider
    ) -> None:
        store = provider.config.token_store
        assert store is not None
        await store.set_token(token)
        provider._token = token
        await provider.clear_auth()
        assert provider._token is None
        token_store = provider.config.token_store
        assert token_store is not None
        assert await token_store.get_token() is None

    @pytest.mark.asyncio
    async def test_authorize_client_credentials(self, config: OAuthClientConfig, metadata: OAuthServerMetadata) -> None:
        provider = OAuthClientProvider(config, metadata)
        with patch.object(provider, "_client_credentials_grant", AsyncMock()) as mock:
            await provider._authorize()
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_authorize_auth_code(self, metadata: OAuthServerMetadata) -> None:
        config_no_secret = OAuthClientConfig(
            server_url="http://localhost:8080", client_id="test-client", client_secret=None
        )
        provider = OAuthClientProvider(config_no_secret, metadata)
        with patch.object(provider, "_authorization_code_grant", AsyncMock()) as mock:
            await provider._authorize()
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_client_credentials_grant(
        self, provider: OAuthClientProvider
    ) -> None:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "cc_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        async def mock_post(*args: Any, **kwargs: Any) -> httpx.Response:
            return mock_resp

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("cscode.mcp.auth.httpx.AsyncClient", return_value=mock_client):
            result = await provider._client_credentials_grant()
            assert result.access_token == "cc_token"

    @pytest.mark.asyncio
    async def test_authorization_code_grant(
        self, config: OAuthClientConfig, metadata: OAuthServerMetadata
    ) -> None:
        config_no_secret = OAuthClientConfig(
            server_url="http://localhost:8080", client_id="test-client",
            token_store=InMemoryTokenStore(),
        )
        provider = OAuthClientProvider(
            config_no_secret, metadata,
            callback_handler=AsyncMock(
                return_value={"code": "auth_code", "state": "fixed-state"}
            ),
        )

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "ac_token",
            "token_type": "Bearer",
        }

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        # Make secrets deterministic for state matching
        with (
            patch("cscode.mcp.auth.httpx.AsyncClient", return_value=mock_client),
            patch("cscode.mcp.auth.secrets.token_urlsafe", return_value="fixed-state"),
        ):
            result = await provider._authorization_code_grant()
            assert result.access_token == "ac_token"

    @pytest.mark.asyncio
    async def test_authorization_code_grant_state_mismatch(
        self, config: OAuthClientConfig, metadata: OAuthServerMetadata
    ) -> None:
        config_no_secret = OAuthClientConfig(
            server_url="http://localhost:8080", client_id="test-client",
            token_store=InMemoryTokenStore(),
        )
        provider = OAuthClientProvider(
            config_no_secret, metadata,
            callback_handler=AsyncMock(
                return_value={"code": "auth_code", "state": "wrong-state"}
            ),
        )

        with patch("cscode.mcp.auth.secrets.token_urlsafe", return_value="expected-state"):
            with pytest.raises(ValueError, match="State mismatch"):
                await provider._authorization_code_grant()

    @pytest.mark.asyncio
    async def test_refresh_token(self, provider: OAuthClientProvider) -> None:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "refreshed_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("cscode.mcp.auth.httpx.AsyncClient", return_value=mock_client):
            result = await provider._refresh_token("old_refresh")
            assert result.access_token == "refreshed_token"

    def test_sha256_b64(self) -> None:
        result = OAuthClientProvider._sha256_b64("test_verifier")
        assert isinstance(result, str)
        assert len(result) > 0
        # Deterministic
        assert OAuthClientProvider._sha256_b64("test_verifier") == result


# ─── MCPOAuthClient ─────────────────────────────────────────────────

class TestMCPOAuthClient:
    @pytest.mark.asyncio
    async def test_aenter_creates_client(
        self, token: OAuthToken, provider: OAuthClientProvider
    ) -> None:
        with patch.object(provider, "get_token", AsyncMock(return_value=token)):
            async with MCPOAuthClient("http://localhost:8080", provider) as client:
                assert client._http_client is not None
                assert client.server_url == "http://localhost:8080"

    @pytest.mark.asyncio
    async def test_aexit_closes_client(
        self, token: OAuthToken, provider: OAuthClientProvider
    ) -> None:
        with patch.object(provider, "get_token", AsyncMock(return_value=token)):
            client = MCPOAuthClient("http://localhost:8080", provider)
            async with client:
                pass
            assert client._http_client is None

    @pytest.mark.asyncio
    async def test_request(
        self, token: OAuthToken, provider: OAuthClientProvider
    ) -> None:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"tools": []}}

        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(return_value=mock_resp)

        client = MCPOAuthClient("http://localhost:8080", provider)
        client._http_client = mock_http

        result = await client.request({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        assert result == {"result": {"tools": []}}
        mock_http.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_request_401_retry(
        self, token: OAuthToken, provider: OAuthClientProvider
    ) -> None:
        # First response 401, second succeeds
        resp_401 = MagicMock(spec=httpx.Response)
        resp_401.status_code = 401

        resp_ok = MagicMock(spec=httpx.Response)
        resp_ok.status_code = 200
        resp_ok.json.return_value = {"result": "ok"}

        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(side_effect=[resp_401, resp_ok])
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        client = MCPOAuthClient("http://localhost:8080", provider)
        client._http_client = mock_http

        with (
            patch.object(provider, "get_token", AsyncMock(return_value=token)),
            patch("cscode.mcp.auth.httpx.AsyncClient", return_value=mock_http),
        ):
            result = await client.request({"jsonrpc": "2.0", "id": 1, "method": "ping"})

        assert result == {"result": "ok"}
        assert mock_http.post.call_count == 2

    @pytest.mark.asyncio
    async def test_list_tools(
        self, token: OAuthToken, provider: OAuthClientProvider
    ) -> None:
        client = MCPOAuthClient("http://localhost:8080", provider)
        with patch.object(client, "request", AsyncMock(return_value={
            "result": {"tools": [{"name": "read", "description": "Read files"}]}
        })):
            tools = await client.list_tools()
            assert len(tools) == 1
            assert tools[0]["name"] == "read"

    @pytest.mark.asyncio
    async def test_call_tool(
        self, token: OAuthToken, provider: OAuthClientProvider
    ) -> None:
        client = MCPOAuthClient("http://localhost:8080", provider)
        with patch.object(client, "request", AsyncMock(return_value={
            "result": {"content": "file content"}
        })):
            result = await client.call_tool("read", {"path": "/tmp/test"})
            assert result == {"content": "file content"}


# ─── discover_oauth_metadata ────────────────────────────────────────

class TestDiscoverOAuthMetadata:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "authorization_endpoint": "http://localhost:8080/auth",
            "token_endpoint": "http://localhost:8080/token",
            "issuer": "http://localhost:8080",
            "introspection_endpoint": "http://localhost:8080/introspect",
        }

        # First call returns protected resource metadata with authorization_servers
        protected_resp = MagicMock(spec=httpx.Response)
        protected_resp.status_code = 200
        protected_resp.json.return_value = {
            "authorization_servers": ["http://localhost:8080"]
        }

        # Mock chain: first .get() for protected resource, second for discovery
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[protected_resp, mock_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("cscode.mcp.auth.httpx.AsyncClient", return_value=mock_client):
            result = await discover_oauth_metadata("http://localhost:8080")
            assert result is not None
            assert result.authorization_endpoint == "http://localhost:8080/auth"
            assert result.token_endpoint == "http://localhost:8080/token"
            assert result.issuer == "http://localhost:8080"

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self) -> None:
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Not found"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("cscode.mcp.auth.httpx.AsyncClient", return_value=mock_client):
            result = await discover_oauth_metadata("http://localhost:8080")
            assert result is None

    @pytest.mark.asyncio
    async def test_no_authorization_servers(self) -> None:
        protected_resp = MagicMock(spec=httpx.Response)
        protected_resp.status_code = 200
        protected_resp.json.return_value = {}  # no authorization_servers

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=protected_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("cscode.mcp.auth.httpx.AsyncClient", return_value=mock_client):
            result = await discover_oauth_metadata("http://localhost:8080")
            assert result is None

    @pytest.mark.asyncio
    async def test_discovery_fallback(self) -> None:
        """Should try second discovery URL if first fails."""
        protected_resp = MagicMock(spec=httpx.Response)
        protected_resp.status_code = 200
        protected_resp.json.return_value = {
            "authorization_servers": ["http://localhost:8080"]
        }

        fail_resp = MagicMock(spec=httpx.Response)
        fail_resp.status_code = 404
        fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=fail_resp
        )

        ok_resp = MagicMock(spec=httpx.Response)
        ok_resp.status_code = 200
        ok_resp.json.return_value = {
            "authorization_endpoint": "http://localhost:8080/auth",
            "token_endpoint": "http://localhost:8080/token",
        }

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[protected_resp, fail_resp, ok_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("cscode.mcp.auth.httpx.AsyncClient", return_value=mock_client):
            result = await discover_oauth_metadata("http://localhost:8080")
            assert result is not None
            assert result.token_endpoint == "http://localhost:8080/token"
