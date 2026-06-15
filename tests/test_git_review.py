from __future__ import annotations

import pytest

from cscode.git.review import GitReview


class TestGitReview:
    def test_init(self) -> None:
        review = GitReview()
        assert review is not None
