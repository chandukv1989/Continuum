"""Unit tests for WatchEventCoordinator concurrency and error isolation."""
import threading
import time
from unittest.mock import MagicMock
import pytest

from backend.app.scanner.contracts import (
    ChangeSet,
    IncrementalScanResult,
    ScanMetrics,
)
from backend.app.watcher.contracts import FileEvent, FileEventType, WatchBatch
from backend.app.watcher.coordinator import WatchEventCoordinator


def _make_mock_result(project_id="test_proj"):
    return IncrementalScanResult(
        project_id=project_id,
        canonical_root="/tmp/repo",
        symbols_db_path="/tmp/repo/symbols.db",
        change_set=ChangeSet(changes=[], detection_source="test"),
        metrics=ScanMetrics(
            files_discovered=1,
            files_filtered=0,
            files_parsed=0,
            parse_failures=0,
            symbols_extracted=0,
            relationships_extracted=0,
            scan_duration_seconds=0.01,
            persistence_duration_seconds=0.005,
        ),
    )


def test_coordinator_serialized_execution():
    """Verify that multiple incoming batches never execute scans concurrently."""
    concurrent_executions = 0
    max_concurrent = 0
    scan_count = 0
    lock = threading.Lock()

    mock_scanner = MagicMock()

    def slow_scan(*args, **kwargs):
        nonlocal concurrent_executions, max_concurrent, scan_count
        with lock:
            concurrent_executions += 1
            if concurrent_executions > max_concurrent:
                max_concurrent = concurrent_executions
        # Simulate work
        time.sleep(0.08)
        with lock:
            concurrent_executions -= 1
            scan_count += 1
        return _make_mock_result()

    mock_scanner.scan_incremental.side_effect = slow_scan

    completed_results = []
    coordinator = WatchEventCoordinator(
        scanner=mock_scanner,
        on_scan_completed=completed_results.append,
    )

    batch1 = WatchBatch(
        batch_id="b1",
        affected_paths={"src/A.ts"},
        events=[FileEvent(FileEventType.MODIFIED, "src/A.ts")],
        created_at=time.time(),
    )
    batch2 = WatchBatch(
        batch_id="b2",
        affected_paths={"src/B.ts"},
        events=[FileEvent(FileEventType.MODIFIED, "src/B.ts")],
        created_at=time.time(),
    )

    # Dispatch batch 1, then immediately dispatch batch 2 while batch 1 is running
    coordinator.on_batch_ready(batch1)
    time.sleep(0.02)
    coordinator.on_batch_ready(batch2)

    # Wait for coordinator worker threads to drain
    time.sleep(0.3)

    # Max concurrent executions must be strictly 1
    assert max_concurrent == 1
    # Both batches must have been processed (either coalesced into 2nd scan or executed)
    assert scan_count >= 1
    assert coordinator.total_batches_processed == 2


def test_coordinator_error_isolation():
    """Verify scanner failures are captured without crashing coordinator."""
    mock_scanner = MagicMock()
    mock_scanner.scan_incremental.side_effect = RuntimeError("SQLite database locked")

    coordinator = WatchEventCoordinator(scanner=mock_scanner)

    batch = WatchBatch(
        batch_id="b1",
        affected_paths={"src/broken.ts"},
        events=[FileEvent(FileEventType.MODIFIED, "src/broken.ts")],
        created_at=time.time(),
    )

    coordinator.on_batch_ready(batch)
    time.sleep(0.1)

    assert coordinator.total_scans_failed == 1
    assert coordinator.last_error is not None
    assert "SQLite database locked" in coordinator.last_error
    assert not coordinator.is_scanning
