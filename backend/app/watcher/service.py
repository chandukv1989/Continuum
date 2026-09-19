"""Unified filesystem watcher service for Continuum workspaces.

Provides complete lifecycle management:
- Clean start(), stop(), and restart behavior
- Safe against repeated start/stop invocations
- Thread cleanup without orphaned observers
- Explicit workspace boundary scoping
- Status reporting and manual flush capabilities
"""
from pathlib import Path
import threading
from typing import Callable, Optional

from backend.app.core.config import ContinuumSettings, get_settings
from backend.app.core.logging import get_logger
from backend.app.scanner.contracts import IncrementalScanResult
from backend.app.scanner.incremental import IncrementalRepositoryScanner
from backend.app.watcher.contracts import WatcherStatus
from backend.app.watcher.coordinator import WatchEventCoordinator
from backend.app.watcher.debouncer import DebounceEngine
from backend.app.watcher.normalizer import EventNormalizer
from backend.app.watcher.observer import (
    ContinuumFileSystemEventHandler,
    ContinuumObserverAdapter,
)
from backend.app.workspace.context import WorkspaceContext

logger = get_logger("continuum.watcher.service")


class FilesystemWatcherService:
    """Complete lifecycle manager for workspace filesystem observation."""

    def __init__(
        self,
        context: WorkspaceContext,
        scanner: IncrementalRepositoryScanner,
        settings: Optional[ContinuumSettings] = None,
        on_scan_completed: Optional[Callable[[IncrementalScanResult], None]] = None,
    ) -> None:
        self.context = context
        self.scanner = scanner
        self.settings = settings or get_settings()

        self._lock = threading.Lock()
        self._is_running: bool = False

        # Initialize domain components
        self.normalizer = EventNormalizer(
            workspace_root=self.context.repository_root,
            additional_ignore_patterns=self.settings.scanner_ignore_patterns,
        )

        self.coordinator = WatchEventCoordinator(
            scanner=self.scanner,
            on_scan_completed=on_scan_completed,
        )

        self.debouncer = DebounceEngine(
            debounce_seconds=self.settings.watcher_debounce_seconds,
            max_pending_paths=self.settings.watcher_max_pending_events,
            on_batch_ready=self.coordinator.on_batch_ready,
        )

        self.handler = ContinuumFileSystemEventHandler(
            normalizer=self.normalizer,
            debouncer=self.debouncer,
        )

        self.adapter = ContinuumObserverAdapter(
            workspace_root=self.context.repository_root,
            handler=self.handler,
        )

    @property
    def is_running(self) -> bool:
        """True if the watcher service is active and observer thread is running."""
        with self._lock:
            return self._is_running and self.adapter.is_alive

    def start(self) -> None:
        """Start filesystem observation. Safe against repeated calls."""
        with self._lock:
            if self._is_running:
                logger.debug(f"Watcher already running for {self.context.project_id}")
                return

            logger.info(
                f"Starting FilesystemWatcherService for project '{self.context.project_id}' at '{self.context.repository_root}'"
            )
            try:
                self.adapter.start()
                self._is_running = True
            except Exception as err:
                logger.error(
                    f"Failed to start watchdog observer for '{self.context.repository_root}': {err}",
                    exc_info=True,
                )
                self._is_running = False
                raise

    def stop(self, timeout: float = 3.0) -> None:
        """Stop filesystem observation gracefully. Safe against repeated calls."""
        with self._lock:
            if not self._is_running:
                return

            logger.info(
                f"Stopping FilesystemWatcherService for project '{self.context.project_id}'"
            )
            self._is_running = False

            # Stop debouncer to cancel active timers
            self.debouncer.stop()

            # Stop watchdog observer
            self.adapter.stop(timeout=timeout)

    def flush_and_scan(self) -> Optional[IncrementalScanResult]:
        """Flush any pending debounced events and synchronously trigger an incremental scan."""
        self.debouncer.flush()
        return self.coordinator.trigger_synchronous_scan()

    def get_status(self) -> WatcherStatus:
        """Query current runtime statistics and health."""
        return WatcherStatus(
            is_running=self.is_running,
            is_scanning=self.coordinator.is_scanning,
            project_id=self.context.project_id,
            workspace_root=self.context.repository_root.as_posix(),
            pending_paths_count=self.debouncer.pending_count + self.coordinator.queued_paths_count,
            total_events_received=self.handler.total_raw_events,
            total_batches_processed=self.coordinator.total_batches_processed,
            total_scans_triggered=self.coordinator.total_scans_triggered,
            total_scans_failed=self.coordinator.total_scans_failed,
            last_event_timestamp=None,
            last_scan_timestamp=self.coordinator.last_scan_timestamp,
            last_error=self.coordinator.last_error,
        )
