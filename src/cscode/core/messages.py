"""
⚠️ LEGACY — Prefer ``cscode.schema.messages`` for new code.

This module exists for backward compatibility. The new Parts-based API
(``cscode.schema.messages``) is the standard for new code instead of the
flat ``content: str`` + ``tool_calls: list[dict]`` format here.

Migration guide:
    Old: from cscode.core.messages import Message, MessageRole
    New: from cscode.schema.messages import Message, MessageRole

    Old Message:
        msg = Message(role=MessageRole.USER, content="hello")
        msg.tool_calls = [...]

    New Message:
        msg = Message.user("hello")             # shortcut
        msg = Message.from_text(role, "hello")   # explicit
        msg = Message(role=role, parts=(TextPart(text="hello"),))  # full form
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from cscode.core.images import ImageAttachment


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    role: MessageRole
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    image_attachments: list[ImageAttachment] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Session:
    id: str | None = None
    title: str = ""
    provider: str = "openai"
    model: str = "gpt-4o"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
