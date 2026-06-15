from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class ShareLinkGenerator:
    def __init__(self, base_url: str = "https://cscode.dev") -> None:
        self.base_url = base_url.rstrip("/")

    def generate(self, session_id: str, access_token: str | None = None) -> str:
        params: dict[str, str] = {}
        if access_token:
            params["token"] = access_token
        url = f"{self.base_url}/share/{session_id}"
        if params:
            url += f"?{urlencode(params)}"
        return url

    def parse(self, url: str) -> dict[str, str] | None:
        try:
            parsed = urlparse(url)
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) < 2 or path_parts[0] != "share":
                return None
            session_id = path_parts[1]
            params = parse_qs(parsed.query)
            token = params.get("token", [None])[0]
            result: dict[str, str] = {"session_id": session_id}
            if token:
                result["token"] = token
            return result
        except Exception as e:
            logger.warning("Failed to parse share link: %s", e)
            return None
