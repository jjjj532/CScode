"""Tests for GitHub Copilot Provider (providers/copilot.py).

Tests verify:
- CopilotAuth token management and expiry
- CopilotOAuth device code flow
- CopilotProvider chat completion
- Error handling (auth, rate limits)
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cscode.providers.copilot import (
    COPILOT_API_URL,
    COPILOT_AUTH_URL,
    COPILOT_TOKEN_URL,
    CopilotAuth,
    CopilotOAuth,
    CopilotProvider,
    create_copilot_provider,
)


class TestCopilotAuth:
    """CopilotAuth token management."""

    def test_create_with_token(self) -> None:
        auth = CopilotAuth(access_token="ghu_test_token")
        assert auth.access_token == "ghu_test_token"
        assert auth.refresh_token is None
        assert auth.expires_at is None

    def test_create_with_refresh(self) -> None:
        auth = CopilotAuth(
            access_token="ghu_test",
            refresh_token="ghr_test",
            expires_at=time.time() + 3600,
        )
        assert auth.access_token == "ghu_test"
        assert auth.refresh_token == "ghr_test"
        assert auth.expires_at is not None

    def test_is_expired_no_expiry(self) -> None:
        auth = CopilotAuth(access_token="test")
        assert auth.is_expired() is False  # No expiry = always valid

    def test_is_expired_with_valid_expiry(self) -> None:
        auth = CopilotAuth(
            access_token="test",
            expires_at=time.time() + 3600,
        )
        assert auth.is_expired() is False

    def test_is_expired_past_expiry(self) -> None:
        auth = CopilotAuth(
            access_token="test",
            expires_at=time.time() - 10,
        )
        assert auth.is_expired() is True

    def test_is_expired_within_grace_period(self) -> None:
        """Should expire 60 seconds before actual expiry (buffer)."""
        auth = CopilotAuth(
            access_token="test",
            expires_at=time.time() + 30,  # 30s left, but buffer is 60s
        )
        assert auth.is_expired() is True

    def test_headers_no_token_raises(self) -> None:
        auth = CopilotAuth()
        with pytest.raises(ValueError, match="No access token"):
            auth.headers()

    def test_headers_with_token(self) -> None:
        auth = CopilotAuth(access_token="ghu_test")
        headers = auth.headers()
        assert headers["Authorization"] == "Bearer ghu_test"
        assert "Accept" in headers
        assert "X-GitHub-Api-Version" in headers

    def test_headers_accept_header(self) -> None:
        auth = CopilotAuth(access_token="test")
        headers = auth.headers()
        assert "application/vnd.github.copilot-chat+json" in headers["Accept"]


class TestCopilotOAuth:
    """Copilot OAuth device code flow."""

    @pytest.mark.asyncio
    async def test_get_device_code(self) -> None:
        """Should return device code from GitHub."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "device_code": "abc123",
            "user_code": "ABCD-1234",
            "verification_uri": "https://github.com/login/device",
            "interval": 5,
        }

        async with httpx.AsyncClient() as client:
            with patch.object(client, "post", AsyncMock(return_value=mock_response)):
                result = await CopilotOAuth.get_device_code(client=client)
                assert result["device_code"] == "abc123"
                assert result["user_code"] == "ABCD-1234"
                assert "verification_uri" in result

    @pytest.mark.asyncio
    async def test_get_device_code_http_error(self) -> None:
        """Should propagate HTTP errors."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad request", request=MagicMock(), response=mock_response
        )

        async with httpx.AsyncClient() as client:
            with patch.object(client, "post", AsyncMock(return_value=mock_response)):
                with pytest.raises(httpx.HTTPStatusError):
                    await CopilotOAuth.get_device_code(client=client)

    @pytest.mark.asyncio
    async def test_poll_for_token_success(self) -> None:
        """Should poll and return auth on success."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "ghu_new_token",
            "refresh_token": "ghr_new_refresh",
            "expires_in": 28800,
        }

        async with httpx.AsyncClient() as client:
            with patch.object(client, "post", AsyncMock(return_value=mock_response)):
                auth = await CopilotOAuth.poll_for_token(
                    device_code="abc123",
                    client=client,
                )
                assert isinstance(auth, CopilotAuth)
                assert auth.access_token == "ghu_new_token"
                assert auth.refresh_token == "ghr_new_refresh"

    @pytest.mark.asyncio
    async def test_poll_for_token_authorization_pending(self) -> None:
        """Should return None when still pending (not an error)."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": "authorization_pending",
        }

        async with httpx.AsyncClient() as client:
            with patch.object(client, "post", AsyncMock(return_value=mock_response)):
                auth = await CopilotOAuth.poll_for_token(
                    device_code="abc123",
                    client=client,
                )
                assert auth is None


class TestCopilotProvider:
    """CopilotProvider chat completion."""

    @pytest.mark.asyncio
    async def test_get_models(self) -> None:
        """Should fetch available models."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "gpt-4o"}, {"name": "gpt-4o-mini"}],
        }

        auth = CopilotAuth(access_token="ghu_test")
        provider = CopilotProvider(auth=auth)

        with patch.object(provider.client, "get", AsyncMock(return_value=mock_response)):
            models = await provider.get_models()
            assert len(models) == 2
            assert models[0]["name"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_get_models_unauthorized(self) -> None:
        """Should raise on 401."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401

        auth = CopilotAuth(access_token="ghu_bad")
        provider = CopilotProvider(auth=auth)

        with patch.object(provider.client, "get", AsyncMock(return_value=mock_response)):
            with pytest.raises(ValueError, match="Unauthorized"):
                await provider.get_models()

    @pytest.mark.asyncio
    async def test_chat_completion(self) -> None:
        """Should send chat request and return response."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from Copilot!"}}],
            "model": "gpt-4o",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        auth = CopilotAuth(access_token="ghu_test")
        provider = CopilotProvider(auth=auth)

        with patch.object(provider.client, "post", AsyncMock(return_value=mock_response)):
            result = await provider.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model="gpt-4o",
            )
            assert result["choices"][0]["message"]["content"] == "Hello from Copilot!"
            assert result["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_chat_with_expired_token(self) -> None:
        """Should raise on expired token."""
        auth = CopilotAuth(
            access_token="ghu_expired",
            expires_at=time.time() - 100,
        )
        provider = CopilotProvider(auth=auth)

        with pytest.raises(ValueError, match="Token expired"):
            await provider.chat(messages=[{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_aclose(self) -> None:
        """Should close the HTTP client."""
        auth = CopilotAuth(access_token="test")
        provider = CopilotProvider(auth=auth)
        await provider.aclose()
        # After close, client should not accept new requests
        with pytest.raises(Exception):
            await provider.client.get(COPILOT_API_URL)


class TestFactory:
    """create_copilot_provider factory."""

    def test_create_from_token(self) -> None:
        provider = create_copilot_provider("ghu_test_token")
        assert isinstance(provider, CopilotProvider)
        assert provider.auth.access_token == "ghu_test_token"

    def test_create_provider_has_async_client(self) -> None:
        provider = create_copilot_provider("ghu_test")
        assert isinstance(provider.client, httpx.AsyncClient)
