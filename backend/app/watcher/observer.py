"""Watchdog infrastructure adapter for Continuum Phase 4.2.

Adapts raw Python watchdog events into normalized Continuum domain events
without leaking watchdog-specific types to the rest of the application.
"""
from pathlib import Path
from typing import Optional

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from backend.app.core.logging import get_logger
from backend.app.watcher.contracts import FileEventType
from backend.app.watcher.debouncer import DebounceEngine
from backend.app.watcher.normalizer import EventNormalizer

logger = get_logger("continuum.watcher.observer")


class ContinuumFileSystemEventHandler(FileSystemEventHandler):
    """Bridges watchdog filesystem notifications to Continuum EventNormalizer and DebounceEngine."""

    def __init__(
        self,
        normalizer: EventNormalizer,
        debouncer: DebounceEngine,
    ) -> None:
        super().__init__()
        self.normalizer = normalizer
        self.debouncer = debouncer
        self.total_raw_events: int = 0

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle created files or directories."""
        self._dispatch(
            event_type=FileEventType.CREATED,
            src_path=event.src_path,
            is_directory=event.is_directory,
        )

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle modified files or directories."""
        self._dispatch(
            event_type=FileEventType.MODIFIED,
            src_path=event.src_path,
            is_directory=event.is_directory,
        )

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle deleted files or directories."""
        self._dispatch(
            event_type=FileEventType.DELETED,
            src_path=event.src_path,
            is_directory=event.is_directory,
        )

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle moved/renamed files or directories."""
        dest_path = getattr(event, "dest_path", None)
        self._dispatch(
            event_type=FileEventType.MOVED,
            src_path=event.src_path,
            dest_path=dest_path,
            is_directory=event.is_directory,
        )

    def _dispatch(
        self,
        event_type: FileEventType,
        src_path: str,
        dest_path: Optional[str] = None,
        is_directory: bool = False,
    ) -> None:
        """Normalize event and route to debouncer with error isolation."""
        self.total_raw_events += 1
        try:
            norm_event = self.normalizer.normalize_event(
                event_type=event_type,
                src_path=src_path,
                dest_path=dest_path,
                is_directory=is_directory,
            )
            if norm_event is not None:
                self.debouncer.add_event(norm_event)
        except Exception as err:
            logger.warning(
                f"Error processing raw watchdog event ({event_type.value}, {src_path}): {err}",
                exc_info=False,
            )


class ContinuumObserverAdapter:
    """Encapsulates watchdog Observer lifecycle and configuration."""

    def __init__(
        self,
        workspace_root: Path,
        handler: ContinuumFileSystemEventHandler,
    ) -> None:
        self.workspace_root = workspace_root
        self.handler = handler
        self._observer: Optional[Observer] = None
        self._is_alive: bool = False

    @property
    def is_alive(self) -> bool:
        """Return True if background observer thread is actively running."""
        return self._is_alive and self._observer is not None and self._observer.is_alive()

    def start(self) -> None:
        """Start the background watchdog observer thread."""
        if self.is_alive:
            return

        self._observer = Observer()
        self._observer.schedule(
            self.handler,
            path=str(self.workspace_root),
            recursive=True,
        )
        self._observer.daemon = True
        self._observer.start()
        self._is_alive = True
        logger.info(f"Watchdog observer started for '{self.workspace_root}'")

    def stop(self, timeout: float = 3.0) -> None:
        """Stop the background watchdog observer thread gracefully."""
        if not self._is_alive or self._observer is None:
            self._is_alive = False
            return

        try:
            self._observer.stop()
            self._observer.join(timeout=timeout)
        except Exception as err:
            logger.warning(f"Error while stopping watchdog observer: {err}")
        finally:
            self._observer = None
            self._is_alive = False
            logger.info(f"Watchdog observer stopped for '{self.workspace_root}'")
