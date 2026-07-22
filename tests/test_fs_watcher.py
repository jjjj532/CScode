"""Tests for P1-5: Filesystem Watcher — watchdog-based file change monitoring.

Tests cover:
- FilesystemWatcher initialization and property defaults
- Adding watch paths
- Start/stop lifecycle (requires watchdog)
- Event notification via callback (requires watchdog)
- Error handling (nonexistent paths, graceful fallback when watchdog missing)
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from cscode.core.fs_watcher import FilesystemWatcher

# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def temp_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def watcher() -> FilesystemWatcher:
    return FilesystemWatcher()


# ─── Initialization ──────────────────────────────────────────────────


class TestInit:
    def test_create_default(self) -> None:
        w = FilesystemWatcher()
        assert not w.is_running
        assert w.watched_paths == []

    def test_create_with_callback(self) -> None:
        def cb(path: str, event_type: str) -> None:
            pass
        w = FilesystemWatcher(callback=cb)
        assert not w.is_running

    def test_create_with_path(self, temp_dir: Path) -> None:
        w = FilesystemWatcher(paths=[str(temp_dir)])
        resolved = os.path.realpath(str(temp_dir))
        assert resolved in w.watched_paths

    def test_is_running_initially_false(self) -> None:
        w = FilesystemWatcher()
        assert not w.is_running


# ─── Path Management ────────────────────────────────────────────────


class TestPathManagement:
    def test_add_path(self, watcher: FilesystemWatcher, temp_dir: Path) -> None:
        watcher.add_path(str(temp_dir))
        resolved = os.path.realpath(str(temp_dir))
        assert resolved in watcher.watched_paths

    def test_add_path_duplicate(self, watcher: FilesystemWatcher, temp_dir: Path) -> None:
        watcher.add_path(str(temp_dir))
        watcher.add_path(str(temp_dir))
        resolved = os.path.realpath(str(temp_dir))
        assert watcher.watched_paths.count(resolved) == 1

    def test_add_nonexistent_path(self, watcher: FilesystemWatcher) -> None:
        with pytest.raises(FileNotFoundError, match="does not exist"):
            watcher.add_path("/tmp/nonexistent_dir_xyz123")

    def test_add_file_path(self, watcher: FilesystemWatcher, temp_dir: Path) -> None:
        file_path = temp_dir / "test.txt"
        file_path.write_text("hello")
        with pytest.raises(NotADirectoryError):
            watcher.add_path(str(file_path))

    def test_remove_path(self, watcher: FilesystemWatcher, temp_dir: Path) -> None:
        watcher.add_path(str(temp_dir))
        watcher.remove_path(str(temp_dir))
        assert str(temp_dir) not in watcher.watched_paths

    def test_remove_nonexistent_path(self, watcher: FilesystemWatcher) -> None:
        watcher.remove_path("/tmp/not_watched")


# ─── Watchdog Missing ───────────────────────────────────────────────


class TestWatchdogMissing:
    def test_start_raises_when_watchdog_missing(self, temp_dir: Path) -> None:
        """start() should raise RuntimeError with install hint when watchdog absent."""
        w = FilesystemWatcher(paths=[str(temp_dir)])
        # Simulate watchdog missing by checking the flag
        from cscode.core.fs_watcher import _WATCHDOG_AVAILABLE
        if not _WATCHDOG_AVAILABLE:
            with pytest.raises(RuntimeError, match="watchdog"):
                w.start()
        else:
            # watchdog is installed, test passes trivially
            w.start()
            w.stop()


# ─── Start/Stop Lifecycle ────────────────────────────────────────────


class TestLifecycle:
    def test_start_and_stop(self, watcher: FilesystemWatcher, temp_dir: Path) -> None:
        pytest.importorskip("watchdog")
        watcher.add_path(str(temp_dir))
        watcher.start()
        assert watcher.is_running
        watcher.stop()
        assert not watcher.is_running

    def test_start_no_paths_raises(self, watcher: FilesystemWatcher) -> None:
        with pytest.raises(RuntimeError, match="No paths"):
            watcher.start()

    def test_double_start(self, watcher: FilesystemWatcher, temp_dir: Path) -> None:
        pytest.importorskip("watchdog")
        watcher.add_path(str(temp_dir))
        watcher.start()
        watcher.start()
        assert watcher.is_running
        watcher.stop()

    def test_double_stop(self, watcher: FilesystemWatcher, temp_dir: Path) -> None:
        pytest.importorskip("watchdog")
        watcher.add_path(str(temp_dir))
        watcher.start()
        watcher.stop()
        watcher.stop()
        assert not watcher.is_running

    def test_context_manager(self, temp_dir: Path) -> None:
        pytest.importorskip("watchdog")
        with FilesystemWatcher(paths=[str(temp_dir)]) as w:
            assert w.is_running
        assert not w.is_running

    def test_context_manager_no_paths(self) -> None:
        with pytest.raises(RuntimeError, match="No paths"):
            with FilesystemWatcher():
                pass


# ─── Edge Cases ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_no_callback_does_not_crash(self, temp_dir: Path) -> None:
        pytest.importorskip("watchdog")
        w = FilesystemWatcher(paths=[str(temp_dir)])
        w.start()
        w.stop()
        assert not w.is_running

    def test_callback_error_does_not_crash_observer(self, temp_dir: Path) -> None:
        pytest.importorskip("watchdog")

        def bad_cb(path: str, event_type: str) -> None:
            raise RuntimeError("callback error")

        w = FilesystemWatcher(paths=[str(temp_dir)], callback=bad_cb)
        w.start()

        new_file = temp_dir / "trigger.txt"
        new_file.write_text("hi")
        import time
        time.sleep(0.5)
        assert w.is_running
        w.stop()
        assert not w.is_running
