"""Tests for version management: consistency across 7 files + CLI.

TDD: these tests define the contract before implementation.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ─── Helpers ─────────────────────────────────────────────────────────────


def get_python_version() -> str:
    """Read __version__ from src/cscode/__init__.py."""
    init_file = PROJECT_ROOT / "src" / "cscode" / "__init__.py"
    src = init_file.read_text()
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', src)
    assert m is not None, f"__version__ not found in {init_file}"
    return m.group(1)


def get_file_version(pattern: str, path: str, group: int = 1) -> str:
    """Extract a version string from a file using a regex."""
    full_path = PROJECT_ROOT / path
    src = full_path.read_text()
    m = re.search(pattern, src)
    assert m is not None, f"Version pattern not found in {path}"
    return m.group(group)


# ─── Version string format ───────────────────────────────────────────────


class TestVersionFormat:
    def test_version_format(self) -> None:
        """__version__ must be MAJOR.MINOR.PATCH."""
        v = get_python_version()
        assert re.match(r"^\d+\.\d+\.\d+$", v), f"Bad version format: {v}"


# ─── Consistency across files ────────────────────────────────────────────


class TestVersionConsistency:
    def _check(self, path: str, label: str) -> str:
        """Assert version in *path* matches __init__.py, return the value."""
        expected = get_python_version()

        if path == "src/cscode/mcp/client.py":
            v = get_file_version(
                r'"version":\s*"([^"]+)"',
                path,
            )
        elif path == "src/cscode/mcp/server.py":
            v = get_file_version(
                r'"version":\s*"([^"]+)"',
                path,
            )
        elif path.endswith("tauri.conf.json"):
            data = json.loads((PROJECT_ROOT / path).read_text())
            v = data["version"]
        elif path.endswith("Cargo.toml"):
            v = get_file_version(
                r'version\s*=\s*"([^"]+)"',
                path,
            )
        elif path.endswith(".sh"):
            v = get_file_version(
                r"(?:macOS|Linux|Windows).*?([\d.]+)",
                path,
            )
        elif path.endswith("app.py") or path.endswith("/__init__.py"):
            v = get_file_version(
                r'version\s*=\s*["\']([^"\']+)["\']',
                path,
            )
        else:
            pytest.fail(f"Unknown file type: {path}")

        assert v == expected, (
            f"[{label}] {path}: expected {expected!r}, got {v!r}"
        )
        return v

    def test_version_consistency_app(self) -> None:
        self._check("src/cscode/server/app.py", "FastAPI(version=...)")

    def test_version_consistency_mcp_client(self) -> None:
        self._check("src/cscode/mcp/client.py", "MCP client version")

    def test_version_consistency_mcp_server(self) -> None:
        self._check("src/cscode/mcp/server.py", "MCP server version")

    def test_version_consistency_tauri_conf(self) -> None:
        self._check("desktop/src-tauri/tauri.conf.json", "tauri.conf.json")

    def test_version_consistency_cargo(self) -> None:
        self._check("desktop/src-tauri/Cargo.toml", "Cargo.toml")

    def test_version_consistency_build_sh(self) -> None:
        self._check("scripts/build.sh", "scripts/build.sh")


# ─── Core version module ─────────────────────────────────────────────────


class TestVersionManager:
    def test_check_returns_ok_when_consistent(self) -> None:
        from cscode.core.version import check_consistency

        results = check_consistency()
        assert len(results) > 4  # at least 5 files checked
        all_ok = all(r.is_ok for r in results)
        if not all_ok:
            details = "\n".join(
                f"  {r.file}: expected {r.expected!r}, got {r.actual!r}"
                for r in results if not r.is_ok
            )
            pytest.fail(f"Version mismatch:\n{details}")
        assert all_ok

    def test_check_consistency_result_count(self) -> None:
        from cscode.core.version import check_consistency

        results = check_consistency()
        # Must cover the 7 known locations
        expected_files = [
            "src/cscode/__init__.py",
            "src/cscode/server/app.py",
            "src/cscode/mcp/client.py",
            "src/cscode/mcp/server.py",
            "desktop/src-tauri/tauri.conf.json",
            "desktop/src-tauri/Cargo.toml",
            "scripts/build.sh",
        ]
        for ef in expected_files:
            matched = any(ef in r.file for r in results)
            assert matched, f"Missing check for {ef}"


# ─── CLI ─────────────────────────────────────────────────────────────────


class TestVersionCLI:
    def test_version_command_output(self) -> None:
        """cs version prints the current version."""
        result = subprocess.run(
            [sys.executable, "-m", "cscode", "version"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        expected = get_python_version()
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert expected in result.stdout, (
            f"Expected {expected!r} in stdout: {result.stdout}"
        )

    def test_version_check_ok(self) -> None:
        """cs version --check exits 0 when consistent."""
        result = subprocess.run(
            [sys.executable, "-m", "cscode", "version", "--check"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, (
            f"stderr: {result.stderr}\nstdout: {result.stdout}"
        )
        assert "OK" in result.stdout

    def test_version_check_detects_mismatch(self) -> None:
        """cs version --check exits 1 when inconsistent."""
        # Temporarily create a file with a wrong version
        # We'll use a side-by-side approach: create a mock version.conf
        # Simulate a mismatch: patch _VERSION_PATTERNS to check a bogus file
        import cscode.core.version as vmod
        from cscode.core.version import check_consistency
        original_patterns = vmod._VERSION_PATTERNS
        bogus_path = PROJECT_ROOT / "_version_test_tmp"
        try:
            bogus_path.write_text('version = "9.9.9"', encoding="utf-8")
            vmod._VERSION_PATTERNS = [
                ("_version_test_tmp", r'version\s*=\s*"([^"]+)"', "bogus"),
            ]
            results = check_consistency()
            mismatches = [r for r in results if not r.is_ok]
            assert len(mismatches) >= 1, "Should detect at least one mismatch"
        finally:
            vmod._VERSION_PATTERNS = original_patterns
            if bogus_path.exists():
                bogus_path.unlink()
