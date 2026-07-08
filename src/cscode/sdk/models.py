"""Typed request/response models for the CScode REST API SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import httpx

# ── Exceptions ───────────────────────────────────────────────────────


@dataclass
class SdkError(Exception):
    """An error returned by the CScode API."""

    status_code: int
    message: str
    body: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.status_code}] {self.message}"

    @classmethod
    def from_response(cls, response: httpx.Response) -> SdkError:
        try:
            body = response.json()
        except Exception:
            body = {"detail": response.text}
        return cls(
            status_code=response.status_code,
            message=body.get("detail", response.reason_phrase or "unknown"),
            body=body,
        )


class CScodeClientError(Exception):
    """Raised on API error or connection failure."""

    def __init__(
        self,
        message: str = "",
        status_code: int = 0,
        body: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.body = body or {}
        self._message = message
        super().__init__(message)

    def __str__(self) -> str:
        if self.status_code:
            return f"[{self.status_code}] {self._message}"
        return self._message

    @classmethod
    def from_response(cls, response: httpx.Response) -> CScodeClientError:
        try:
            body = response.json()
        except Exception:
            body = {"detail": response.text}
        return cls(
            message=body.get("detail", response.reason_phrase or "unknown"),
            status_code=response.status_code,
            body=body,
        )


# ── Responses ────────────────────────────────────────────────────────


@dataclass
class MessageData:
    """A single chat message from the API."""

    role: str
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageData:
        return cls(
            role=data.get("role", ""),
            content=data.get("content", ""),
            tool_calls=data.get("tool_calls", []),
        )


@dataclass
class SessionInfo:
    """A session summary returned by the list/get endpoints."""

    id: str
    title: str
    provider: str
    model: str
    created_at: str
    updated_at: str
    message_count: int = 0
    status: str = "active"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionInfo:
        return cls(
            id=data["id"],
            title=data["title"],
            provider=data.get("provider", "openai"),
            model=data.get("model", "gpt-4o"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            message_count=data.get("message_count", 0),
            status=data.get("status", "active"),
        )


@dataclass
class SessionListResponse:
    """Response from GET /api/sessions."""

    sessions: list[SessionInfo]
    total: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionListResponse:
        raw = data.get("sessions", data if isinstance(data, list) else [])
        if isinstance(raw, list):
            items = [SessionInfo.from_dict(s) for s in raw]
            return cls(sessions=items, total=len(items))
        return cls(
            sessions=[SessionInfo.from_dict(s) for s in raw],
            total=data.get("total", len(raw)),
        )


@dataclass
class ChatRequest:
    """Request payload for POST /api/chat and /api/chat/stream."""

    prompt: str
    session_id: str | None = None
    model: str | None = None
    system_prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"prompt": self.prompt}
        if self.session_id is not None:
            d["session_id"] = self.session_id
        if self.model is not None:
            d["model"] = self.model
        if self.system_prompt is not None:
            d["system_prompt"] = self.system_prompt
        return d


@dataclass
class ChatResponse:
    """Response from POST /api/chat (non-streaming)."""

    message: MessageData
    session_id: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatResponse:
        return cls(
            message=MessageData.from_dict(data.get("message", {})),
            session_id=data.get("session_id", ""),
        )


@dataclass
class HealthResponse:
    """Response from GET /api/health."""

    status: str
    version: str = ""
    uptime: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HealthResponse:
        return cls(
            status=data.get("status", "unknown"),
            version=data.get("version", ""),
            uptime=data.get("uptime", 0.0),
        )


@dataclass
class ConfigResponse:
    """Response from GET /api/config."""

    provider: str = ""
    model: str = ""
    temperature: float = 0.0
    top_p: float = 0.0
    max_tokens: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfigResponse:
        return cls(
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            temperature=data.get("temperature", 0.0),
            top_p=data.get("top_p", 0.0),
            max_tokens=data.get("max_tokens", 0),
        )


@dataclass
class ConfigSetRequest:
    """Request payload for POST /api/config."""

    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.provider is not None:
            d["provider"] = self.provider
        if self.model is not None:
            d["model"] = self.model
        if self.api_key is not None:
            d["api_key"] = self.api_key
        if self.api_base is not None:
            d["api_base"] = self.api_base
        if self.temperature is not None:
            d["temperature"] = self.temperature
        if self.top_p is not None:
            d["top_p"] = self.top_p
        if self.max_tokens is not None:
            d["max_tokens"] = self.max_tokens
        return d


@dataclass
class WorkspaceInfo:
    """A workspace returned by the API."""

    id: str
    name: str
    path: str
    created_at: str
    updated_at: str
    config_json: str = "{}"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceInfo:
        return cls(
            id=data["id"],
            name=data["name"],
            path=data["path"],
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            config_json=str(data.get("config_json", "{}")),
        )


@dataclass
class CredentialInfo:
    """A credential returned by the API."""

    id: str
    name: str
    type: str
    provider: str
    created_at: float
    updated_at: float
    expires_at: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CredentialInfo:
        return cls(
            id=data["id"],
            name=data["name"],
            type=data.get("type", "api_key"),
            provider=data.get("provider", ""),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
            expires_at=data.get("expires_at"),
        )


@dataclass
class CredentialListResponse:
    """Response from GET /api/credentials."""

    credentials: list[CredentialInfo]
    total: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CredentialListResponse:
        raw = cast("list[dict[str, Any]]", data if isinstance(data, list) else data.get("credentials", []))
        items = [CredentialInfo.from_dict(c) for c in raw]
        total = len(raw) if isinstance(data, list) else data.get("total", len(raw))
        return cls(credentials=items, total=total)

    @classmethod
    def from_list(cls, data: list[dict[str, Any]]) -> CredentialListResponse:
        items = [CredentialInfo.from_dict(c) for c in data]
        return cls(credentials=items, total=len(items))


@dataclass
class WorkspaceListResponse:
    """Response from GET /api/workspaces."""

    workspaces: list[WorkspaceInfo]

    @classmethod
    def from_list(cls, data: list[dict[str, Any]]) -> WorkspaceListResponse:
        items = [WorkspaceInfo.from_dict(w) for w in data]
        return cls(workspaces=items)


@dataclass
class VerificationReportResponse:
    """Response from GET /api/sessions/{id}/verification-report."""

    session_id: str
    summary: dict[str, int]
    verifications: list[dict[str, Any]]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationReportResponse:
        return cls(
            session_id=data.get("session_id", ""),
            summary=data.get("summary", {}),
            verifications=data.get("verifications", []),
        )
