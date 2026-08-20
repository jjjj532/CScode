"""Tests for G-3: ToolResult 判别联合 + providerExecuted (spec §4.3)."""

from __future__ import annotations

from cscode.llm.cache_policy import CacheHint
from cscode.schema.ids import ToolCallID
from cscode.schema.messages import (
    Message,
    MessageRole,
    TextPart,
    ToolResultPart,
)
from cscode.schema.tool_result import ToolOutput, ToolResultValue
from cscode.tools2.base import ToolResult


class TestToolResultValue:
    """四种 kind 可构造、可序列化（锁定 JSON 形状）。"""

    def test_json_kind(self) -> None:
        v = ToolResultValue(kind="json", json={"a": 1})
        assert v.kind == "json"
        assert v.json == {"a": 1}

    def test_text_kind(self) -> None:
        v = ToolResultValue(kind="text", text="hello")
        assert v.kind == "text"
        assert v.text == "hello"

    def test_error_kind(self) -> None:
        v = ToolResultValue(kind="error", error="boom")
        assert v.kind == "error"
        assert v.error == "boom"

    def test_content_kind(self) -> None:
        v = ToolResultValue(kind="content", content=[TextPart(text="hi")])
        assert v.kind == "content"
        assert v.content is not None
        assert v.content[0].text == "hi"

    def test_to_dict_json_shape(self) -> None:
        v = ToolResultValue(kind="json", json={"result": "ok"})
        assert v.to_dict() == {"kind": "json", "json": {"result": "ok"}}

    def test_to_dict_text_shape(self) -> None:
        v = ToolResultValue(kind="text", text="hello")
        assert v.to_dict() == {"kind": "text", "text": "hello"}

    def test_to_dict_error_shape(self) -> None:
        v = ToolResultValue(kind="error", error="boom")
        assert v.to_dict() == {"kind": "error", "error": "boom"}

    def test_to_dict_content_shape(self) -> None:
        v = ToolResultValue(kind="content", content=[TextPart(text="hi")])
        d = v.to_dict()
        assert d["kind"] == "content"
        assert d["content"] == [{"type": "text", "text": "hi"}]

    def test_factory_helpers(self) -> None:
        assert ToolResultValue.from_json({"a": 1}).kind == "json"
        assert ToolResultValue.from_text("hi").kind == "text"
        assert ToolResultValue.from_error("boom").kind == "error"

    def test_to_dict_content_media_part(self) -> None:
        """content kind 支持 MediaPart（报告 §5.2 缺口 #4）。"""
        from cscode.schema.messages import MediaPart

        v = ToolResultValue(kind="content", content=[MediaPart(media_type="image/png", data="AAA")])
        d = v.to_dict()
        assert d["kind"] == "content"
        assert d["content"] == [{"type": "media", "media_type": "image/png", "data": "AAA"}]

    def test_to_dict_content_tool_call_part(self) -> None:
        """content kind 支持 ToolCallPart（报告 §5.2 缺口 #4）。"""
        from cscode.schema.ids import ToolCallID
        from cscode.schema.messages import ToolCallPart

        v = ToolResultValue(
            kind="content",
            content=[ToolCallPart(tool_call_id=ToolCallID("c1"), name="bash", args={"cmd": "ls"})],
        )
        d = v.to_dict()
        assert d["kind"] == "content"
        assert d["content"] == [
            {"type": "tool-call", "tool_call_id": "c1", "name": "bash", "args": {"cmd": "ls"}}
        ]


class TestToolOutput:
    """ToolOutput{structured, content} 结构化输出。"""

    def test_structured(self) -> None:
        out = ToolOutput(structured={"plan_id": "p1"})
        assert out.structured == {"plan_id": "p1"}

    def test_content(self) -> None:
        out = ToolOutput(content=[TextPart(text="done")])
        assert out.content is not None
        assert out.content[0].text == "done"


class TestToolResultValueField:
    """ToolResult 携带 value 判别联合 + provider_executed。"""

    def test_tool_result_carries_value(self) -> None:
        r = ToolResult(success=True, value=ToolResultValue.from_text("ok"), data={"x": 1})
        assert r.value is not None
        assert r.value.kind == "text"
        # 旧 data 路径保留（向后兼容）
        assert r.data == {"x": 1}

    def test_provider_executed_flag(self) -> None:
        r = ToolResult(success=True, provider_executed=True)
        assert r.provider_executed is True

    def test_default_provider_executed_false(self) -> None:
        r = ToolResult(success=True)
        assert r.provider_executed is False


class TestToolResultPartExtended:
    """ToolResultPart 增补 provider_executed/cache/metadata。"""

    def test_provider_executed_field(self) -> None:
        p = ToolResultPart(
            tool_call_id=ToolCallID("call_1"),
            name="bash",
            result="done",
            provider_executed=True,
        )
        assert p.provider_executed is True

    def test_cache_hint_field(self) -> None:
        p = ToolResultPart(
            tool_call_id=ToolCallID("call_1"),
            name="bash",
            result="done",
            cache=CacheHint(ttl_seconds=60),
        )
        assert p.cache is not None
        assert p.cache.ttl_seconds == 60

    def test_metadata_field(self) -> None:
        p = ToolResultPart(
            tool_call_id=ToolCallID("call_1"),
            name="bash",
            result="done",
            metadata={"source": "session"},
        )
        assert p.metadata == {"source": "session"}

    def test_backward_compatible_construction(self) -> None:
        """既有构造方式（无新字段）必须保持。"""
        p = ToolResultPart(tool_call_id=ToolCallID("call_1"), name="bash", result="ok")
        assert p.result == "ok"
        assert p.is_error is False
        assert p.provider_executed is False
        assert p.cache is None
        assert p.metadata == {}

    def test_serialization_with_extended_fields(self) -> None:
        """携带 provider_executed/cache 时序列化不破坏既有形状（spec §4.3.4-3）。"""
        p = ToolResultPart(
            tool_call_id=ToolCallID("call_1"),
            name="bash",
            result="done",
            provider_executed=True,
        )
        m = Message(role=MessageRole.TOOL, parts=(p,))
        d = m.to_dict()
        # 既有 tool-result 形状保留
        content = d["content"]
        assert content is not None and isinstance(content, list)
        assert content[0]["type"] == "tool-result"
        assert content[0]["tool_call_id"] == "call_1"
        assert content[0]["result"] == "done"
        # 新字段条件序列化
        assert content[0]["provider_executed"] is True

    def test_serialization_default_no_extra_fields(self) -> None:
        """无新字段时序列化形状与改造前一致。"""
        p = ToolResultPart(tool_call_id=ToolCallID("call_1"), name="bash", result="ok")
        m = Message(role=MessageRole.TOOL, parts=(p,))
        d = m.to_dict()
        content = d["content"]
        assert content is not None and isinstance(content, list)
        entry = content[0]
        assert entry == {
            "type": "tool-result",
            "tool_call_id": "call_1",
            "name": "bash",
            "result": "ok",
            "is_error": False,
        }
