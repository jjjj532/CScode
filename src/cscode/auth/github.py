from __future__ import annotations

from urllib.parse import urlencode

import httpx

from cscode.utils.logging import get_logger

logger = get_logger(__name__)

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"


class GitHubOAuth:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    def get_authorize_url(self, state: str = "", scopes: list[str] | None = None) -> str:
        if scopes is None:
            scopes = ["repo", "user"]
        params = {
            "client_id": self.client_id,
            "scope": ",".join(scopes),
            "state": state,
        }
        return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, str]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                GITHUB_TOKEN_URL,
                json={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data: dict[str, str] = response.json()
            return data
