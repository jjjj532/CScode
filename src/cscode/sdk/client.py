"""Async HTTP client for the CScode REST API.

Usage:
    async with CScodeClient(base_url="http://127.0.0.1:8080", api_key="...") as client:
        health = await client.health()
        sessions = await client.list_sessions()
        reply = await client.chat("Hello!")
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import httpx

from cscode.sdk.models import (
    ChatRequest,
    ChatResponse,
    ConfigResponse,
    ConfigSetRequest,
    CredentialInfo,
    CScodeClientError,
    HealthResponse,
    SessionInfo,
    SessionListResponse,
    VerificationReportResponse,
    WorkspaceInfo,
)


class CScodeClient:
    """Async HTTP client for CScode's REST API.

    All public methods raise ``CScodeClientError`` on HTTP errors or
    connection failures.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        api_key: str | None = None,
        timeout: float = 30.0,
        _transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        headers: dict[str, str] = {
            "content-type": "application/json",
            "accept": "application/json",
        }
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"
        transport: httpx.AsyncBaseTransport | None = cast(
            "httpx.AsyncBaseTransport | None", _transport
        )
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout),
            transport=transport,
        )

    async def __aenter__(self) -> CScodeClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.aclose()

    async def close(self) -> None:
        await self._client.aclose()

    # ── low-level helpers ───────────────────────────────────────────

    async def _get(self, path: str) -> Any:
        try:
            resp = await self._client.get(path)
        except httpx.RequestError as e:
            raise CScodeClientError(str(e)) from e
        if resp.is_error:
            raise CScodeClientError.from_response(resp)
        try:
            return resp.json()
        except Exception:
            raise CScodeClientError("invalid JSON response", status_code=resp.status_code)

    async def _post(
        self, path: str, json: dict[str, Any] | None = None
    ) -> Any:
        try:
            resp = await self._client.post(path, json=json)
        except httpx.RequestError as e:
            raise CScodeClientError(str(e)) from e
        if resp.is_error:
            raise CScodeClientError.from_response(resp)
        return resp.json()

    async def _patch(self, path: str, json: dict[str, Any]) -> Any:
        try:
            resp = await self._client.patch(path, json=json)
        except httpx.RequestError as e:
            raise CScodeClientError(str(e)) from e
        if resp.is_error:
            raise CScodeClientError.from_response(resp)
        return resp.json()

    async def _delete(self, path: str) -> None:
        try:
            resp = await self._client.delete(path)
        except httpx.RequestError as e:
            raise CScodeClientError(str(e)) from e
        if resp.is_error:
            raise CScodeClientError.from_response(resp)

    async def _post_stream(
        self, path: str, json: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        try:
            async with self._client.stream("POST", path, json=json) as resp:
                if resp.is_error:
                    body = await resp.aread()
                    try:
                        err_data: dict[str, Any] = resp.json()
                    except Exception:
                        err_data = {"detail": body.decode()}
                    raise CScodeClientError(
                        status_code=resp.status_code,
                        message=err_data.get("detail", str(resp.status_code)),
                        body=err_data,
                    )
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if line.startswith("data: "):
                        payload = line[len("data: "):]
                        if payload:
                            import json as _json

                            try:
                                yield _json.loads(payload)
                            except _json.JSONDecodeError:
                                yield {"type": "raw", "data": payload}
                        else:
                            yield {"type": "done"}
        except httpx.RequestError as e:
            raise CScodeClientError(str(e)) from e

    # ── Health ──────────────────────────────────────────────────────

    async def health(self) -> HealthResponse:
        data = await self._get("/api/health")
        return HealthResponse.from_dict(data)

    # ── Sessions ────────────────────────────────────────────────────

    async def list_sessions(
        self, limit: int = 50, offset: int = 0
    ) -> SessionListResponse:
        data = await self._get(f"/api/sessions?limit={limit}&offset={offset}")
        return SessionListResponse.from_dict(data)

    async def create_session(
        self,
        title: str = "",
        provider: str | None = None,
        model: str | None = None,
    ) -> SessionInfo:
        body: dict[str, Any] = {"title": title}
        if provider:
            body["provider"] = provider
        if model:
            body["model"] = model
        data = await self._post("/api/sessions", json=body)
        return SessionInfo.from_dict(data)

    async def get_session(self, session_id: str) -> SessionInfo:
        data = await self._get(f"/api/sessions/{session_id}")
        return SessionInfo.from_dict(data)

    async def delete_session(self, session_id: str) -> None:
        await self._delete(f"/api/sessions/{session_id}")

    async def stop_session(self, session_id: str) -> None:
        await self._post(f"/api/sessions/{session_id}/stop")

    async def export_session(self, session_id: str) -> dict[str, Any]:
        data = await self._post(f"/api/sessions/{session_id}/export")
        return cast("dict[str, Any]", data)

    # ── Chat ────────────────────────────────────────────────────────

    async def chat(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
    ) -> ChatResponse:
        req = ChatRequest(prompt=prompt, session_id=session_id, model=model)
        data = await self._post("/api/chat", json=req.to_dict())
        return ChatResponse.from_dict(data)

    async def chat_stream(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        req = ChatRequest(prompt=prompt, session_id=session_id, model=model)
        async for event in self._post_stream("/api/chat/stream", json=req.to_dict()):
            yield event

    # ── Config ──────────────────────────────────────────────────────

    async def get_config(self) -> ConfigResponse:
        data = await self._get("/api/config")
        return ConfigResponse.from_dict(data)

    async def set_config(self, config: ConfigSetRequest) -> None:
        await self._post("/api/config", json=config.to_dict())

    # ── Workspaces ──────────────────────────────────────────────────

    async def list_workspaces(self) -> list[WorkspaceInfo]:
        data = await self._get("/api/workspaces")
        items: list[Any] = data if isinstance(data, list) else []
        return [WorkspaceInfo.from_dict(w) for w in items]

    async def create_workspace(
        self, name: str, path: str
    ) -> WorkspaceInfo:
        data = await self._post(
            "/api/workspaces",
            json={"name": name, "path": path},
        )
        return WorkspaceInfo.from_dict(data)

    async def get_workspace(self, workspace_id: str) -> WorkspaceInfo:
        data = await self._get(f"/api/workspaces/{workspace_id}")
        return WorkspaceInfo.from_dict(data)

    # ── Credentials ─────────────────────────────────────────────────

    async def list_credentials(self) -> list[CredentialInfo]:
        data = await self._get("/api/credentials")
        items: list[Any] = data if isinstance(data, list) else data.get("credentials", [])
        return [CredentialInfo.from_dict(c) for c in items]

    async def create_credential(
        self, name: str, value: str, provider: str, type_: str = "api_key"
    ) -> CredentialInfo:
        data = await self._post(
            "/api/credentials",
            json={"name": name, "value": value, "provider": provider, "type": type_},
        )
        return CredentialInfo.from_dict(data)

    # ── Verification ────────────────────────────────────────────────

    async def get_verification_report(
        self, session_id: str
    ) -> VerificationReportResponse:
        data = await self._get(
            f"/api/sessions/{session_id}/verification-report"
        )
        return VerificationReportResponse.from_dict(data)



