from __future__ import annotations

import pytest
from cscode.acp.protocol import (
    ACPMessage,
    ACPMessageType,
    ACPRouter,
    create_message,
    parse_message,
)


class TestACPMessageType:
    def test_enum_values(self) -> None:
        assert ACPMessageType.REQUEST.value == "request"
        assert ACPMessageType.RESPONSE.value == "response"
        assert ACPMessageType.EVENT.value == "event"
        assert ACPMessageType.ERROR.value == "error"


class TestACPMessage:
    def test_create_message(self) -> None:
        msg = ACPMessage(
            msg_type=ACPMessageType.REQUEST,
            sender="agent-a",
            receiver="agent-b",
            payload={"action": "search", "query": "test"},
        )
        assert msg.sender == "agent-a"
        assert msg.receiver == "agent-b"
        assert msg.payload["action"] == "search"

    def test_message_to_dict(self) -> None:
        msg = ACPMessage(
            msg_type=ACPMessageType.EVENT,
            sender="agent-a",
            receiver="*",
            payload={"type": "status", "data": "ready"},
        )
        d = msg.to_dict()
        assert d["type"] == "event"
        assert d["sender"] == "agent-a"

    def test_message_from_dict(self) -> None:
        data = {
            "type": "response",
            "sender": "agent-b",
            "receiver": "agent-a",
            "payload": {"result": "found"},
            "correlation_id": "corr-123",
        }
        msg = ACPMessage.from_dict(data)
        assert msg.msg_type == ACPMessageType.RESPONSE
        assert msg.correlation_id == "corr-123"


class TestCreateParse:
    def test_create_and_parse_roundtrip(self) -> None:
        original = create_message(
            msg_type=ACPMessageType.REQUEST,
            sender="agent-1",
            receiver="agent-2",
            payload={"cmd": "execute"},
        )
        serialized = original.to_dict()
        parsed = parse_message(serialized)
        assert parsed.sender == "agent-1"
        assert parsed.receiver == "agent-2"
        assert parsed.payload["cmd"] == "execute"


class TestACPRouter:
    def test_register_agent(self) -> None:
        router = ACPRouter()
        router.register("agent-1")
        assert router.is_registered("agent-1")
        assert not router.is_registered("agent-2")

    def test_unregister_agent(self) -> None:
        router = ACPRouter()
        router.register("agent-1")
        router.unregister("agent-1")
        assert not router.is_registered("agent-1")

    def test_route_message(self) -> None:
        router = ACPRouter()
        router.register("agent-a")
        router.register("agent-b")

        msg = create_message(
            msg_type=ACPMessageType.REQUEST,
            sender="agent-a",
            receiver="agent-b",
            payload={"cmd": "hello"},
        )

        delivered = router.route(msg)
        assert len(delivered) == 1
        assert delivered[0].receiver == "agent-b"

    def test_broadcast(self) -> None:
        router = ACPRouter()
        router.register("a")
        router.register("b")
        router.register("c")

        msg = create_message(
            msg_type=ACPMessageType.EVENT,
            sender="a",
            receiver="*",
            payload={"event": "shutdown"},
        )

        delivered = router.route(msg)
        assert len(delivered) == 2  # b and c (not sender)
