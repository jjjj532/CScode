from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_package_importable():
    """验证包可以被导入且有版本号"""
    import cscode
    assert hasattr(cscode, "__version__")
    assert isinstance(cscode.__version__, str)
    assert len(cscode.__version__) > 0


def test_cli_help():
    """验证 cs --help 输出帮助信息"""
    result = subprocess.run(
        [sys.executable, "-m", "cscode", "--help"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0
    assert "CScode" in result.stdout or "cscode" in result.stdout.lower()
    assert "help" in result.stdout.lower()


def test_cli_version():
    """验证 cs --version 输出版本号"""
    result = subprocess.run(
        [sys.executable, "-m", "cscode", "--version"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0
    assert "0.2.10" in result.stdout


def test_pyproject_toml_exists():
    """验证 pyproject.toml 存在且格式正确"""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    assert pyproject.exists()
    content = pyproject.read_text()
    assert "[project]" in content
    assert 'name = "cscode"' in content


def test_project_structure():
    """验证关键目录结构存在"""
    dirs = [
        PROJECT_ROOT / "src" / "cscode",
        PROJECT_ROOT / "tests",
        PROJECT_ROOT / "src" / "cscode" / "core",
        PROJECT_ROOT / "src" / "cscode" / "tools",
        PROJECT_ROOT / "src" / "cscode" / "providers",
        PROJECT_ROOT / "src" / "cscode" / "storage",
    ]
    for d in dirs:
        assert d.exists(), f"Directory does not exist: {d}"


def test_python_version_compatible():
    """验证 Python 版本 >= 3.11"""
    assert sys.version_info >= (3, 11), f"Python 3.11+ required, got {sys.version_info}"
