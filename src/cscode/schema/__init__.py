"""CScode Schema Layer — Pure type definitions with zero runtime dependencies.

This is the foundation layer of the architecture:
  schema → llm → core → app

No module in this package imports from anywhere else in cscode.
"""

from cscode.schema.errors import LLMError, LLMErrorReason, ToolFailure
from cscode.schema.events import (
    Error as LLMEventError,
)
from cscode.schema.events import (
    Finish,
    LLMEvent,
    Pending,
    ReasoningDelta,
    ReasoningEnded,
    ReasoningStarted,
    TextDelta,
    TextEnded,
    TextStarted,
    ToolCallDelta,
    ToolCallEnded,
    ToolCallStarted,
    ToolResult,
)
from cscode.schema.events import (
    ToolFailure as EventToolFailure,
)
from cscode.schema.ids import (
    AssistantMessageID,
    MessageID,
    ModelID,
    ProviderID,
    SessionID,
    ToolCallID,
)
from cscode.schema.messages import (
    MediaPart,
    Message,
    MessageRole,
    Part,
    ReasoningPart,
    SystemPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from cscode.schema.options import CachePolicy, GenerationOptions, ProviderOptions
from cscode.schema.tool import ToolChoice, ToolDefinition

__all__ = [
    # messages
    "SystemPart",
    "TextPart",
    "MediaPart",
    "ToolCallPart",
    "ToolResultPart",
    "ReasoningPart",
    "Part",
    "MessageRole",
    "Message",
    # errors
    "LLMErrorReason",
    "LLMError",
    "ToolFailure",
    # events
    "TextStarted",
    "TextDelta",
    "TextEnded",
    "ToolCallStarted",
    "ToolCallDelta",
    "ToolCallEnded",
    "ToolResult",
    "EventToolFailure",
    "ReasoningStarted",
    "ReasoningDelta",
    "ReasoningEnded",
    "Finish",
    "LLMEventError",
    "Pending",
    "LLMEvent",
    # ids
    "SessionID",
    "ToolCallID",
    "MessageID",
    "AssistantMessageID",
    "ModelID",
    "ProviderID",
    # options
    "GenerationOptions",
    "ProviderOptions",
    "CachePolicy",
    # tool
    "ToolDefinition",
    "ToolChoice",
]
