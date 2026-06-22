from __future__ import annotations

from cscode.core.compression import ContextCompressor, CompressionStrategy
from cscode.core.messages import Message, MessageRole


def test_compressor_not_needed_for_short_history():
    compressor = ContextCompressor(threshold=50_000)
    messages = [
        Message(role=MessageRole.USER, content="short message"),
        Message(role=MessageRole.ASSISTANT, content="short reply"),
    ]
    assert not compressor.needs_compression(messages)
    result = compressor.compress(messages)
    assert len(result) == 2
    assert result == messages


def test_compressor_truncates_long_history():
    compressor = ContextCompressor(threshold=100, keep_recent=3)
    messages = [
        Message(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
    ]
    for i in range(20):
        messages.append(Message(role=MessageRole.USER, content=f"Message {i} with some padding content to exceed the threshold."))
        messages.append(Message(role=MessageRole.ASSISTANT, content=f"Reply {i} with some padding content as well for testing."))

    assert compressor.needs_compression(messages)
    result = compressor.compress(messages)
    assert len(result) < len(messages)

    # System message should be preserved
    assert result[0].role == MessageRole.SYSTEM
    assert "You are a helpful assistant." in result[0].content

    # Compression note should be present
    assert "[Compressed]" in result[1].content

    # Recent messages should be preserved
    assert result[-1].content == messages[-1].content


def test_compressor_preserves_system_prompt():
    compressor = ContextCompressor(threshold=50, keep_recent=2)
    messages = [
        Message(role=MessageRole.SYSTEM, content="System prompt here."),
    ]
    for i in range(10):
        messages.append(Message(role=MessageRole.USER, content=f"Longer user message number {i} with lots of text."))
        messages.append(Message(role=MessageRole.ASSISTANT, content=f"Longer assistant message number {i} with lots of text."))

    result = compressor.compress(messages)
    assert result[0].role == MessageRole.SYSTEM
    assert result[0].content == "System prompt here."


def test_compressor_summarize_falls_back_to_truncate():
    compressor = ContextCompressor(threshold=50, keep_recent=2, strategy=CompressionStrategy.SUMMARIZE)
    messages = [Message(role=MessageRole.USER, content=f"Long message {i} with lots of text.") for i in range(10)]

    result = compressor.compress(messages)
    assert len(result) < len(messages)
    # Should still work (fallback to truncate)
