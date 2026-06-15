from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class ACPMessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    ERROR = "error"


@dataclass
class ACPMessage:
    msg_type: ACPMessageType
    sender: str
    receiver: str
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""

    def __post_init__(self) -> None:
        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.msg_type.value,
            "sender": self.sender,
            "receiver": self.receiver,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ACPMessage:
        return cls(
            msg_type=ACPMessageType(data.get("type", "event")),
            sender=data.get("sender", ""),
            receiver=data.get("receiver", ""),
            payload=data.get("payload", {}),
            correlation_id=data.get("correlation_id", ""),
        )


def create_message(
    msg_type: ACPMessageType,
    sender: str,
    receiver: str,
    payload: dict[str, Any],
) -> ACPMessage:
    return ACPMessage(
        msg_type=msg_type,
        sender=sender,
        receiver=receiver,
        payload=payload,
    )


def parse_message(data: dict[str, Any]) -> ACPMessage:
    return ACPMessage.from_dict(data)


class ACPRouter:
    def __init__(self) -> None:
        self._agents: set[str] = set()

    def register(self, agent_id: str) -> None:
        self._agents.add(agent_id)
        logger.info("ACP: registered agent '%s'", agent_id)

    def unregister(self, agent_id: str) -> None:
        self._agents.discard(agent_id)
        logger.info("ACP: unregistered agent '%s'", agent_id)

    def is_registered(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def route(self, message: ACPMessage) -> list[ACPMessage]:
        delivered: list[ACPMessage] = []
        if message.receiver == "*":
            for agent_id in self._agents:
                if agent_id != message.sender:
                    delivered.append(message)
        elif message.receiver in self._agents:
            delivered.append(message)
        return delivered
