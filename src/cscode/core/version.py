"""Version management — single source of truth for CScode version strings.

Ensures all 7 version locations stay consistent:
  1. src/cscode/__init__.py         (__version__)
  2. src/cscode/server/app.py       (FastAPI version=)
  3. src/cscode/mcp/client.py       ("version" in clientInfo)
  4. src/cscode/mcp/server.py       ("version" in serverInfo)
  5. desktop/src-tauri/tauri.conf.json  ("version" field)
  6. desktop/src-tauri/Cargo.toml      ([package] version)
  7. scripts/build.sh                  (hardcoded version in paths)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent.parent


@dataclass
class VersionResult:
    """Result of checking a single version location."""

    file: str
    expected: str
    actual: str | None
    is_ok: bool = True


# ─── Version sources ────────────────────────────────────────────────────


def get_canonical_version() -> str:
    """Read the authoritative version from ``__init__.py``."""
    init_file = PROJECT_ROOT / "src" / "cscode" / "__init__.py"
    src = init_file.read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', src)
    if m is None:
        msg = f"__version__ not found in {init_file}"
        raise RuntimeError(msg)
    return m.group(1)


_VERSION_PATTERNS: Final[list[tuple[str, str, str]]] = [
    # (relative_path, regex, label)
    ("src/cscode/__init__.py", r'__version__\s*=\s*["\']([^"\']+)["\']', "canonical"),
    ("src/cscode/server/app.py", r'version\s*=\s*["\']([^"\']+)["\']', "FastAPI(version=...)"),
    ("src/cscode/mcp/client.py", r'"version":\s*"([^"]+)"', "MCP client"),
    ("src/cscode/mcp/server.py", r'"version":\s*"([^"]+)"', "MCP server"),
    ("desktop/src-tauri/tauri.conf.json", None, "tauri.conf.json"),
    ("desktop/src-tauri/Cargo.toml", r'^version\s*=\s*"([^"]+)"', "Cargo.toml"),
    ("scripts/build.sh", r"(?:macOS|Linux|Windows)\b.*?([\d.]+)", "build.sh"),
]


def _read_version(rel_path: str, pattern: str | None) -> str | None:
    """Extract a version string from a file. Returns None if not found."""
    full_path = PROJECT_ROOT / rel_path
    if not full_path.exists():
        return None
    raw = full_path.read_text(encoding="utf-8")

    # Special handling: JSON file
    if pattern is None:
        try:
            data = json.loads(raw)
            return data.get("version")
        except (json.JSONDecodeError, KeyError):
            return None

    flags = 0
    if pattern.startswith("^"):
        flags = re.MULTILINE

    m = re.search(pattern, raw, flags)
    return m.group(1) if m else None


# ─── Public API ─────────────────────────────────────────────────────────


def check_consistency() -> list[VersionResult]:
    """Check version consistency across all 7 locations.

    Returns:
        A list of ``VersionResult`` objects, one per checked file.
        Callers should check ``all(r.is_ok for r in results)``.
    """
    expected = get_canonical_version()
    results: list[VersionResult] = []

    for rel_path, pattern, _label in _VERSION_PATTERNS:
        actual = _read_version(rel_path, pattern)
        if actual is None:
            results.append(VersionResult(
                file=rel_path,
                expected=expected,
                actual=None,
                is_ok=False,
            ))
        else:
            results.append(VersionResult(
                file=rel_path,
                expected=expected,
                actual=actual,
                is_ok=actual == expected,
            ))

    return results


def format_check_report(results: list[VersionResult]) -> str:
    """Format consistency check results as a human-readable string."""
    lines: list[str] = []
    all_ok = True

    for r in results:
        if r.is_ok:
            status = "✓"
        else:
            status = "✗"
            all_ok = False
        actual_str = r.actual if r.actual is not None else "(not found)"
        lines.append(f"  {status} {r.file:45s} {actual_str}")

    if all_ok:
        lines.insert(0, f"Version {results[0].expected}: OK")
    else:
        lines.insert(0, f"Version {results[0].expected}: MISMATCH")
        for r in results:
            if not r.is_ok:
                lines.append(
                    f"  → {r.file}: expected {r.expected!r}, got {r.actual!r}"
                )

    return "\n".join(lines)
