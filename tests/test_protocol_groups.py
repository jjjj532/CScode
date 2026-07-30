"""Tests for Protocol group contracts — session/tool/config endpoint shapes.

These contracts define the typed request/response shapes for API
endpoints without depending on FastAPI.
"""

from __future__ import annotations

import typing

from cscode.protocol.groups.sessions import (
    CreateSessionRequest,
    RunStateRequest,
    RunStateResponse,
    SessionListParams,
    SessionResponse,
)
from cscode.protocol.groups.tools import ToolDefinitionResponse, ToolListParams
from cscode.protocol.groups.config import (
    ConfigItem,
    ConfigReferenceItem,
    ConfigResponse,
    ConfigUpdateRequest,
)


class TestSessionGroup:
    """Session endpoint contracts.

    Matches the existing routes/sessions.py API shapes.
    """

    def test_session_list_params(self) -> None:
        params = SessionListParams(limit=50, offset=10)
        assert params.limit == 50
        assert params.offset == 10
        assert params.limit != params.offset

    def test_session_list_params_defaults(self) -> None:
        params = SessionListParams()
        assert params.limit == 50  # default
        assert params.offset == 0  # default

    def test_create_session_request(self) -> None:
        req = CreateSessionRequest(title="My Chat")
        assert req.title == "My Chat"

    def test_create_session_request_default(self) -> None:
        req = CreateSessionRequest()
        assert req.title == "New Session"  # default

    def test_session_response(self) -> None:
        resp = SessionResponse(
            id="sess_abc",
            title="Test",
            provider="openai",
            model="gpt-4o",
            status="active",
            created_at=1000.0,
            updated_at=2000.0,
            message_count=5,
            event_count=42,
        )
        assert resp.message_count == 5
        assert resp.event_count == 42

    def test_session_response_minimal(self) -> None:
        resp = SessionResponse(
            id="s1", title="T", provider="p", model="m",
            status="active", created_at=0.0, updated_at=0.0,
        )
        assert resp.message_count == 0
        assert resp.event_count == 0

    def test_run_state_request(self) -> None:
        req = RunStateRequest(status="running", error="")
        assert req.status == "running"
        assert req.error == ""

    def test_run_state_response(self) -> None:
        resp = RunStateResponse(status="completed", error="")
        assert resp.status == "completed"


class TestToolGroup:
    """Tool endpoint contracts."""

    def test_tool_list_params(self) -> None:
        params = ToolListParams()
        # No required fields — all optional

    def test_tool_definition_response(self) -> None:
        resp = ToolDefinitionResponse(
            name="bash",
            description="Execute shell commands",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
        )
        assert resp.name == "bash"
        assert resp.input_schema["type"] == "object"


class TestConfigGroup:
    """Config endpoint contracts."""

    def test_config_item(self) -> None:
        item = ConfigItem(key="model", value="gpt-4o")
        assert item.key == "model"
        assert item.value == "gpt-4o"

    def test_config_response(self) -> None:
        resp = ConfigResponse(config=[ConfigItem(key="k", value="v")])
        assert len(resp.config) == 1
        assert resp.config[0].key == "k"

    def test_config_update_request(self) -> None:
        req = ConfigUpdateRequest(config=[ConfigItem(key="model", value="claude-3")])
        assert req.config[0].value == "claude-3"

    def test_config_reference_item(self) -> None:
        item = ConfigReferenceItem(
            key="model",
            type="string",
            description="LLM model name",
            default="gpt-4o",
        )
        assert item.key == "model"
        assert item.type == "string"
        assert item.default == "gpt-4o"


class TestProtocolGroupNoRuntimeDeps:
    """None of the protocol groups import from cscode.core or cscode.server."""

    GROUPS = [
        "cscode.protocol.groups.sessions",
        "cscode.protocol.groups.tools",
        "cscode.protocol.groups.config",
    ]

    def test_no_runtime_deps(self) -> None:
        import importlib
        import inspect

        for mod_name in self.GROUPS:
            mod = importlib.import_module(mod_name)
            source = inspect.getsource(mod)
            assert "cscode.core" not in source, f"{mod_name} imports cscode.core"
            assert "cscode.server" not in source, f"{mod_name} imports cscode.server"
