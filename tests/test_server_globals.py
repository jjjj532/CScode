"""Regression tests for module-level server globals.

Verifies that server module-level singletons (_plugin_host, _event_store, ...)
have proper module-level declarations so that code paths that run WITHOUT the
FastAPI lifespan (unit tests, alternate entry points, future refactors) do not
raise NameError.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _get_temp_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="cscode_global_test_"))
    return temp_dir / "test_cscode.db"


def test_plugin_host_has_module_level_declaration():
    """Regression: _plugin_host was previously only assigned inside lifespan(),
    so mypy reported name-defined and any non-lifespan code path would NameError.

    It must have a module-level declaration (like _event_store, _tool_registry).
    """
    db_path = _get_temp_db_path()
    os.environ["CSCODE_DB_PATH"] = str(db_path)
    try:
        import cscode.server.app as app_mod

        # Module-level attribute must exist (mypy name-defined regression)
        assert hasattr(app_mod, "_plugin_host")

        # After running lifespan it must be a PluginHost instance
        from fastapi import FastAPI

        app = FastAPI()
        import asyncio

        async def run_lifespan() -> None:
            async with app_mod.lifespan(app):
                assert app_mod._plugin_host is not None, (
                    "lifespan must initialize _plugin_host"
                )

        asyncio.run(run_lifespan())
    finally:
        if db_path.exists():
            db_path.unlink()
