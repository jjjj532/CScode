"""Filesystem Watcher — watchdog-based file change monitoring.

Detects file creation, modification, and deletion events and
notifies registered callbacks for further processing.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

# Type alias for event callbacks
EventCallback = Callable[[str, str], None]


class _ChangeHandler(FileSystemEventHandler):
    """Internal watchdog event handler that delegates to a callback."""

    def __init__(self, callback: EventCallback | None) -> None:
        super().__init__()
        self._callback = callback

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._safe_notify(str(event.src_path), "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._safe_notify(str(event.src_path), "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._safe_notify(str(event.src_path), "deleted")

    def _safe_notify(self, path: str, event_type: str) -> None:
        """Invoke callback, swallowing exceptions so the observer stays alive."""
        cb = self._callback
        if cb is None:
            return
        try:
            cb(path, event_type)
        except Exception:
            logger.exception("Filesystem watcher callback error for %s %s", event_type, path)


class FilesystemWatcher:
    """Monitor filesystem changes using watchdog.

    Usage::

        def on_change(path: str, event_type: str) -> None:
            print(f"{event_type}: {path}")

        with FilesystemWatcher(paths=["/src"], callback=on_change):
            # filesystem is being watched
            ...

    Attributes:
        is_running: Whether the observer is currently active.
        watched_paths: List of directory paths being watched.
    """

    def __init__(
        self,
        paths: list[str] | None = None,
        callback: EventCallback | None = None,
    ) -> None:
        self._paths: list[str] = []
        self._callback = callback
        self._observer = Observer()
        self._handler = _ChangeHandler(callback)
        self._is_running = False

        if paths:
            for p in paths:
                self.add_path(p)

    # ── Properties ──────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def watched_paths(self) -> list[str]:
        return list(self._paths)

    # ── Path Management ─────────────────────────────────────────────

    def add_path(self, path: str) -> None:
        """Add a directory to watch.

        Raises:
            FileNotFoundError: If the path does not exist.
            NotADirectoryError: If the path is not a directory.
        """
        resolved = os.path.realpath(path)
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"Path does not exist: {path}")
        if not os.path.isdir(resolved):
            raise NotADirectoryError(f"Not a directory: {path}")
        if resolved not in self._paths:
            self._paths.append(resolved)

    def remove_path(self, path: str) -> None:
        """Remove a directory from the watch list.

        Silently ignores paths that are not currently watched.
        """
        resolved = os.path.realpath(path)
        if resolved in self._paths:
            self._paths.remove(resolved)

    # ── Lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """Start watching all registered paths.

        Raises:
            RuntimeError: If no paths have been configured.
        """
        if self._is_running:
            logger.debug("FilesystemWatcher already running")
            return
        if not self._paths:
            raise RuntimeError("No paths configured for watching")
        for p in self._paths:
            self._observer.schedule(self._handler, p, recursive=False)
        self._observer.start()
        self._is_running = True
        logger.info("FilesystemWatcher started: %d paths", len(self._paths))

    def stop(self) -> None:
        """Stop watching."""
        if not self._is_running:
            logger.debug("FilesystemWatcher already stopped")
            return
        self._observer.stop()
        self._observer.join()
        self._is_running = False
        logger.info("FilesystemWatcher stopped")

    # ── Context Manager ─────────────────────────────────────────────

    def __enter__(self) -> FilesystemWatcher:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()
