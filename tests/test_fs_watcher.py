"""Tests for P1-5: Filesystem Watcher — watchdog-based file change monitoring.

Tests cover:
- FilesystemWatcher initialization and property defaults
- Adding watch paths
- Start/stop lifecycle
- Event notification via callback
- Error handling (nonexistent paths, unwatchable paths)
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
        # Should not raise — silently ignore


# ─── Start/Stop Lifecycle ────────────────────────────────────────────


class TestLifecycle:
    def test_start_and_stop(self, watcher: FilesystemWatcher, temp_dir: Path) -> None:
        watcher.add_path(str(temp_dir))
        watcher.start()
        assert watcher.is_running
        watcher.stop()
        assert not watcher.is_running

    def test_start_no_paths_raises(self, watcher: FilesystemWatcher) -> None:
        with pytest.raises(RuntimeError, match="No paths"):
            watcher.start()

    def test_double_start(self, watcher: FilesystemWatcher, temp_dir: Path) -> None:
        watcher.add_path(str(temp_dir))
        watcher.start()
        watcher.start()
        assert watcher.is_running
        watcher.stop()

    def test_double_stop(self, watcher: FilesystemWatcher, temp_dir: Path) -> None:
        watcher.add_path(str(temp_dir))
        watcher.start()
        watcher.stop()
        watcher.stop()
        assert not watcher.is_running

    def test_context_manager(self, temp_dir: Path) -> None:
        with FilesystemWatcher(paths=[str(temp_dir)]) as w:
            assert w.is_running
        assert not w.is_running

    def test_context_manager_no_paths(self) -> None:
        with pytest.raises(RuntimeError, match="No paths"):
            with FilesystemWatcher():
                pass


# ─── Event Notification ──────────────────────────────────────────────


class TestEventNotification:
    def test_callback_receives_created_event(self, temp_dir: Path) -> None:
        events: list[tuple[str, str]] = []

        def cb(path: str, event_type: str) -> None:
            events.append((path, event_type))

        w = FilesystemWatcher(paths=[str(temp_dir)], callback=cb)
        w.start()
        # Create a file
        new_file = temp_dir / "new_file.txt"
        new_file.write_text("content")
        # Give watchdog time to fire the event
        import time
        time.sleep(0.5)
        w.stop()

        assert len(events) >= 1
        path, event_type = events[0]
        assert "new_file.txt" in path
        assert event_type == "created"

    def test_callback_receives_modified_event(self, temp_dir: Path) -> None:
        events: list[tuple[str, str]] = []

        def cb(path: str, event_type: str) -> None:
            events.append((path, event_type))

        # Pre-create a file
        existing = temp_dir / "existing.txt"
        existing.write_text("initial")
        import time
        time.sleep(0.2)

        w = FilesystemWatcher(paths=[str(temp_dir)], callback=cb)
        w.start()
        # Modify the file
        existing.write_text("modified")
        time.sleep(0.5)
        w.stop()

        modified_events = [e for e in events if e[1] == "modified"]
        assert len(modified_events) >= 1

    def test_callback_receives_deleted_event(self, temp_dir: Path) -> None:
        events: list[tuple[str, str]] = []

        def cb(path: str, event_type: str) -> None:
            events.append((path, event_type))

        # Pre-create a file
        doomed = temp_dir / "to_delete.txt"
        doomed.write_text("bye")
        import time
        time.sleep(0.2)

        w = FilesystemWatcher(paths=[str(temp_dir)], callback=cb)
        w.start()
        # Delete the file
        doomed.unlink()
        time.sleep(0.5)
        w.stop()

        deleted_events = [e for e in events if e[1] == "deleted"]
        assert len(deleted_events) >= 1
        path, _ = deleted_events[0]
        assert "to_delete.txt" in path


# ─── Edge Cases ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_no_callback_does_not_crash(self, temp_dir: Path) -> None:
        """Watcher should work without a callback."""
        w = FilesystemWatcher(paths=[str(temp_dir)])
        w.start()
        w.stop()
        assert not w.is_running

    def test_callback_error_does_not_crash_observer(self, temp_dir: Path) -> None:
        """Callback raising an exception should not stop the observer."""

        def bad_cb(path: str, event_type: str) -> None:
            raise RuntimeError("callback error")

        w = FilesystemWatcher(paths=[str(temp_dir)], callback=bad_cb)
        w.start()

        new_file = temp_dir / "trigger.txt"
        new_file.write_text("hi")
        import time
        time.sleep(0.5)
        # Should still be running despite callback error
        assert w.is_running
        w.stop()
        assert not w.is_running
