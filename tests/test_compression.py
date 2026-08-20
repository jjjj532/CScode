from __future__ import annotations

import pytest

from cscode.core.compression import (
    DEFAULT_BUFFER_TOKENS,
    DEFAULT_KEEP_TOKENS,
    TOOL_OUTPUT_MAX_CHARS,
    CompressionStrategy,
    ContextCompressor,
    _message_token_count,
    serialize_messages,
)
from cscode.schema.ids import ToolCallID
from cscode.schema.messages import Message, MessageRole, ToolCallPart


class TestDefaults:
    """对齐 OpenCode compaction.ts 常量。"""

    def test_default_buffer_tokens(self) -> None:
        assert DEFAULT_BUFFER_TOKENS == 20_000

    def test_default_keep_tokens(self) -> None:
        assert DEFAULT_KEEP_TOKENS == 8_000

    def test_tool_output_max_chars(self) -> None:
        assert TOOL_OUTPUT_MAX_CHARS == 2_000

    def test_default_strategy_is_truncate(self) -> None:
        c = ContextCompressor()
        assert c.strategy == CompressionStrategy.TRUNCATE


class TestNeedsCompression:
    def test_empty_list(self) -> None:
        c = ContextCompressor()
        assert not c.needs_compression([])

    def test_below_token_buffer(self) -> None:
        c = ContextCompressor(buffer_tokens=100)
        msgs = [Message.user("hello")]
        assert not c.needs_compression(msgs)

    def test_above_token_buffer_cjk(self) -> None:
        """5k CJK chars ≈ 5k tokens，buffer=100 应触发。"""
        c = ContextCompressor(buffer_tokens=100)
        msgs = [Message.user("中" * 5_000)]
        assert c.needs_compression(msgs)

    def test_above_token_buffer_ascii(self) -> None:
        """20k ASCII chars ≈ 5k tokens，buffer=100 应触发。"""
        c = ContextCompressor(buffer_tokens=100)
        msgs = [Message.user("a" * 20_000)]
        assert c.needs_compression(msgs)

    def test_token_based_not_char_based(self) -> None:
        """字符数相同，CJK 触发（token 密度高）而 ASCII 不触发（buffer=2000）。"""
        c = ContextCompressor(buffer_tokens=2_000)
        cjk = [Message.user("中" * 4_000)]  # 4k tokens
        ascii_ = [Message.user("a" * 4_000)]  # 1k tokens
        assert c.needs_compression(cjk)
        assert not c.needs_compression(ascii_)


class TestSerializeMessages:
    """OpenCode compaction 序列化规则逐字符锁定。"""

    def test_user_text(self) -> None:
        msg = Message.user("hello there")
        assert serialize_messages([msg]) == "[User]: hello there"

    def test_assistant_text(self) -> None:
        msg = Message.assistant("hi back")
        assert serialize_messages([msg]) == "[Assistant]: hi back"

    def test_system(self) -> None:
        msg = Message.system("be helpful")
        assert serialize_messages([msg]) == "[System update]: be helpful"

    def test_tool_call(self) -> None:
        msg = Message(
            role=MessageRole.ASSISTANT,
            parts=(
                ToolCallPart(tool_call_id=ToolCallID("call_1"), name="read", args={"path": "a.py"}),
            ),
        )
        assert serialize_messages([msg]) == "[Assistant tool call]: read({\"path\": \"a.py\"})"

    def test_tool_result(self) -> None:
        msg = Message.from_tool_result(tool_call_id=ToolCallID("call_1"), name="read", result="file contents")
        assert serialize_messages([msg]) == "[Tool result]: file contents"

    def test_tool_error(self) -> None:
        msg = Message.from_tool_result(tool_call_id=ToolCallID("call_1"), name="read", result="boom", is_error=True)
        assert serialize_messages([msg]) == "[Tool error]: boom"

    def test_tool_result_truncated(self) -> None:
        """超过 TOOL_OUTPUT_MAX_CHARS 的工具结果显示 truncated 标记。"""
        msg = Message.from_tool_result(
            tool_call_id=ToolCallID("call_1"), name="read", result="x" * (TOOL_OUTPUT_MAX_CHARS + 100)
        )
        serialized = serialize_messages([msg])
        assert "[Tool result]:" in serialized
        assert "truncated" in serialized

    def test_multi_message_join(self) -> None:
        msgs = [Message.user("a"), Message.assistant("b")]
        assert serialize_messages(msgs) == "[User]: a\n[Assistant]: b"


class TestCompressTokenAware:
    def test_no_compression_needed(self) -> None:
        c = ContextCompressor(buffer_tokens=10_000)
        msgs = [Message.user("hi")]
        result = c.compress(msgs)
        assert result is msgs

    def test_truncate_keeps_recent_within_keep_tokens(self) -> None:
        """切分后 recent 段 token 数不超过 keep_tokens。"""
        c = ContextCompressor(buffer_tokens=100, keep_tokens=50)
        msgs = [Message.user(f"message {i} " + "x" * 100) for i in range(20)]
        result = c.compress(msgs)
        assert len(result) < len(msgs)
        # 结果最后一个仍是最后一条消息（从尾部切分）
        assert result[-1].content == msgs[-1].content

    def test_truncate_recent_tokens_within_budget(self) -> None:
        """recent 段 token 总和 ≤ keep_tokens（报告 §5.2 缺口 #1 显式断言）。"""
        c = ContextCompressor(buffer_tokens=100, keep_tokens=50)
        msgs = [Message.user(f"message {i} " + "x" * 100) for i in range(20)]
        head, recent = c._split_head_recent(msgs)
        assert recent  # 有保留段
        assert head  # 有压缩段
        recent_tokens = sum(_message_token_count(m) for m in recent)
        assert recent_tokens <= c.keep_tokens

    def test_system_prompt_preserved(self) -> None:
        c = ContextCompressor(buffer_tokens=100, keep_tokens=50)
        msgs = [Message.system("original sys prompt")] + [
            Message.user(f"q{i}") for i in range(10)
        ]
        result = c.compress(msgs)
        sys_msgs = [m for m in result if m.role == MessageRole.SYSTEM]
        assert any("original sys prompt" in m.content for m in sys_msgs)

    def test_compression_note_present(self) -> None:
        c = ContextCompressor(buffer_tokens=100, keep_tokens=50)
        msgs = [Message.user(f"m{i}" + "y" * 200) for i in range(10)]
        result = c.compress(msgs)
        assert any("[Compressed]" in m.content for m in result)


class TestSummarizeStrategy:
    def test_summarize_with_summarizer(self) -> None:
        """注入 summarizer 回调时，压缩段被序列化并交给摘要函数。"""

        def fake_summarize(serialized: str) -> str:
            return "SUMMARY:" + serialized[:50]

        c = ContextCompressor(
            buffer_tokens=100,
            keep_tokens=50,
            strategy=CompressionStrategy.SUMMARIZE,
            summarizer=fake_summarize,
        )
        msgs = [Message.user(f"q{i} " + "z" * 200) for i in range(10)]
        result = c.compress(msgs)
        assert len(result) < len(msgs)
        # 摘要结果出现在压缩说明中
        assert any("SUMMARY:" in m.content for m in result)

    def test_summarize_fallback_on_summarizer_error(self) -> None:
        """summarizer 抛错 → 回退 TRUNCATE，不抛异常。"""

        def broken_summarize(serialized: str) -> str:
            raise RuntimeError("llm down")

        c = ContextCompressor(
            buffer_tokens=100,
            keep_tokens=50,
            strategy=CompressionStrategy.SUMMARIZE,
            summarizer=broken_summarize,
        )
        msgs = [Message.user(f"q{i} " + "z" * 200) for i in range(10)]
        result = c.compress(msgs)  # 不应抛异常
        assert len(result) < len(msgs)

    def test_summarize_error_logs_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        """summarizer 抛错时必须记录异常日志（报告 §5.2 缺口 #2，Ratchet 规则）。"""

        def broken_summarize(serialized: str) -> str:
            raise RuntimeError("llm down")

        c = ContextCompressor(
            buffer_tokens=100,
            keep_tokens=50,
            strategy=CompressionStrategy.SUMMARIZE,
            summarizer=broken_summarize,
        )
        msgs = [Message.user(f"q{i} " + "z" * 200) for i in range(10)]
        with caplog.at_level("ERROR", logger="cscode.core.compression"):
            c.compress(msgs)
        assert any("summarizer" in r.message.lower() for r in caplog.records)

    def test_no_summarizer_falls_back_to_truncate(self) -> None:
        """未注入 summarizer → 明确回退 TRUNCATE 且带压缩说明。"""
        c = ContextCompressor(
            buffer_tokens=100,
            keep_tokens=50,
            strategy=CompressionStrategy.SUMMARIZE,
        )
        msgs = [Message.user(f"q{i} " + "z" * 200) for i in range(10)]
        result = c.compress(msgs)
        assert any("[Compressed]" in m.content for m in result)


class TestEdgeCases:
    """边界：单条超预算消息无法压缩 → 原样返回。"""

    def test_single_message_over_budget_returns_original(self) -> None:
        c = ContextCompressor(buffer_tokens=10, keep_tokens=5)
        msgs = [Message.user("中" * 100)]  # 100 tokens
        result = c.compress(msgs)
        assert result is msgs  # 无 head 可压缩 → 原对象返回

    def test_single_message_over_budget_truncate_strategy(self) -> None:
        c = ContextCompressor(
            buffer_tokens=10, keep_tokens=5, strategy=CompressionStrategy.TRUNCATE
        )
        msgs = [Message.user("中" * 100)]
        result = c.compress(msgs)
        assert result is msgs

    def test_all_messages_recent_no_head(self) -> None:
        """所有消息都在 recent 预算内 → 无 head → 原样返回。"""
        c = ContextCompressor(buffer_tokens=1, keep_tokens=1_000)
        msgs = [Message.user("hi"), Message.assistant("yo")]
        result = c.compress(msgs)
        assert result is msgs
