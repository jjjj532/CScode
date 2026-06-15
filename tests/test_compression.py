from __future__ import annotations

import pytest
from cscode.core.compression import ContextCompressor, CompressionStrategy
from cscode.core.messages import Message, MessageRole


class TestThreshold:
    def test_default_threshold(self) -> None:
        c = ContextCompressor()
        assert c.threshold == 100_000

    def test_custom_threshold(self) -> None:
        c = ContextCompressor(threshold=500)
        assert c.threshold == 500


class TestNeedsCompression:
    def test_empty_list(self) -> None:
        c = ContextCompressor()
        assert not c.needs_compression([])

    def test_below_threshold(self) -> None:
        c = ContextCompressor(threshold=1000)
        msgs = [Message(role=MessageRole.USER, content="hello")]
        assert not c.needs_compression(msgs)

    def test_above_threshold(self) -> None:
        c = ContextCompressor(threshold=10)
        msgs = [Message(role=MessageRole.USER, content="x" * 100)]
        assert c.needs_compression(msgs)


class TestCompress:
    def test_no_compression_needed(self) -> None:
        c = ContextCompressor(threshold=10_000)
        msgs = [Message(role=MessageRole.USER, content="hi")]
        result = c.compress(msgs)
        assert result is msgs

    def test_compress_preserves_recent(self) -> None:
        c = ContextCompressor(threshold=5, keep_recent=2)
        msgs = [
            Message(role=MessageRole.SYSTEM, content="sys"),
            Message(role=MessageRole.USER, content="hi"),
            Message(role=MessageRole.ASSISTANT, content="hello"),
            Message(role=MessageRole.USER, content="how are you"),
        ]
        compressed = c.compress(msgs)
        assert len(compressed) >= 2
        assert compressed[-1].content == "how are you"
        assert compressed[-2].content == "hello"

    def test_compress_replaces_old_with_summary_marker(self) -> None:
        c = ContextCompressor(threshold=1, keep_recent=1)
        msgs = [
            Message(role=MessageRole.SYSTEM, content="original sys prompt"),
            Message(role=MessageRole.USER, content="first question"),
            Message(role=MessageRole.ASSISTANT, content="first answer"),
            Message(role=MessageRole.USER, content="second question"),
        ]
        compressed = c.compress(msgs)
        sys_msgs = [m for m in compressed if m.role == MessageRole.SYSTEM]
        assert any("[Compressed]" in m.content for m in sys_msgs)

    def test_total_char_count(self) -> None:
        c = ContextCompressor()
        msgs = [
            Message(role=MessageRole.USER, content="abc"),
            Message(role=MessageRole.ASSISTANT, content="def"),
        ]
        assert c._total_chars(msgs) == 6


class TestStrategy:
    def test_default_strategy(self) -> None:
        c = ContextCompressor()
        assert c.strategy == CompressionStrategy.TRUNCATE

    def test_summarize_falls_back_to_truncate(self) -> None:
        c = ContextCompressor(threshold=1, keep_recent=1, strategy=CompressionStrategy.SUMMARIZE)
        msgs = [
            Message(role=MessageRole.SYSTEM, content="sys"),
            Message(role=MessageRole.USER, content="hello"),
        ]
        compressed = c.compress(msgs)
        assert len(compressed) < len(msgs) or any("[Compressed]" in m.content for m in compressed)
