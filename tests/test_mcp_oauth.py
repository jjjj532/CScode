from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from cscode.mcp.auth import (
    FileTokenStore,
    InMemoryTokenStore,
    OAuthClientConfig,
    OAuthClientProvider,
    OAuthServerMetadata,
    OAuthToken,
    discover_oauth_metadata,
)


class TestOAuthToken:
    def test_create_token(self) -> None:
        token = OAuthToken(access_token="abc123")
        assert token.access_token == "abc123"
        assert token.token_type == "Bearer"
        assert token.is_expired is False

    def test_expired_token(self) -> None:
        token = OAuthToken(access_token="abc", expires_in=1, acquired_at=time.time() - 120)
        assert token.is_expired is True

    def test_no_expiry(self) -> None:
        token = OAuthToken(access_token="abc", expires_in=None)
        assert token.is_expired is False

    def test_from_dict(self) -> None:
        data = {
            "access_token": "abc",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "ref1",
            "scope": "read write",
        }
        token = OAuthToken.from_dict(data)
        assert token.access_token == "abc"
        assert token.refresh_token == "ref1"
        assert token.scope == "read write"

    def test_to_dict(self) -> None:
        token = OAuthToken(
            access_token="abc",
            token_type="Bearer",
            expires_in=3600,
            refresh_token="ref1",
            scope="read",
        )
        d = token.to_dict()
        assert d["access_token"] == "abc"
        assert d["refresh_token"] == "ref1"
        assert d["expires_in"] == 3600

    def test_roundtrip(self) -> None:
        original = OAuthToken(access_token="tok", refresh_token="ref")
        d = original.to_dict()
        restored = OAuthToken.from_dict(d)
        assert restored.access_token == original.access_token
        assert restored.refresh_token == original.refresh_token


class TestInMemoryTokenStore:
    @pytest.fixture
    def store(self) -> InMemoryTokenStore:
        return InMemoryTokenStore()

    async def test_get_set(self, store: InMemoryTokenStore) -> None:
        token = OAuthToken(access_token="abc")
        await store.set_token(token)
        retrieved = await store.get_token()
        assert retrieved is not None
        assert retrieved.access_token == "abc"

    async def test_get_empty(self, store: InMemoryTokenStore) -> None:
        result = await store.get_token()
        assert result is None

    async def test_clear(self, store: InMemoryTokenStore) -> None:
        await store.set_token(OAuthToken(access_token="abc"))
        await store.clear_token()
        assert await store.get_token() is None


class TestFileTokenStore:
    @pytest.fixture
    def tmp_path(self, tmp_path: Path) -> Path:
        return tmp_path

    async def test_get_set(self, tmp_path: Path) -> None:
        store = FileTokenStore(tmp_path / "token.json")
        token = OAuthToken(access_token="abc")
        await store.set_token(token)
        assert (tmp_path / "token.json").exists()
        retrieved = await store.get_token()
        assert retrieved is not None
        assert retrieved.access_token == "abc"

    async def test_get_empty(self, tmp_path: Path) -> None:
        store = FileTokenStore(tmp_path / "nonexistent.json")
        result = await store.get_token()
        assert result is None

    async def test_clear(self, tmp_path: Path) -> None:
        store = FileTokenStore(tmp_path / "token.json")
        await store.set_token(OAuthToken(access_token="abc"))
        await store.clear_token()
        assert not (tmp_path / "token.json").exists()

    async def test_invalid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "token.json"
        p.write_text("invalid json")
        store = FileTokenStore(p)
        result = await store.get_token()
        assert result is None


class TestOAuthClientProvider:
    @pytest.fixture
    def config(self) -> OAuthClientConfig:
        return OAuthClientConfig(server_url="https://mcp.example.com")

    @pytest.fixture
    def metadata(self) -> OAuthServerMetadata:
        return OAuthServerMetadata(
            authorization_endpoint="https://auth.example.com/auth",
            token_endpoint="https://auth.example.com/token",
        )

    async def test_client_credentials_grant(self, config: OAuthClientConfig, metadata: OAuthServerMetadata) -> None:
        config.client_id = "my-client"
        config.client_secret = "my-secret"
        provider = OAuthClientProvider(config=config, metadata=metadata)

        from unittest.mock import MagicMock

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "tok123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            token = await provider.get_token()

        assert token.access_token == "tok123"
        # Verify the token endpoint was called
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["data"]["grant_type"] == "client_credentials"

    async def test_refresh_expired(self, config: OAuthClientConfig, metadata: OAuthServerMetadata) -> None:
        from unittest.mock import MagicMock

        expired = OAuthToken(
            access_token="old",
            refresh_token="ref1",
            expires_in=1,
            acquired_at=time.time() - 120,
        )
        await config.token_store.set_token(expired)  # type: ignore[union-attr]

        provider = OAuthClientProvider(config=config, metadata=metadata)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "refreshed", "expires_in": 3600}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            token = await provider.get_token()

        assert token.access_token == "refreshed"
        # Verify refresh_token grant was used
        args, kwargs = mock_post.call_args
        assert kwargs["data"]["grant_type"] == "refresh_token"
        assert kwargs["data"]["refresh_token"] == "ref1"

    async def test_clear_auth(self, config: OAuthClientConfig, metadata: OAuthServerMetadata) -> None:
        await config.token_store.set_token(OAuthToken(access_token="abc"))  # type: ignore[union-attr]
        provider = OAuthClientProvider(config=config, metadata=metadata)
        await provider.clear_auth()
        assert await config.token_store.get_token() is None  # type: ignore[union-attr]

    async def test_authorization_code_grant(self, config: OAuthClientConfig, metadata: OAuthServerMetadata) -> None:
        """Test browser-based flow with mock redirect/callback."""
        from unittest.mock import MagicMock

        redirects: list[str] = []

        async def mock_callback() -> dict[str, str]:
            # Simulate user pasting callback params
            return {"code": "auth_code_123", "state": "test_state"}

        provider = OAuthClientProvider(
            config=config,
            metadata=metadata,
            redirect_handler=lambda url: redirects.append(url),
            callback_handler=mock_callback,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "auth_tok", "expires_in": 3600}

        # Patch the state generation to be deterministic
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            # We need to handle state mismatch. Let's patch secrets too.
            with patch("secrets.token_urlsafe") as mock_secret:
                mock_secret.side_effect = ["test_state", "test_code_verifier_32_bytes_long!!"]
                token = await provider.get_token()

        assert token.access_token == "auth_tok"
        assert len(redirects) == 1
        assert "authorization_endpoint" in redirects[0] or "auth.example.com" in redirects[0]


class TestDiscoverOAuthMetadata:
    async def test_discovery_success(self) -> None:
        from unittest.mock import MagicMock

        mock_meta = MagicMock()
        mock_meta.status_code = 200
        mock_meta.json.return_value = {
            "authorization_servers": ["https://auth.example.com"],
        }

        mock_disc = MagicMock()
        mock_disc.status_code = 200
        mock_disc.json.return_value = {
            "authorization_endpoint": "https://auth.example.com/auth",
            "token_endpoint": "https://auth.example.com/token",
            "issuer": "https://auth.example.com",
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [mock_meta, mock_disc]
            result = await discover_oauth_metadata("https://mcp.example.com")

        assert result is not None
        assert result.authorization_endpoint == "https://auth.example.com/auth"
        assert result.token_endpoint == "https://auth.example.com/token"

    async def test_discovery_no_auth_servers(self) -> None:
        from unittest.mock import MagicMock

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"authorization_servers": []}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            result = await discover_oauth_metadata("https://mcp.example.com")

        assert result is None

    async def test_discovery_http_error(self) -> None:
        import httpx

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPError("connection failed")
            result = await discover_oauth_metadata("https://mcp.example.com")

        assert result is None
