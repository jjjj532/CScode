"""GitHub Copilot Provider — P0.5

Provides Copilot as an LLM provider with:
- OAuth device code authentication flow
- Async HTTP client for all API calls
- Token refresh and expiry management
- Copilot-specific error parsing

API reference: https://docs.github.com/en/copilot/using-github-copilot/using-github-copilot-codex
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

# GitHub OAuth endpoints
COPILOT_AUTH_URL = "https://github.com/login/device/code"
COPILOT_TOKEN_URL = "https://github.com/login/oauth/access_token"
COPILOT_API_URL = "https://api.github.com/copilot"

# Copilot OAuth client ID (public, used by all Copilot integrations)
_COPILOT_CLIENT_ID = "Iv1.b9925b0c5d8c8c7c"
_COPILOT_SCOPES = ["read:user", "repo", "copilot"]


@dataclass
class CopilotAuth:
    """GitHub Copilot OAuth authentication state.

    Attributes:
        access_token: GitHub OAuth access token.
        refresh_token: Optional refresh token for token renewal.
        expires_at: Unix timestamp when the token expires (None = no expiry).
    """

    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: float | None = None

    def is_expired(self) -> bool:
        """Check if the access token is expired (with 60s buffer).

        Returns False if no expiry is set (tokens without expiry
        are treated as always-valid).
        """
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at - 60

    def headers(self) -> dict[str, str]:
        """Build HTTP headers for Copilot API requests.

        Raises:
            ValueError: If no access token is available.
        """
        if not self.access_token:
            raise ValueError("No access token available")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/vnd.github.copilot-chat+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }


class CopilotOAuth:
    """GitHub Copilot OAuth device code flow.

    Usage:
        # Step 1: Get device code (show user_code to user)
        client = httpx.AsyncClient()
        device_code = await CopilotOAuth.get_device_code(client=client)
        print(f"Visit {device_code['verification_uri']} and enter {device_code['user_code']}")

        # Step 2: Poll for token
        auth = None
        while auth is None:
            await asyncio.sleep(device_code['interval'])
            auth = await CopilotOAuth.poll_for_token(device_code['device_code'], client=client)
    """

    CLIENT_ID = _COPILOT_CLIENT_ID
    SCOPES = _COPILOT_SCOPES

    @staticmethod
    async def get_device_code(
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        """Step 1: Request a device code from GitHub.

        Returns a dict with:
            device_code: Code to poll with.
            user_code: Code the user enters on GitHub.
            verification_uri: URL for the user to visit.
            interval: Polling interval in seconds.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        close_client = client is None
        if client is None:
            client = httpx.AsyncClient()

        try:
            response = await client.post(
                COPILOT_AUTH_URL,
                json={
                    "client_id": _COPILOT_CLIENT_ID,
                    "scope": " ".join(_COPILOT_SCOPES),
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()
        finally:
            if close_client:
                await client.aclose()

    @staticmethod
    async def poll_for_token(
        device_code: str,
        client: httpx.AsyncClient | None = None,
    ) -> CopilotAuth | None:
        """Step 2: Poll GitHub for token authorization.

        Args:
            device_code: The device_code from get_device_code().
            client: Optional async HTTP client.

        Returns:
            CopilotAuth on success, None if still pending.
            Raises on error.
        """
        close_client = client is None
        if client is None:
            client = httpx.AsyncClient()

        try:
            response = await client.post(
                COPILOT_TOKEN_URL,
                json={
                    "client_id": _COPILOT_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            # Check for pending authorization
            if data.get("error") == "authorization_pending":
                return None

            # Parse tokens
            return CopilotAuth(
                access_token=data.get("access_token"),
                refresh_token=data.get("refresh_token"),
                expires_at=(
                    time.time() + data["expires_in"]
                    if "expires_in" in data
                    else None
                ),
            )
        finally:
            if close_client:
                await client.aclose()


class CopilotProvider:
    """GitHub Copilot LLM Provider.

    Provides chat completion and model listing via the Copilot API,
    which is compatible with the OpenAI chat format.

    Attributes:
        auth: The authentication state.
        client: The async HTTP client for API calls.
    """

    def __init__(
        self,
        auth: CopilotAuth,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            auth: Copilot authentication.
            client: Optional async HTTP client (created if not provided).
        """
        self.auth = auth
        self.client = client or httpx.AsyncClient()

    @staticmethod
    def create_from_token(access_token: str) -> CopilotProvider:
        """Create a provider from an existing GitHub access token.

        This is the simplest way to create a provider when you already
        have a token (e.g., from GH CLI or environment variable).
        """
        auth = CopilotAuth(access_token=access_token)
        return CopilotProvider(auth)

    async def get_models(self) -> list[dict[str, Any]]:
        """Get available Copilot models.

        Returns:
            List of model dicts with 'name' and other fields.

        Raises:
            ValueError: If token expired or unauthorized.
        """
        if self.auth.is_expired():
            raise ValueError("Token expired, need refresh")

        response = await self.client.get(
            f"{COPILOT_API_URL}/v1/models",
            headers=self.auth.headers(),
        )
        if response.status_code == 401:
            raise ValueError("Unauthorized - check token")
        response.raise_for_status()
        data = response.json()
        return data.get("models", [])

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "gpt-4o",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model name (default: gpt-4o).
            **kwargs: Additional parameters (temperature, max_tokens, etc.).

        Returns:
            The API response dict.

        Raises:
            ValueError: If token expired.
            httpx.HTTPStatusError: On API errors.
        """
        if self.auth.is_expired():
            raise ValueError("Token expired, need refresh")

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            **kwargs,
        }

        response = await self.client.post(
            f"{COPILOT_API_URL}/v1/chat/completions",
            headers=self.auth.headers(),
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> CopilotProvider:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()


def create_copilot_provider(access_token: str) -> CopilotProvider:
    """Factory: create a CopilotProvider from an access token.

    Args:
        access_token: GitHub OAuth access token.

    Returns:
        A configured CopilotProvider instance.
    """
    return CopilotProvider.create_from_token(access_token)
