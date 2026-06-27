"""Contract tests for the Schema layer (src/cscode/schema/).

Tests verify:
- Part types: construction, frozen immutability, type discrimination
- Message: construction, content property, to_dict, from_text
- LLMError: construction, retryability, format
- LLMEvent: construction, match/case discrimination
- Options: construction, defaults
- Tool: construction
"""

from __future__ import annotations

import pickle

import pytest

from cscode.schema.errors import LLMError, LLMErrorReason, ToolFailure, is_retryable
from cscode.schema.events import (
    Error as LLMEventError,
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
    ToolFailure as EventToolFailure,
    ToolResult,
    assert_never,
)
from cscode.schema.ids import AssistantMessageID, MessageID, ModelID, ProviderID, SessionID, ToolCallID
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


# ─── IDs ─────────────────────────────────────────────────────────────


class TestIDs:
    def test_session_id_is_newtype_string(self) -> None:
        sid: SessionID = SessionID("sess_abc123")
        assert isinstance(sid, str)
        assert sid == "sess_abc123"

    def test_tool_call_id_is_newtype_string(self) -> None:
        tid: ToolCallID = ToolCallID("call_xyz")
        assert isinstance(tid, str)

    def test_message_id_is_newtype_string(self) -> None:
        mid: MessageID = MessageID("msg_001")
        assert isinstance(mid, str)

    def test_assistant_message_id(self) -> None:
        amid: AssistantMessageID = AssistantMessageID("asst_msg_001")
        assert isinstance(amid, str)

    def test_model_id(self) -> None:
        mid: ModelID = ModelID("gpt-4o")
        assert isinstance(mid, str)

    def test_provider_id(self) -> None:
        pid: ProviderID = ProviderID("openai")
        assert isinstance(pid, str)

    def test_ids_are_distinct_types(self) -> None:
        """Type checker enforces this; runtime check that they're all str."""
        sid: SessionID = SessionID("x")
        tid: ToolCallID = ToolCallID("x")
        assert sid == tid  # Same string value compares equal at runtime


# ─── Part types ──────────────────────────────────────────────────────


class TestParts:
    def test_system_part(self) -> None:
        p = SystemPart(text="You are a helpful assistant.")
        assert p.type == "system"
        assert p.text == "You are a helpful assistant."

    def test_text_part(self) -> None:
        p = TextPart(text="Hello!")
        assert p.type == "text"
        assert p.text == "Hello!"

    def test_media_part(self) -> None:
        p = MediaPart(media_type="image/png", data="base64data")
        assert p.type == "media"
        assert p.media_type == "image/png"
        assert p.data == "base64data"

    def test_tool_call_part(self) -> None:
        p = ToolCallPart(tool_call_id=ToolCallID("call_1"), name="read_file", args={"path": "/tmp/x"})
        assert p.type == "tool-call"
        assert p.name == "read_file"
        assert p.args == {"path": "/tmp/x"}

    def test_tool_result_part(self) -> None:
        p = ToolResultPart(tool_call_id=ToolCallID("call_1"), name="read_file", result="file content")
        assert p.type == "tool-result"
        assert not p.is_error

    def test_tool_result_part_error(self) -> None:
        p = ToolResultPart(tool_call_id=ToolCallID("call_1"), name="read_file", result="not found", is_error=True)
        assert p.is_error

    def test_reasoning_part(self) -> None:
        p = ReasoningPart(text="thinking...", signature="sig123")
        assert p.type == "reasoning"
        assert p.signature == "sig123"

    def test_reasoning_part_no_signature(self) -> None:
        p = ReasoningPart(text="thinking...")
        assert p.signature is None

    def test_part_union_can_hold_any_type(self) -> None:
        parts: list[Part] = [
            SystemPart(text="sys"),
            TextPart(text="txt"),
            MediaPart(media_type="image/png", data="d"),
            ToolCallPart(tool_call_id=ToolCallID("c1"), name="read", args={}),
            ToolResultPart(tool_call_id=ToolCallID("c1"), name="read", result="ok"),
            ReasoningPart(text="..."),
        ]
        assert len(parts) == 6

    def test_parts_are_frozen(self) -> None:
        p = TextPart(text="hello")
        with pytest.raises(AttributeError):
            p.text = "world"  # type: ignore[misc]

    def test_part_type_discrimination_match_case(self) -> None:
        """Ensure match/case works on type discriminator."""
        p: Part = TextPart(text="hello")
        match p:
            case TextPart(text=t):
                assert t == "hello"
            case _:
                pytest.fail("Should have matched TextPart")


# ─── Message ─────────────────────────────────────────────────────────


class TestMessage:
    def test_simple_text_message(self) -> None:
        msg = Message(role=MessageRole.USER, parts=(TextPart(text="Hello"),))
        assert msg.role == "user"
        assert len(msg.parts) == 1
        assert msg.content == "Hello"

    def test_message_with_multiple_parts(self) -> None:
        msg = Message(
            role=MessageRole.USER,
            parts=(TextPart(text="Check this: "), MediaPart(media_type="image/png", data="abc")),
        )
        assert len(msg.parts) == 2
        # content only includes text parts
        assert msg.content == "Check this: "

    def test_content_concatenates_text_and_reasoning(self) -> None:
        msg = Message(
            role=MessageRole.ASSISTANT,
            parts=(
                ReasoningPart(text="Let me think..."),
                TextPart(text="The answer is 42."),
            ),
        )
        assert "Let me think..." in msg.content
        assert "The answer is 42." in msg.content

    def test_to_dict_text_only(self) -> None:
        msg = Message(role=MessageRole.USER, parts=(TextPart(text="Hi"),))
        d = msg.to_dict()
        assert d["role"] == "user"
        assert isinstance(d["content"], list)
        assert d["content"] == [{"type": "text", "text": "Hi"}]

    def test_to_dict_with_tool_calls(self) -> None:
        tid = ToolCallID("call_1")
        msg = Message(
            role=MessageRole.ASSISTANT,
            parts=(
                TextPart(text="Let me check..."),
                ToolCallPart(tool_call_id=tid, name="read_file", args={"path": "/x"}),
            ),
        )
        d = msg.to_dict()
        assert "tool_calls" in d
        assert d["tool_calls"] == [
            {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": {"path": "/x"}}},
        ]

    def test_to_dict_tool_result(self) -> None:
        msg = Message.from_tool_result(ToolCallID("call_1"), "read_file", "content")
        d = msg.to_dict()
        assert d["role"] == "tool"
        assert "content" in d

    def test_from_text_convenience(self) -> None:
        msg = Message.from_text("user", "Hello!")
        assert msg.role == "user"
        assert msg.content == "Hello!"

    def test_system_convenience(self) -> None:
        msg = Message.system("Be helpful.")
        assert msg.role == "system"
        assert msg.content == "Be helpful."

    def test_user_convenience(self) -> None:
        msg = Message.user("Hi")
        assert msg.role == "user"
        assert msg.content == "Hi"

    def test_assistant_convenience(self) -> None:
        msg = Message.assistant("Response")
        assert msg.role == "assistant"
        assert msg.content == "Response"

    def test_assistant_empty(self) -> None:
        msg = Message.assistant()
        assert msg.role == "assistant"
        assert msg.content == ""

    def test_message_is_iterable(self) -> None:
        msg = Message.user("Hello")
        parts = list(msg)
        assert len(parts) == 1
        assert isinstance(parts[0], TextPart)

    def test_message_len(self) -> None:
        msg = Message.user("Hello")
        assert len(msg) == 1

    def test_message_with_id(self) -> None:
        mid = MessageID("msg_001")
        msg = Message(role=MessageRole.USER, parts=(TextPart(text="Hi"),), id=mid)
        assert msg.id == mid

    def test_message_with_assistant_message_id(self) -> None:
        amid = AssistantMessageID("asst_001")
        msg = Message(
            role=MessageRole.TOOL,
            parts=(ToolResultPart(tool_call_id=ToolCallID("c1"), name="read", result="ok"),),
            assistant_message_id=amid,
        )
        assert msg.assistant_message_id == amid

    def test_to_dict_empty_content_fallback(self) -> None:
        """When no parts exist, content defaults to empty string."""
        msg = Message(role=MessageRole.ASSISTANT, parts=())
        d = msg.to_dict()
        assert d["content"] == ""

    def test_to_dict_reasoning_part_with_signature(self) -> None:
        msg = Message(role=MessageRole.ASSISTANT, parts=(ReasoningPart(text="thinking", signature="sig"),))
        d = msg.to_dict()
        assert isinstance(d["content"], list)
        assert d["content"][0]["signature"] == "sig"

    def test_to_dict_reasoning_part_no_signature(self) -> None:
        msg = Message(role=MessageRole.ASSISTANT, parts=(ReasoningPart(text="thinking"),))
        d = msg.to_dict()
        assert isinstance(d["content"], list)
        assert "signature" not in d["content"][0]


# ─── MessageRole ─────────────────────────────────────────────────────


class TestMessageRole:
    def test_constants(self) -> None:
        assert MessageRole.SYSTEM == "system"
        assert MessageRole.USER == "user"
        assert MessageRole.ASSISTANT == "assistant"
        assert MessageRole.TOOL == "tool"

    def test_all(self) -> None:
        assert MessageRole.ALL == ("system", "user", "assistant", "tool")


# ─── LLMError ────────────────────────────────────────────────────────


class TestLLMError:
    def test_retryable_reasons(self) -> None:
        assert is_retryable(LLMErrorReason.RATE_LIMIT)
        assert is_retryable(LLMErrorReason.PROVIDER_INTERNAL)

    def test_non_retryable_reasons(self) -> None:
        assert not is_retryable(LLMErrorReason.INVALID_REQUEST)
        assert not is_retryable(LLMErrorReason.AUTHENTICATION)
        assert not is_retryable(LLMErrorReason.CONTENT_POLICY)
        assert not is_retryable(LLMErrorReason.UNKNOWN_PROVIDER)

    def test_default_retryable_from_reason(self) -> None:
        err = LLMError(module="LLM", method="stream", reason=LLMErrorReason.RATE_LIMIT, message="Too fast")
        assert err.retryable

    def test_retryable_override(self) -> None:
        err = LLMError(
            module="LLM",
            method="stream",
            reason=LLMErrorReason.INVALID_REQUEST,
            message="Bad request",
            retryable=True,
        )
        assert err.retryable

    def test_retry_after_ms(self) -> None:
        err = LLMError(
            module="LLM",
            method="stream",
            reason=LLMErrorReason.RATE_LIMIT,
            message="429",
            retry_after_ms=5000,
        )
        assert err.retry_after_ms == 5000

    def test_format_message_with_retry(self) -> None:
        err = LLMError(
            module="LLM",
            method="stream",
            reason=LLMErrorReason.RATE_LIMIT,
            message="429 Too Many Requests",
            retry_after_ms=5000,
        )
        msg = str(err)
        assert "RateLimit" in msg
        assert "LLM.stream" in msg
        assert "retry after" in msg

    def test_format_message_without_retry(self) -> None:
        err = LLMError(
            module="ConfigStore",
            method="get",
            reason=LLMErrorReason.AUTHENTICATION,
            message="No API key",
        )
        msg = str(err)
        assert "Authentication" in msg
        assert "ConfigStore.get" in msg
        assert "retry after" not in msg

    def test_reason_enum_values(self) -> None:
        assert LLMErrorReason.INVALID_REQUEST.value == "InvalidRequest"
        assert LLMErrorReason.RATE_LIMIT.value == "RateLimit"

    def test_pickle_roundtrip(self) -> None:
        """LLMError supports pickling for async exception propagation."""
        err = LLMError(module="LLM", method="stream", reason=LLMErrorReason.RATE_LIMIT, message="429")
        restored = pickle.loads(pickle.dumps(err))
        assert restored.module == "LLM"
        assert restored.method == "stream"
        assert restored.reason == LLMErrorReason.RATE_LIMIT
        assert restored.message == "429"

    def test_tool_failure(self) -> None:
        err = ToolFailure("File not found")
        assert str(err) == "File not found"
        assert err.message == "File not found"


# ─── LLMEvent types ─────────────────────────────────────────────────


class TestLLMEvents:
    def test_text_started(self) -> None:
        ev = TextStarted()
        assert ev.type == "text-started"

    def test_text_delta(self) -> None:
        ev = TextDelta(text="Hello")
        assert ev.text == "Hello"

    def test_text_ended(self) -> None:
        ev = TextEnded(full_text="Hello world")
        assert ev.full_text == "Hello world"

    def test_tool_call_started(self) -> None:
        ev = ToolCallStarted(tool_call_id=ToolCallID("c1"), name="read")
        assert ev.type == "tool-call-started"
        assert ev.tool_call_id == "c1"

    def test_tool_call_delta(self) -> None:
        ev = ToolCallDelta(tool_call_id=ToolCallID("c1"), args_text='{"path":')
        assert ev.args_text == '{"path":'

    def test_tool_call_ended(self) -> None:
        ev = ToolCallEnded(tool_call_id=ToolCallID("c1"), name="read", args={"path": "/x"})
        assert ev.args == {"path": "/x"}

    def test_tool_result(self) -> None:
        ev = ToolResult(tool_call_id=ToolCallID("c1"), result="ok")
        assert ev.result == "ok"

    def test_tool_failure(self) -> None:
        ev = EventToolFailure(tool_call_id=ToolCallID("c1"), error="timeout")
        assert ev.error == "timeout"

    def test_reasoning_started(self) -> None:
        ev = ReasoningStarted(signature="sig")
        assert ev.signature == "sig"

    def test_reasoning_delta(self) -> None:
        ev = ReasoningDelta(text="thinking", signature="sig")
        assert ev.text == "thinking"

    def test_reasoning_ended(self) -> None:
        ev = ReasoningEnded(text="done", signature="sig")
        assert ev.text == "done"

    def test_finish(self) -> None:
        ev = Finish(finish_reason="stop", usage={"prompt_tokens": 10, "completion_tokens": 20})
        assert ev.finish_reason == "stop"
        assert ev.usage == {"prompt_tokens": 10, "completion_tokens": 20}

    def test_finish_no_usage(self) -> None:
        ev = Finish(finish_reason="stop")
        assert ev.usage is None

    def test_error_event(self) -> None:
        inner = LLMError(module="LLM", method="stream", reason=LLMErrorReason.AUTHENTICATION, message="No key")
        ev = LLMEventError(error=inner)
        assert ev.type == "error"
        assert ev.error.reason == LLMErrorReason.AUTHENTICATION

    def test_pending(self) -> None:
        ev = Pending()
        assert ev.type == "pending"

    def test_llm_event_union_can_hold_any_type(self) -> None:
        events: list[LLMEvent] = [
            TextStarted(),
            TextDelta(text="a"),
            TextEnded(full_text="a"),
            ToolCallStarted(tool_call_id=ToolCallID("c1"), name="r"),
            ToolCallDelta(tool_call_id=ToolCallID("c1"), args_text="{}"),
            ToolCallEnded(tool_call_id=ToolCallID("c1"), name="r", args={}),
            ToolResult(tool_call_id=ToolCallID("c1"), result="ok"),
            EventToolFailure(tool_call_id=ToolCallID("c1"), error="e"),
            ReasoningStarted(),
            ReasoningDelta(text="t"),
            ReasoningEnded(text="t"),
            Finish(finish_reason="stop"),
            LLMEventError(error=LLMError(module="LLM", method="s", reason=LLMErrorReason.RATE_LIMIT, message="m")),
            Pending(),
        ]
        assert len(events) == 14

    def test_event_type_discrimination_match_case(self) -> None:
        """Verify match/case exhaustive pattern works on events."""
        ev: LLMEvent = TextDelta(text="hello")
        match ev:
            case TextDelta(text=t):
                assert t == "hello"
            case _:
                pytest.fail("Should have matched TextDelta")


# ─── Options ──────────────────────────────────────────────────────────


class TestOptions:
    def test_generation_options_defaults(self) -> None:
        opts = GenerationOptions()
        assert opts.temperature is None
        assert opts.top_p is None
        assert opts.max_tokens is None
        assert opts.stop == ()

    def test_generation_options_custom(self) -> None:
        opts = GenerationOptions(temperature=0.7, max_tokens=2048, stop=("\n",))
        assert opts.temperature == 0.7
        assert opts.max_tokens == 2048
        assert opts.stop == ("\n",)

    def test_generation_options_frozen(self) -> None:
        opts = GenerationOptions(temperature=0.5)
        with pytest.raises(AttributeError):
            opts.temperature = 0.7  # type: ignore[misc]

    def test_provider_options_defaults(self) -> None:
        opts = ProviderOptions()
        assert opts.reasoning_effort is None
        assert opts.store is None
        assert opts.metadata == {}
        assert opts.extra == {}

    def test_provider_options_custom(self) -> None:
        opts = ProviderOptions(reasoning_effort="high", metadata={"user": "test"}, extra={"custom": "value"})
        assert opts.reasoning_effort == "high"
        assert opts.metadata == {"user": "test"}
        assert opts.extra == {"custom": "value"}

    def test_cache_policy_defaults(self) -> None:
        policy = CachePolicy()
        assert policy.enabled is True
        assert policy.breakpoints == ()

    def test_cache_policy_disabled(self) -> None:
        policy = CachePolicy(enabled=False)
        assert not policy.enabled

    def test_cache_policy_with_breakpoints(self) -> None:
        policy = CachePolicy(breakpoints=(0, 2))
        assert policy.breakpoints == (0, 2)


# ─── Tool ─────────────────────────────────────────────────────────────


class TestTool:
    def test_tool_definition(self) -> None:
        td = ToolDefinition(name="read", description="Read a file", input_schema={"type": "object"})
        assert td.name == "read"
        assert td.input_schema == {"type": "object"}

    def test_tool_choice_literals(self) -> None:
        # Verify type narrowing works
        choices: list[ToolChoice] = ["auto", "required", "none"]
        assert len(choices) == 3

    def test_tool_choice_specific_name(self) -> None:
        choice: ToolChoice = "read_file"
        assert choice == "read_file"
