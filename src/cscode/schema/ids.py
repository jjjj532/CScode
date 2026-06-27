"""Branded ID types for distinct semantic primitives.

Every distinct concept uses a NewType so the type checker prevents
mixing them up at compile time. A SessionID cannot be passed where
a ToolCallID is expected.
"""

from typing import NewType

SessionID = NewType("SessionID", str)
"""Unique identifier for a conversation session."""

ToolCallID = NewType("ToolCallID", str)
"""Unique identifier for a single tool invocation within a session."""

MessageID = NewType("MessageID", str)
"""Unique identifier for a message within a session."""

AssistantMessageID = NewType("AssistantMessageID", str)
"""Unique identifier for the assistant message that produced a tool call."""

ModelID = NewType("ModelID", str)
"""Model identifier (e.g. 'gpt-4o', 'claude-3-5-sonnet')."""

ProviderID = NewType("ProviderID", str)
"""Provider identifier (e.g. 'openai', 'anthropic')."""
