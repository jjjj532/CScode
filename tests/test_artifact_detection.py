"""P1-back: regression tests for _collect_new_artifacts.

The E2E report found generated Excel files were written to /tmp (outside
OUTPUTS_DIR) and never surfaced. _collect_new_artifacts scans OUTPUTS_DIR
plus an extension-whitelisted top level of /tmp so such files reach the
frontend via file_created events.
"""

from __future__ import annotations

import os
import time

import pytest

from cscode.server.app import OUTPUT_ARTIFACT_EXTENSIONS, _collect_new_artifacts


@pytest.mark.asyncio
async def test_artifact_extensions_whitelist_contains_documents() -> None:
    assert ".xlsx" in OUTPUT_ARTIFACT_EXTENSIONS
    assert ".pdf" in OUTPUT_ARTIFACT_EXTENSIONS
    assert ".csv" in OUTPUT_ARTIFACT_EXTENSIONS
    assert ".py" not in OUTPUT_ARTIFACT_EXTENSIONS


@pytest.mark.asyncio
async def test_collect_new_artifacts_scans_outputs_dir(tmp_path, monkeypatch) -> None:
    from cscode.server import app as app_mod

    monkeypatch.setattr(app_mod, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(app_mod, "TMP_SCAN_DIR", tmp_path / "empty-tmp")
    before = time.time()
    f1 = tmp_path / "report.xlsx"
    f1.write_bytes(b"PK")
    f2 = tmp_path / "stale.txt"
    f2.write_text("old")
    os.utime(f2, (before - 60, before - 60))

    found = _collect_new_artifacts(before)
    assert "report.xlsx" in found
    assert "stale.txt" not in found


@pytest.mark.asyncio
async def test_collect_new_artifacts_tmp_whitelist(tmp_path, monkeypatch) -> None:
    """/tmp artifacts are only picked up when they match the whitelist."""
    from cscode.server import app as app_mod

    tmp_scan = tmp_path / "scan-tmp"
    tmp_scan.mkdir()
    monkeypatch.setattr(app_mod, "OUTPUTS_DIR", tmp_path / "empty-outputs")
    monkeypatch.setattr(app_mod, "TMP_SCAN_DIR", tmp_scan)

    before = time.time()
    (tmp_scan / "数据表.xlsx").write_bytes(b"PK")
    (tmp_scan / "notes.log").write_text("noise")

    found = _collect_new_artifacts(before)
    assert "数据表.xlsx" in found
    assert "notes.log" not in found


@pytest.mark.asyncio
async def test_collect_new_artifacts_deduplicates_across_dirs(tmp_path, monkeypatch) -> None:
    """Same filename in OUTPUTS_DIR and /tmp is reported once."""
    from cscode.server import app as app_mod

    monkeypatch.setattr(app_mod, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(app_mod, "TMP_SCAN_DIR", tmp_path)
    before = time.time()
    (tmp_path / "dup.xlsx").write_bytes(b"PK")

    found = _collect_new_artifacts(before)
    assert found.count("dup.xlsx") == 1