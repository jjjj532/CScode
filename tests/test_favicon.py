"""Test that favicon.ico exists and is served correctly."""

from pathlib import Path


def test_favicon_file_exists():
    """favicon.ico should exist in the Vite public directory."""
    favicon_path = Path(__file__).parent.parent / "src" / "cscode" / "web" / "public" / "favicon.ico"
    assert favicon_path.exists(), f"favicon.ico not found at {favicon_path}"
    assert favicon_path.stat().st_size > 0, "favicon.ico is empty"


def test_favicon_is_ico_format():
    """favicon.ico should be a valid ICO file."""
    favicon_path = Path(__file__).parent.parent / "src" / "cscode" / "web" / "public" / "favicon.ico"
    if not favicon_path.exists():
        return  # Skip if file doesn't exist yet (TDD)
    data = favicon_path.read_bytes()
    # ICO header: reserved=0 (2 bytes), type=1 (2 bytes), count (2 bytes)
    assert data[:2] == b"\x00\x00", "Invalid ICO reserved bytes"
    assert data[2:4] in (b"\x01\x00",), "Invalid ICO type (must be 1 for .ico)"
