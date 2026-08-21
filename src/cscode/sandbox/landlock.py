"""Landlock LSM bindings — OS-level file system sandboxing (G-12, Linux 5.13+).

Provides ctypes wrappers for Landlock syscalls to restrict file system access
in child processes. Falls back gracefully on unsupported platforms.

Spec reference: §6.6 (G-12 OS sandbox, Route B)
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import struct
import sys
from pathlib import Path

from cscode.utils.logging import get_logger

logger = get_logger(__name__)

# Landlock ABI version constants (from linux/landlock.h)
LANDLOCK_ABI_VERSION = 1
LANDLOCK_ACCESS_FS_EXECUTE = 1 << 0
LANDLOCK_ACCESS_FS_WRITE_FILE = 1 << 1
LANDLOCK_ACCESS_FS_READ_FILE = 1 << 2
LANDLOCK_ACCESS_FS_READ_DIR = 1 << 3
LANDLOCK_RULE_PATH_BENEATH = 1 << 0
LANDLOCK_ACCESS_FS_READ = (
    LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR
)
LANDLOCK_ACCESS_FS_WRITE = LANDLOCK_ACCESS_FS_WRITE_FILE

PR_SET_NO_NEW_PRIVS = 38

_libc: ctypes.CDLL | None = None
_landlock_available: bool | None = None


def _load_libc() -> ctypes.CDLL | None:
    global _libc
    if _libc is not None:
        return _libc
    libc_path = ctypes.util.find_library("c")
    if libc_path is None:
        logger.debug("Landlock: libc not found")
        return None
    try:
        _libc = ctypes.CDLL(libc_path, use_errno=True)
        return _libc
    except OSError as e:
        logger.debug("Landlock: failed to load libc: %s", e)
        return None


def _set_no_new_privs() -> bool:
    libc = _load_libc()
    if libc is None:
        return False
    result = libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
    return bool(result == 0)


def _create_ruleset(
    allowed_fs_read: int,
    allowed_fs_write: int,
) -> int:
    libc = _load_libc()
    if libc is None:
        raise OSError("libc not available")
    attr = struct.pack(
        "QQI",
        allowed_fs_read,
        allowed_fs_write,
        0,
    )
    attr_size = len(attr)
    attr_p = ctypes.create_string_buffer(attr, attr_size)
    fd = libc.landlock_create_ruleset(attr_p, attr_size, 0)
    if fd < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    return int(fd)


def _add_path_beneath_rule(
    ruleset_fd: int,
    path: Path,
    allowed_access: int,
) -> None:
    libc = _load_libc()
    if libc is None:
        raise OSError("libc not available")
    rule_type = LANDLOCK_RULE_PATH_BENEATH
    rule_struct = ctypes.create_string_buffer(
        struct.pack("QQi", rule_type, 0, allowed_access),
        16,
    )
    result = libc.landlock_add_rule(ruleset_fd, rule_type, rule_struct, 0)
    if result < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))


def _add_read_path_rule(ruleset_fd: int, path: Path) -> None:
    _add_path_beneath_rule(ruleset_fd, path, LANDLOCK_ACCESS_FS_READ)


def _add_write_path_rule(ruleset_fd: int, path: Path) -> None:
    _add_path_beneath_rule(ruleset_fd, path, LANDLOCK_ACCESS_FS_WRITE)


def is_landlock_available() -> bool:
    global _landlock_available
    if _landlock_available is not None:
        return _landlock_available
    if sys.platform != "linux":
        _landlock_available = False
        return False
    libc = _load_libc()
    if libc is None:
        _landlock_available = False
        return False
    if not _set_no_new_privs():
        _landlock_available = False
        return False
    try:
        fd = _create_ruleset(LANDLOCK_ACCESS_FS_READ, 0)
        os.close(fd)
        _landlock_available = True
        logger.debug("Landlock: available (ABI v%d)", LANDLOCK_ABI_VERSION)
        return True
    except OSError:
        _landlock_available = False
        return False


def apply_landlock_rules(
    allowed_read: list[str],
    allowed_write: list[str],
) -> None:
    if not is_landlock_available():
        logger.debug("Landlock: not available, skipping")
        return

    if not _set_no_new_privs():
        logger.warning("Landlock: prctl(PR_SET_NO_NEW_PRIVS) failed")
        return

    fs_read = LANDLOCK_ACCESS_FS_READ
    fs_write = LANDLOCK_ACCESS_FS_WRITE
    try:
        ruleset_fd = _create_ruleset(fs_read, fs_write)
    except OSError as e:
        logger.warning("Landlock: failed to create ruleset: %s", e)
        return

    errors: list[str] = []
    for path_str in allowed_read:
        p = Path(path_str)
        if p.exists():
            try:
                _add_read_path_rule(ruleset_fd, p)
            except OSError as e:
                errors.append(f"read {path_str}: {e}")

    for path_str in allowed_write:
        p = Path(path_str)
        try:
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
            _add_write_path_rule(ruleset_fd, p)
        except OSError as e:
            errors.append(f"write {path_str}: {e}")

    if errors:
        logger.warning("Landlock: some rules failed: %s", "; ".join(errors))

    try:
        os.close(ruleset_fd)
    except OSError:
        pass
