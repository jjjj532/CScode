from __future__ import annotations

from typing import Any


class CScodeClient:
    """Client for connecting to a CScode server.

    Args:
        base_url: The base URL of the CScode server (e.g. http://localhost:8000).
        api_key: API key for authentication.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def send_message(self, message: str, session_id: str | None = None) -> str:
        """Send a message to the CScode server and get a response."""
        import httpx

        body: dict[str, Any] = {"message": message}
        if session_id:
            body["session_id"] = session_id

        async with httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=120.0) as client:
            response = await client.post("/api/chat", json=body)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

    async def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions on the server."""
        import httpx

        async with httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=30.0) as client:
            response = await client.get("/api/sessions")
            response.raise_for_status()
            return response.json().get("sessions", [])

    async def health(self) -> dict[str, Any]:
        """Check server health."""
        import httpx

        async with httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=10.0) as client:
            response = await client.get("/health")
            response.raise_for_status()
            return response.json()
