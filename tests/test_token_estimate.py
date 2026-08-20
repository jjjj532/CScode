from __future__ import annotations

from cscode.core.token_estimate import estimate_tokens


class TestEstimateTokens:
    """estimate_tokens 近似规则（OpenCode Token.estimate 对齐）：

    - ASCII: ~4 chars per token (0.25 token/char)
    - CJK/宽字符: ~1 token per char
    - 空字符串: 0
    """

    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_ascii_short(self) -> None:
        # "hello" = 5 chars → 5/4 = 1.25 → 1
        assert estimate_tokens("hello") == 1

    def test_ascii_exact_token(self) -> None:
        # 4 chars → 1 token
        assert estimate_tokens("abcd") == 1

    def test_ascii_rounding(self) -> None:
        # 9 chars → 9/4 = 2.25 → 2
        assert estimate_tokens("abcdefghi") == 2

    def test_cjk_char_is_one_token(self) -> None:
        # 中文 1 char ≈ 1 token
        assert estimate_tokens("你") == 1

    def test_cjk_mixed_with_ascii(self) -> None:
        # "你好hello" = 2 CJK (2 tokens) + 5 ASCII (1 token) = 3
        assert estimate_tokens("你好hello") == 3

    def test_cjk_sentence(self) -> None:
        # "这是一段十个汉字的中文文本" = 13 CJK chars ≈ 13 tokens
        assert estimate_tokens("这是一段十个汉字的中文文本") == 13

    def test_long_ascii(self) -> None:
        # 100 chars → 25 tokens
        assert estimate_tokens("a" * 100) == 25

    def test_newlines_count_as_ascii(self) -> None:
        # "\n" 计入 ASCII；"a\nb" = 3 chars → 3//4 = 0
        assert estimate_tokens("a\nb") == 0

    def test_monotonic_with_length(self) -> None:
        """更长的文本估算 token 数不减少（近似单调性）。"""
        short = estimate_tokens("short text")
        long_ = estimate_tokens("this is a much longer text to estimate tokens for")
        assert long_ >= short

    def test_cjk_vs_ascii_density(self) -> None:
        """同长度 CJK 比 ASCII 估算更多 token（密度差异）。"""
        cjk = estimate_tokens("中" * 100)
        ascii_ = estimate_tokens("a" * 100)
        assert cjk > ascii_
