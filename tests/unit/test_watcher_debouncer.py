"""Unit tests for Watcher DebounceEngine and event coalescing."""
import time
from typing import List
import pytest

from backend.app.watcher.contracts import FileEvent, FileEventType, WatchBatch
from backend.app.watcher.debouncer import DebounceEngine


def test_debouncer_coalesces_duplicate_events():
    """Verify multiple rapid events for the same path collapse into a single affected path."""
    dispatched_batches: List[WatchBatch] = []

    debouncer = DebounceEngine(
        debounce_seconds=0.05,
        on_batch_ready=dispatched_batches.append,
    )

    try:
        # Simulate burst of 5 duplicate modifications on A.ts
        for _ in range(5):
            debouncer.add_event(
                FileEvent(event_type=FileEventType.MODIFIED, path="src/A.ts")
            )

        assert debouncer.pending_count == 1

        # Wait for debounce window to elapse
        time.sleep(0.1)

        assert len(dispatched_batches) == 1
        batch = dispatched_batches[0]
        assert batch.paths_count == 1
        assert "src/A.ts" in batch.affected_paths
        assert len(batch.events) == 5
    finally:
        debouncer.stop()


def test_debouncer_coalesces_multi_file_burst():
    """Verify burst across multiple files is grouped into one batch."""
    dispatched_batches: List[WatchBatch] = []

    debouncer = DebounceEngine(
        debounce_seconds=0.05,
        on_batch_ready=dispatched_batches.append,
    )

    try:
        debouncer.add_event(
            FileEvent(event_type=FileEventType.CREATED, path="src/A.ts")
        )
        debouncer.add_event(
            FileEvent(event_type=FileEventType.MODIFIED, path="src/A.ts")
        )
        debouncer.add_event(
            FileEvent(event_type=FileEventType.MODIFIED, path="src/B.py")
        )
        debouncer.add_event(
            FileEvent(event_type=FileEventType.DELETED, path="src/C.ts")
        )

        assert debouncer.pending_count == 3

        time.sleep(0.1)

        assert len(dispatched_batches) == 1
        batch = dispatched_batches[0]
        assert batch.paths_count == 3
        assert batch.affected_paths == {"src/A.ts", "src/B.py", "src/C.ts"}
    finally:
        debouncer.stop()


def test_debouncer_atomic_save_pattern():
    """Simulate common IDE atomic save: create temp, modify temp, rename to target."""
    dispatched_batches: List[WatchBatch] = []

    debouncer = DebounceEngine(
        debounce_seconds=0.05,
        on_batch_ready=dispatched_batches.append,
    )

    try:
        # 1. Editor writes temp file
        debouncer.add_event(
            FileEvent(event_type=FileEventType.CREATED, path="src/main.ts.tmp")
        )
        # 2. Editor modifies temp file
        debouncer.add_event(
            FileEvent(event_type=FileEventType.MODIFIED, path="src/main.ts.tmp")
        )
        # 3. Editor renames temp file to original file
        debouncer.add_event(
            FileEvent(
                event_type=FileEventType.MOVED,
                path="src/main.ts",
                old_path="src/main.ts.tmp",
            )
        )

        time.sleep(0.1)

        assert len(dispatched_batches) == 1
        batch = dispatched_batches[0]
        # Both temp and target are tracked so ChangeDetector can evaluate workspace state
        assert "src/main.ts" in batch.affected_paths
        assert "src/main.ts.tmp" in batch.affected_paths
    finally:
        debouncer.stop()


def test_debouncer_backpressure_forces_immediate_flush():
    """Verify that exceeding max_pending_paths triggers immediate flush without waiting for timer."""
    dispatched_batches: List[WatchBatch] = []

    debouncer = DebounceEngine(
        debounce_seconds=10.0,  # Deliberately huge timer
        max_pending_paths=5,    # Low threshold for testing
        on_batch_ready=dispatched_batches.append,
    )

    try:
        # Add 5 distinct paths
        for i in range(5):
            debouncer.add_event(
                FileEvent(event_type=FileEventType.CREATED, path=f"src/file_{i}.ts")
            )

        # Should flush immediately upon reaching 5
        assert len(dispatched_batches) == 1
        assert dispatched_batches[0].paths_count == 5
        assert debouncer.pending_count == 0
    finally:
        debouncer.stop()


def test_debouncer_manual_flush_and_stop():
    """Verify manual flush() and stop() methods."""
    dispatched_batches: List[WatchBatch] = []

    debouncer = DebounceEngine(
        debounce_seconds=10.0,
        on_batch_ready=dispatched_batches.append,
    )

    try:
        debouncer.add_event(
            FileEvent(event_type=FileEventType.MODIFIED, path="src/manual.ts")
        )
        assert len(dispatched_batches) == 0

        batch = debouncer.flush()
        assert batch is not None
        assert "src/manual.ts" in batch.affected_paths
        assert len(dispatched_batches) == 1

        # Second flush on empty buffer returns None
        assert debouncer.flush() is None

        debouncer.stop()
        # Adding event after stop is safely ignored
        debouncer.add_event(
            FileEvent(event_type=FileEventType.MODIFIED, path="src/ignored.ts")
        )
        assert debouncer.pending_count == 0
    finally:
        debouncer.stop()
