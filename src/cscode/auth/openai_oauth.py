from __future__ import annotations

from urllib.parse import urlencode

import httpx

from cscode.utils.logging import get_logger

logger = get_logger(__name__)

OPENAI_AUTHORIZE_URL = "https://authorize.openai.com/authorize"
OPENAI_TOKEN_URL = "https://authorize.openai.com/oauth/token"


class OpenAIOAuth:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    def get_authorize_url(self, state: str = "", redirect_uri: str = "http://localhost:8080/callback") -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
        return f"{OPENAI_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str = "http://localhost:8080/callback") -> dict[str, str]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENAI_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            data: dict[str, str] = response.json()
            return data
