"""Serialized scan coordinator integrating Watcher with Phase 4.1 Incremental Scanner.

Guarantees:
1. Strict serialization: No overlapping scans for the same project.
2. Backpressure queue: Batches arriving during an active scan are merged into a pending queue.
3. Content hash authority: Phase 4.1 ChangeDetector determines actual changes.
4. Error isolation: Scan exceptions do not crash the observer or corrupt Code Brain.
"""
import threading
import time
from typing import Callable, Optional, Set

from backend.app.core.logging import get_logger
from backend.app.scanner.contracts import IncrementalScanResult
from backend.app.scanner.incremental import IncrementalRepositoryScanner
from backend.app.watcher.contracts import WatchBatch

logger = get_logger("continuum.watcher.coordinator")


class WatchEventCoordinator:
    """Coordinates debounced filesystem batches and executes serialized incremental scans."""

    def __init__(
        self,
        scanner: IncrementalRepositoryScanner,
        on_scan_completed: Optional[Callable[[IncrementalScanResult], None]] = None,
    ) -> None:
        self.scanner = scanner
        self.on_scan_completed = on_scan_completed

        self._lock = threading.Lock()
        self._scan_mutex = threading.Lock()
        self._is_scanning: bool = False
        self._queued_paths: Set[str] = set()

        # Metrics
        self.total_batches_processed: int = 0
        self.total_scans_triggered: int = 0
        self.total_scans_failed: int = 0
        self.last_scan_timestamp: Optional[float] = None
        self.last_error: Optional[str] = None

    @property
    def is_scanning(self) -> bool:
        """True if an incremental scan is currently in progress."""
        with self._lock:
            return self._is_scanning

    @property
    def queued_paths_count(self) -> int:
        """Number of paths queued while a scan is in progress."""
        with self._lock:
            return len(self._queued_paths)

    def on_batch_ready(self, batch: WatchBatch) -> None:
        """Receive a coalesced batch of affected paths from DebounceEngine."""
        if batch.is_empty:
            return

        with self._lock:
            self.total_batches_processed += 1
            # Merge paths into queued paths
            self._queued_paths.update(batch.affected_paths)
            should_launch = not self._is_scanning

        if should_launch:
            # Launch serialized worker thread
            worker = threading.Thread(
                target=self._run_scan_loop,
                name="ContinuumScanCoordinatorWorker",
                daemon=True,
            )
            worker.start()

    def _run_scan_loop(self) -> None:
        """Execute scans sequentially until no queued paths remain."""
        # Ensure only one worker thread enters the scanning section
        if not self._scan_mutex.acquire(blocking=False):
            return

        try:
            while True:
                with self._lock:
                    if not self._queued_paths:
                        self._is_scanning = False
                        break
                    # Drain pending queued paths for this scan iteration
                    paths_to_evaluate = set(self._queued_paths)
                    self._queued_paths.clear()
                    self._is_scanning = True

                # Execute incremental scan via authoritative Phase 4.1 engine
                self._execute_single_scan(paths_to_evaluate)
        finally:
            with self._lock:
                self._is_scanning = False
            self._scan_mutex.release()

    def _execute_single_scan(self, paths: Set[str]) -> Optional[IncrementalScanResult]:
        """Invoke Phase 4.1 IncrementalRepositoryScanner with error isolation."""
        self.total_scans_triggered += 1
        start_time = time.perf_counter()

        logger.info(
            f"Triggering Phase 4.1 incremental scan for {len(paths)} watched paths",
            extra={"paths_count": len(paths)},
        )

        try:
            # Authoritative Phase 4.1 invocation
            result = self.scanner.scan_incremental(reconcile_project_brain=True)

            self.last_scan_timestamp = time.time()
            self.last_error = None

            duration = round(time.perf_counter() - start_time, 4)
            logger.info(
                f"Incremental scan completed in {duration}s",
                extra={
                    "changes": len(result.change_set.changes),
                    "files_parsed": result.metrics.files_parsed,
                    "symbols": result.metrics.symbols_extracted,
                    "duration": duration,
                },
            )

            if self.on_scan_completed:
                try:
                    self.on_scan_completed(result)
                except Exception as err:
                    logger.error(f"Error in on_scan_completed callback: {err}")

            return result

        except Exception as err:
            self.total_scans_failed += 1
            self.last_error = str(err)
            logger.error(
                f"Incremental scan failed: {err}",
                extra={"error": str(err)},
                exc_info=True,
            )
            return None

    def trigger_synchronous_scan(self) -> Optional[IncrementalScanResult]:
        """Direct synchronous scan invocation (used for testing and manual flushes)."""
        with self._scan_mutex:
            with self._lock:
                paths = set(self._queued_paths)
                self._queued_paths.clear()
                self._is_scanning = True
            try:
                return self._execute_single_scan(paths)
            finally:
                with self._lock:
                    self._is_scanning = False
