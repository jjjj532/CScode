"""Phase 3 cleanup: verify old engine.py is fully removed.

TDD: This test asserts that importing the old engine module FAILS.
It will fail (RED) as long as engine.py exists, and pass (GREEN)
once the file is deleted.
"""

from __future__ import annotations

import pytest


def test_old_engine_module_no_longer_importable() -> None:
    """After Phase 3 cleanup, cscode.core.engine must not exist."""
    with pytest.raises(ImportError, match="No module named.*engine"):
        import cscode.core.engine  # noqa: F401


def test_old_session_manager_no_longer_importable() -> None:
    """After Phase 3 cleanup, cscode.core.session_manager must not exist."""
    with pytest.raises(ImportError, match="No module named.*session_manager"):
        import cscode.core.session_manager  # noqa: F401
