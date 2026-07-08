"""Tests for CScode Python SDK (cscode.sdk).

Covers models, client CRUD, chat, streaming, and error handling.
Uses httpx mock transport to avoid live server dependency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator
import json

import httpx
import pytest

from cscode.sdk.models import (
    HealthResponse,
    SessionInfo,
    SessionListResponse,
    ChatRequest,
    ChatResponse,
    ConfigResponse,
    ConfigSetRequest,
    WorkspaceInfo,
    WorkspaceListResponse,
    CredentialInfo,
    CredentialListResponse,
    VerificationReportResponse,
    SdkError,
    CScodeClientError,
)
from cscode.sdk.client import CScodeClient


# ── helpers ──────────────────────────────────────────────────────────

def _mock_transport(
    responses: dict[str, dict[str, Any]],
) -> httpx.MockTransport:
    """Build a MockTransport that maps (method, path) -> response dict."""
    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url.path}"
        if request.url.path.startswith("/api/chat/stream"):
            # streaming: yield SSE text lines
            body = responses.get(key, {})
            sse_data = body.get("_sse", "")
            return httpx.Response(200, text=sse_data, headers={"content-type": "text/event-stream"})
        body = responses.get(key, {})
        status = body.pop("_status", 200) if isinstance(body, dict) else 200
        return httpx.Response(status, json=body if isinstance(body, dict) else body)
    return httpx.MockTransport(handler)


def _client(responses: dict[str, Any]) -> CScodeClient:
    transport = _mock_transport(responses)
    return CScodeClient(
        base_url="http://127.0.0.1:8080",
        api_key="test-key",
        _transport=transport,
    )


# ── Models ───────────────────────────────────────────────────────────

class TestHealthResponse:
    def test_from_dict(self) -> None:
        data = {"status": "ok"}
        m = HealthResponse.from_dict(data)
        assert m.status == "ok"

    def test_from_dict_extra(self) -> None:
        data = {"status": "ok", "version": "0.3.3", "uptime": 123}
        m = HealthResponse.from_dict(data)
        assert m.status == "ok"
        assert m.version == "0.3.3"
        assert m.uptime == 123


class TestSessionInfo:
    def test_from_dict(self) -> None:
        data = {
            "id": "ses_001",
            "title": "test session",
            "provider": "openai",
            "model": "gpt-4o",
            "created_at": "2026-07-06T10:00:00",
            "updated_at": "2026-07-06T10:30:00",
        }
        m = SessionInfo.from_dict(data)
        assert m.id == "ses_001"
        assert m.title == "test session"
        assert m.provider == "openai"
        assert m.model == "gpt-4o"
        assert m.message_count == 0

    def test_from_dict_with_counts(self) -> None:
        data = {
            "id": "ses_001",
            "title": "t",
            "provider": "p",
            "model": "m",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "message_count": 5,
            "status": "active",
        }
        m = SessionInfo.from_dict(data)
        assert m.message_count == 5
        assert m.status == "active"


class TestChatRequest:
    def test_to_dict(self) -> None:
        req = ChatRequest(prompt="Hello", session_id="ses_001")
        d = req.to_dict()
        assert d["prompt"] == "Hello"
        assert d["session_id"] == "ses_001"

    def test_to_dict_minimal(self) -> None:
        req = ChatRequest(prompt="hi")
        d = req.to_dict()
        assert d["prompt"] == "hi"
        assert "session_id" not in d


class TestChatResponse:
    def test_from_dict(self) -> None:
        data = {
            "message": {"role": "assistant", "content": "Hello back"},
            "session_id": "ses_001",
        }
        m = ChatResponse.from_dict(data)
        assert m.message.role == "assistant"
        assert m.message.content == "Hello back"
        assert m.session_id == "ses_001"


class TestConfigResponse:
    def test_from_dict(self) -> None:
        data = {"provider": "openai", "model": "gpt-4o", "temperature": 0.7}
        m = ConfigResponse.from_dict(data)
        assert m.provider == "openai"
        assert m.model == "gpt-4o"
        assert m.temperature == 0.7


class TestWorkspaceInfo:
    def test_from_dict(self) -> None:
        data = {
            "id": "ws_001",
            "name": "my project",
            "path": "/home/user/project",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        m = WorkspaceInfo.from_dict(data)
        assert m.id == "ws_001"
        assert m.name == "my project"
        assert m.path == "/home/user/project"


class TestCredentialInfo:
    def test_from_dict(self) -> None:
        data = {
            "id": "cred_001",
            "name": "openai-key",
            "type": "api_key",
            "provider": "openai",
            "created_at": 1712345678.0,
            "updated_at": 1712345678.0,
        }
        m = CredentialInfo.from_dict(data)
        assert m.id == "cred_001"
        assert m.name == "openai-key"
        assert m.provider == "openai"


class TestVerificationReportResponse:
    def test_from_dict(self) -> None:
        data = {
            "session_id": "ses_001",
            "summary": {"total": 5, "passed": 3, "failed": 0, "unverified": 2},
            "verifications": [],
        }
        m = VerificationReportResponse.from_dict(data)
        assert m.session_id == "ses_001"
        assert m.summary["total"] == 5


class TestSdkError:
    def test_str(self) -> None:
        err = SdkError(status_code=404, message="Not found", body={"detail": "missing"})
        s = str(err)
        assert "404" in s
        assert "Not found" in s

    def test_from_response(self) -> None:
        resp = httpx.Response(400, json={"detail": "bad request"})
        err = SdkError.from_response(resp)
        assert err.status_code == 400
        assert "bad request" in err.body.get("detail", "")


# ── Client ───────────────────────────────────────────────────────────

class TestClientHealth:
    async def test_health_ok(self) -> None:
        client = _client({"GET /api/health": {"status": "ok", "version": "0.3.3"}})
        result = await client.health()
        assert isinstance(result, HealthResponse)
        assert result.status == "ok"
        assert result.version == "0.3.3"

    async def test_health_fails_on_error(self) -> None:
        client = _client({"GET /api/health": {"_status": 503, "detail": "not ready"}})
        with pytest.raises(CScodeClientError) as exc:
            await client.health()
        assert "503" in str(exc.value)

    async def test_health_fails_on_connection_refused(self) -> None:
        client = CScodeClient(base_url="http://127.0.0.1:1")  # unlikely port
        with pytest.raises(CScodeClientError):
            await client.health()


class TestClientSessions:
    async def test_list_sessions(self) -> None:
        data = {
            "sessions": [
                {
                    "id": "ses_001", "title": "s1",
                    "provider": "openai", "model": "gpt-4o",
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
                }
            ],
            "total": 1,
        }
        client = _client({"GET /api/sessions": data})
        result = await client.list_sessions()
        assert isinstance(result, SessionListResponse)
        assert len(result.sessions) == 1
        assert result.sessions[0].title == "s1"

    async def test_create_session(self) -> None:
        data = {
            "id": "ses_new",
            "title": "new session",
            "provider": "openai",
            "model": "gpt-4o",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        client = _client({"POST /api/sessions": data})
        result = await client.create_session()
        assert result.id == "ses_new"

    async def test_get_session(self) -> None:
        data = {
            "id": "ses_001", "title": "t",
            "provider": "p", "model": "m",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        client = _client({"GET /api/sessions/ses_001": data})
        result = await client.get_session("ses_001")
        assert result.id == "ses_001"

    async def test_delete_session(self) -> None:
        client = _client({"DELETE /api/sessions/ses_001": {"_status": 204}})
        await client.delete_session("ses_001")  # should not raise

    async def test_delete_session_not_found(self) -> None:
        client = _client({"DELETE /api/sessions/nonexistent": {"_status": 404, "detail": "not found"}})
        with pytest.raises(CScodeClientError):
            await client.delete_session("nonexistent")

    async def test_stop_session(self) -> None:
        client = _client({"POST /api/sessions/ses_001/stop": {"_status": 200}})
        await client.stop_session("ses_001")

    async def test_export_session(self) -> None:
        data = {"session": {"id": "ses_001"}, "messages": []}
        client = _client({"POST /api/sessions/ses_001/export": data})
        result = await client.export_session("ses_001")
        assert result["session"]["id"] == "ses_001"


class TestClientChat:
    async def test_chat_non_streaming(self) -> None:
        data = {
            "message": {"role": "assistant", "content": "Hello!"},
            "session_id": "ses_001",
        }
        client = _client({"POST /api/chat": data})
        result = await client.chat("Hello", session_id="ses_001")
        assert result.message.content == "Hello!"
        assert result.session_id == "ses_001"

    async def test_chat_streaming(self) -> None:
        sse = "data: {\"type\": \"text_delta\", \"delta\": \"Hel\"}\n\ndata: {\"type\": \"text_delta\", \"delta\": \"lo!\"}\n\ndata: {\"type\": \"done\"}\n\n"
        client = _client({"POST /api/chat/stream": {"_sse": sse}})
        events: list[dict[str, Any]] = []
        async for event in client.chat_stream("Hello", session_id="ses_001"):
            events.append(event)
        assert len(events) == 3
        assert events[0]["type"] == "text_delta"
        assert events[0]["delta"] == "Hel"
        assert events[2]["type"] == "done"

    async def test_chat_streaming_empty(self) -> None:
        client = _client({"POST /api/chat/stream": {"_sse": ""}})
        events: list[dict[str, Any]] = []
        async for event in client.chat_stream("Hello"):
            events.append(event)
        assert events == []

    async def test_chat_without_session(self) -> None:
        """Chat creates a new session if session_id not provided."""
        data = {
            "message": {"role": "assistant", "content": "Hello!"},
            "session_id": "ses_new",
        }
        client = _client({"POST /api/chat": data})
        result = await client.chat("Hello")
        assert result.session_id == "ses_new"


class TestClientConfig:
    async def test_get_config(self) -> None:
        data = {"provider": "openai", "model": "gpt-4o"}
        client = _client({"GET /api/config": data})
        result = await client.get_config()
        assert result.provider == "openai"

    async def test_set_config(self) -> None:
        client = _client({"POST /api/config": {"_status": 200}})
        await client.set_config(ConfigSetRequest(provider="azure"))

    async def test_set_config_invalid(self) -> None:
        client = _client({"POST /api/config": {"_status": 422, "detail": "validation error"}})
        with pytest.raises(CScodeClientError):
            await client.set_config(ConfigSetRequest(provider=""))


class TestClientWorkspace:
    async def test_list_workspaces(self) -> None:
        data = [{"id": "ws_001", "name": "p1", "path": "/p1", "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"}]
        client = _client({"GET /api/workspaces": data})
        result = await client.list_workspaces()
        assert len(result) == 1
        assert result[0].name == "p1"

    async def test_create_workspace(self) -> None:
        data = {"id": "ws_new", "name": "new", "path": "/new", "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"}
        client = _client({"POST /api/workspaces": data})
        result = await client.create_workspace(name="new", path="/new")
        assert result.id == "ws_new"

    async def test_get_workspace(self) -> None:
        data = {"id": "ws_001", "name": "p1", "path": "/p1", "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"}
        client = _client({"GET /api/workspaces/ws_001": data})
        result = await client.get_workspace("ws_001")
        assert result.id == "ws_001"


class TestClientCredentials:
    async def test_list_credentials(self) -> None:
        data = [{"id": "cred_001", "name": "my-key", "type": "api_key", "provider": "openai", "created_at": 1.0, "updated_at": 1.0}]
        client = _client({"GET /api/credentials": data})
        result = await client.list_credentials()
        assert len(result) == 1
        assert result[0].name == "my-key"

    async def test_create_credential(self) -> None:
        data = {"id": "cred_new", "name": "new-key", "type": "api_key", "provider": "azure", "created_at": 2.0, "updated_at": 2.0}
        client = _client({"POST /api/credentials": data})
        result = await client.create_credential(name="new-key", value="sk-...", provider="azure")
        assert result.id == "cred_new"


class TestClientVerification:
    async def test_verification_report(self) -> None:
        data = {
            "session_id": "ses_001",
            "summary": {"total": 2, "passed": 1, "failed": 0, "unverified": 1},
            "verifications": [
                {
                    "task_id": "t1", "tool_name": "read",
                    "status": "PASSED", "evidence": "file found",
                    "verified": 1,
                }
            ],
        }
        client = _client({"GET /api/sessions/ses_001/verification-report": data})
        result = await client.get_verification_report("ses_001")
        assert result.session_id == "ses_001"
        assert result.summary["passed"] == 1


# ── Error handling ──────────────────────────────────────────────────

class TestClientErrors:
    async def test_401_unauthorized(self) -> None:
        client = _client({"GET /api/health": {"_status": 401, "detail": "unauthorized"}})
        with pytest.raises(CScodeClientError) as exc:
            await client.health()
        assert "401" in str(exc.value)

    async def test_500_server_error(self) -> None:
        client = _client({"GET /api/sessions": {"_status": 500, "detail": "internal"}})
        with pytest.raises(CScodeClientError) as exc:
            await client.list_sessions()
        assert "500" in str(exc.value)

    async def test_invalid_json_response(self) -> None:
        """Server returns non-JSON on error."""
        transport = httpx.MockTransport(lambda _: httpx.Response(200, text="not-json"))
        client = CScodeClient(base_url="http://127.0.0.1:8080", _transport=transport)
        with pytest.raises(CScodeClientError):
            await client.health()
