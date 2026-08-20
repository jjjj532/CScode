"""Token estimation for context compression.

Provides a lightweight, dependency-free approximation of token counting
aligned with OpenCode's `Token.estimate` semantics:

- ASCII / Latin characters: ~4 chars per token (0.25 token/char)
- CJK / wide characters: ~1 token per char
- Empty string: 0 tokens

This is a *rough* estimate used to decide *when* to compress and how many
tokens to keep. It deliberately avoids a heavyweight tokenizer dependency;
documented approximation precision is part of the contract (see
`tests/test_token_estimate.py`).
"""

from __future__ import annotations

from typing import Final

#: 4 ASCII chars ≈ 1 token
_ASCII_CHARS_PER_TOKEN: Final[int] = 4


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in ``text``.

    Rules:
      - empty string → 0
      - CJK / wide characters (ord > 0x2E7F) → 1 token each
      - all other characters (ASCII etc.) → len / 4, integer floor

    The floor division means short ASCII strings may estimate to 0 tokens;
    this is intentional and matches OpenCode's token-estimate rounding.
    """
    if not text:
        return 0

    wide = sum(1 for ch in text if ord(ch) > 0x2E7F)
    narrow = len(text) - wide
    return wide + narrow // _ASCII_CHARS_PER_TOKEN
