"""Debounce and event coalescing engine for Continuum Phase 4.2.

Coalesces high-frequency file event bursts, atomic editor save sequences,
and duplicate modifications into bounded, debounced batches.
"""
import threading
import time
import uuid
from typing import Callable, List, Optional, Set

from backend.app.core.logging import get_logger
from backend.app.watcher.contracts import FileEvent, WatchBatch

logger = get_logger("continuum.watcher.debouncer")


class DebounceEngine:
    """Thread-safe event debouncer and coalescing buffer."""

    def __init__(
        self,
        debounce_seconds: float = 0.3,
        max_pending_paths: int = 1000,
        on_batch_ready: Optional[Callable[[WatchBatch], None]] = None,
    ) -> None:
        self.debounce_seconds = max(0.01, debounce_seconds)
        self.max_pending_paths = max(1, max_pending_paths)
        self.on_batch_ready = on_batch_ready

        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._pending_paths: Set[str] = set()
        self._pending_events: List[FileEvent] = []
        self._batch_start_time: Optional[float] = None
        self._stopped: bool = False

    @property
    def pending_count(self) -> int:
        """Current number of unique pending paths."""
        with self._lock:
            return len(self._pending_paths)

    def add_event(self, event: FileEvent) -> None:
        """Add a normalized FileEvent to the coalescing buffer."""
        batch_to_dispatch: Optional[WatchBatch] = None

        with self._lock:
            if self._stopped:
                return

            if self._batch_start_time is None:
                self._batch_start_time = time.time()

            # Record affected paths
            self._pending_paths.add(event.path)
            if event.old_path:
                self._pending_paths.add(event.old_path)

            self._pending_events.append(event)

            # Backpressure check: if pending paths exceed maximum capacity, flush immediately
            if len(self._pending_paths) >= self.max_pending_paths:
                logger.info(
                    f"Backpressure limit reached ({len(self._pending_paths)} paths). Forcing immediate flush."
                )
                batch_to_dispatch = self._create_batch_locked()
            else:
                # Cancel existing trailing timer and schedule fresh one
                self._reschedule_timer_locked()

        # Dispatch outside the lock to prevent deadlock
        if batch_to_dispatch and self.on_batch_ready:
            try:
                self.on_batch_ready(batch_to_dispatch)
            except Exception as err:
                logger.error(f"Error in on_batch_ready callback: {err}")

    def _reschedule_timer_locked(self) -> None:
        """Cancel existing timer and schedule a new trailing timer (must hold self._lock)."""
        if self._timer:
            self._timer.cancel()
            self._timer = None

        if not self._stopped:
            self._timer = threading.Timer(self.debounce_seconds, self._on_timer_fired)
            self._timer.daemon = True
            self._timer.start()

    def _on_timer_fired(self) -> None:
        """Invoked when the trailing debounce window elapses with no new events."""
        batch_to_dispatch: Optional[WatchBatch] = None

        with self._lock:
            if self._stopped:
                return
            batch_to_dispatch = self._create_batch_locked()

        if batch_to_dispatch and self.on_batch_ready:
            try:
                self.on_batch_ready(batch_to_dispatch)
            except Exception as err:
                logger.error(f"Error in on_batch_ready callback: {err}")

    def _create_batch_locked(self) -> Optional[WatchBatch]:
        """Create a WatchBatch and reset pending buffers (must hold self._lock)."""
        if self._timer:
            self._timer.cancel()
            self._timer = None

        if not self._pending_paths:
            self._batch_start_time = None
            return None

        batch = WatchBatch(
            batch_id=f"batch_{uuid.uuid4().hex[:8]}",
            affected_paths=set(self._pending_paths),
            events=list(self._pending_events),
            created_at=self._batch_start_time or time.time(),
            flushed_at=time.time(),
        )

        self._pending_paths.clear()
        self._pending_events.clear()
        self._batch_start_time = None

        logger.debug(
            f"Debounce window closed: produced {batch.batch_id} with {batch.paths_count} paths"
        )
        return batch

    def flush(self) -> Optional[WatchBatch]:
        """Manually flush all currently pending events immediately."""
        batch_to_dispatch: Optional[WatchBatch] = None

        with self._lock:
            batch_to_dispatch = self._create_batch_locked()

        if batch_to_dispatch and self.on_batch_ready:
            try:
                self.on_batch_ready(batch_to_dispatch)
            except Exception as err:
                logger.error(f"Error in on_batch_ready callback: {err}")

        return batch_to_dispatch

    def stop(self) -> None:
        """Stop the debouncer and cancel any active timer."""
        with self._lock:
            self._stopped = True
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._pending_paths.clear()
            self._pending_events.clear()
            self._batch_start_time = None
