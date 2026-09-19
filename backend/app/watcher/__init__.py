"""Watcher domain package for Continuum Phase 4.2.

Provides:
- Internal domain contracts for filesystem events and batches
- Event normalizer and path boundary enforcement
- Debounce and coalescing engine
- Thread-safe scan coordinator integrating with Phase 4.1 incremental scanner
- Watchdog infrastructure observer
- High-level watcher service lifecycle
"""
from backend.app.watcher.contracts import (
    FileEvent,
    FileEventType,
    WatchBatch,
    WatcherStatus,
)
from backend.app.watcher.coordinator import WatchEventCoordinator
from backend.app.watcher.debouncer import DebounceEngine
from backend.app.watcher.normalizer import EventNormalizer
from backend.app.watcher.observer import (
    ContinuumFileSystemEventHandler,
    ContinuumObserverAdapter,
)
from backend.app.watcher.service import FilesystemWatcherService

__all__ = [
    "FileEvent",
    "FileEventType",
    "WatchBatch",
    "WatcherStatus",
    "EventNormalizer",
    "DebounceEngine",
    "WatchEventCoordinator",
    "ContinuumFileSystemEventHandler",
    "ContinuumObserverAdapter",
    "FilesystemWatcherService",
]
