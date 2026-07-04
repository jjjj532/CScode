from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cscode.mcp.auth import (
    InMemoryTokenStore,
    OAuthClientConfig,
    OAuthClientProvider,
    OAuthServerMetadata,
    OAuthToken,
)


class TestOAuthCallbackFlow:
    """Test the OAuth callback flow end-to-end."""

    @pytest.fixture
    def config(self) -> OAuthClientConfig:
        return OAuthClientConfig(
            server_url="https://mcp.example.com",
            client_id="test-client",
        )

    @pytest.fixture
    def metadata(self) -> OAuthServerMetadata:
        return OAuthServerMetadata(
            authorization_endpoint="https://auth.example.com/auth",
            token_endpoint="https://auth.example.com/token",
        )

    async def test_token_storage_persists_after_callback(self) -> None:
        """Verify token is stored after OAuth callback completes."""
        store = InMemoryTokenStore()
        config = OAuthClientConfig(
            server_url="https://mcp.example.com",
            token_store=store,
        )
        config.client_id = "test-client"
        metadata = OAuthServerMetadata(
            authorization_endpoint="https://auth.example.com/auth",
            token_endpoint="https://auth.example.com/token",
        )

        redirects: list[str] = []

        async def mock_callback() -> dict[str, str]:
            return {"code": "auth_code_xyz", "state": "test_state"}

        provider = OAuthClientProvider(
            config=config,
            metadata=metadata,
            redirect_handler=lambda url: redirects.append(url),
            callback_handler=mock_callback,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "final_token",
            "refresh_token": "refresh_xyz",
            "expires_in": 3600,
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            with patch("secrets.token_urlsafe") as mock_secret:
                mock_secret.side_effect = ["test_state", "test_code_verifier_32_chars_long!!"]
                token = await provider.get_token()

        assert token.access_token == "final_token"
        # Verify token is stored
        stored = await store.get_token()
        assert stored is not None
        assert stored.access_token == "final_token"
        assert stored.refresh_token == "refresh_xyz"


class TestTokenRefresh:
    """Test token refresh mechanism."""

    async def test_refresh_uses_refresh_token(self) -> None:
        """Verify token refresh uses the refresh_token grant."""
        store = InMemoryTokenStore()
        expired = OAuthToken(
            access_token="old_token",
            refresh_token="refresh_me",
            expires_in=1,
            acquired_at=0,
        )
        await store.set_token(expired)

        config = OAuthClientConfig(
            server_url="https://mcp.example.com",
            token_store=store,
        )
        metadata = OAuthServerMetadata(
            authorization_endpoint="https://auth.example.com/auth",
            token_endpoint="https://auth.example.com/token",
        )

        provider = OAuthClientProvider(config=config, metadata=metadata)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "refreshed_token",
            "expires_in": 3600,
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            token = await provider.get_token()

        assert token.access_token == "refreshed_token"
        # Verify refresh_token grant was used
        args, kwargs = mock_post.call_args
        assert kwargs["data"]["grant_type"] == "refresh_token"
        assert kwargs["data"]["refresh_token"] == "refresh_me"

        # Verify store was updated
        stored = await store.get_token()
        assert stored is not None
        assert stored.access_token == "refreshed_token"

    async def test_client_credentials_grant(self) -> None:
        """Verify client credentials grant works for machine-to-machine auth."""
        store = InMemoryTokenStore()
        config = OAuthClientConfig(
            server_url="https://mcp.example.com",
            client_id="svc-account",
            client_secret="svc-secret",
            token_store=store,
        )
        metadata = OAuthServerMetadata(
            authorization_endpoint="https://auth.example.com/auth",
            token_endpoint="https://auth.example.com/token",
        )

        provider = OAuthClientProvider(config=config, metadata=metadata)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "client_cred_token",
            "expires_in": 3600,
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            token = await provider.get_token()

        assert token.access_token == "client_cred_token"
        # Verify client_credentials grant
        args, kwargs = mock_post.call_args
        assert kwargs["data"]["grant_type"] == "client_credentials"
        assert kwargs["data"]["client_id"] == "svc-account"
        assert kwargs["data"]["client_secret"] == "svc-secret"


class TestAuthCallbackEndpoint:
    """Test the OAuth callback HTTP endpoint."""

    def test_callback_endpoint_registered(self) -> None:
        """Verify the /api/auth/callback route is registered on the server app."""
        from cscode.server.app import api_router
        routes = [r.path for r in api_router.routes]
        assert "/api/auth/callback" in routes

    def test_token_endpoint_registered(self) -> None:
        """Verify the /api/auth/token route is registered."""
        from cscode.server.app import api_router
        routes = [r.path for r in api_router.routes]
        assert "/api/auth/token" in routes
