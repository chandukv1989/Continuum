"""Unit tests for Watcher contracts and EventNormalizer."""
from pathlib import Path
import pytest

from backend.app.scanner.filtering import FileFilter
from backend.app.watcher.contracts import (
    FileEvent,
    FileEventType,
    WatchBatch,
    WatcherStatus,
)
from backend.app.watcher.normalizer import EventNormalizer


def test_watcher_contracts_serialization():
    """Verify serialization of FileEvent, WatchBatch, and WatcherStatus."""
    event = FileEvent(
        event_type=FileEventType.CREATED,
        path="src/main.py",
        old_path=None,
        is_directory=False,
    )
    event_dict = event.to_dict()
    assert event_dict["event_type"] == "created"
    assert event_dict["path"] == "src/main.py"
    assert event_dict["old_path"] is None
    assert event_dict["is_directory"] is False

    batch = WatchBatch(
        batch_id="batch_123",
        affected_paths={"src/main.py", "src/utils.py"},
        events=[event],
        created_at=100.0,
        flushed_at=100.3,
    )
    assert batch.paths_count == 2
    assert not batch.is_empty
    batch_dict = batch.to_dict()
    assert batch_dict["batch_id"] == "batch_123"
    assert "src/main.py" in batch_dict["affected_paths"]
    assert batch_dict["events_count"] == 1

    status = WatcherStatus(
        is_running=True,
        is_scanning=False,
        project_id="proj_abc",
        workspace_root="/tmp/workspace",
        pending_paths_count=5,
        total_events_received=10,
        total_batches_processed=2,
        total_scans_triggered=2,
        total_scans_failed=0,
    )
    status_dict = status.to_dict()
    assert status_dict["is_running"] is True
    assert status_dict["project_id"] == "proj_abc"
    assert status_dict["pending_paths_count"] == 5


def test_event_normalizer_path_normalization(tmp_path: Path):
    """Verify normalizer converts raw absolute paths to relative POSIX paths."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src").mkdir()
    file_path = workspace / "src" / "index.ts"
    file_path.write_text("export const x = 1;")

    normalizer = EventNormalizer(workspace_root=workspace)

    # Valid internal path
    norm = normalizer.normalize_path(file_path)
    assert norm == "src/index.ts"

    # Workspace root itself
    assert normalizer.normalize_path(workspace) == "."


def test_event_normalizer_boundary_enforcement(tmp_path: Path):
    """Verify normalizer strictly rejects events outside the workspace root."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("secret")

    normalizer = EventNormalizer(workspace_root=workspace)

    # Outside file must be rejected and return None
    assert normalizer.normalize_path(outside_file) is None
    assert normalizer.normalize_path("/etc/passwd") is None


def test_event_normalizer_ignore_rules(tmp_path: Path):
    """Verify normalizer filters out .git, .continuum, node_modules, and cache files."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    normalizer = EventNormalizer(workspace_root=workspace)

    # .git
    assert normalizer.normalize_path(workspace / ".git" / "HEAD") is None

    # .continuum (Crucial: prevents Project Brain write feedback loops!)
    assert normalizer.normalize_path(workspace / ".continuum" / "decisions" / "dec_001.md") is None
    assert normalizer.normalize_path(workspace / ".continuum" / "discrepancies.yaml") is None

    # node_modules
    assert normalizer.normalize_path(workspace / "node_modules" / "react" / "index.js") is None

    # __pycache__
    assert normalizer.normalize_path(workspace / "src" / "__pycache__" / "test.pyc") is None

    # Ephemeral editor temporary files
    assert normalizer.normalize_path(workspace / "src" / ".index.ts.swp") is None
    assert normalizer.normalize_path(workspace / "src" / "index.ts~") is None
    assert normalizer.normalize_path(workspace / "src" / "index.ts.tmp") is None


def test_event_normalizer_event_types(tmp_path: Path):
    """Verify normalizer maps raw watchdog event types to Continuum FileEvent."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    src_file = workspace / "src" / "calc.py"
    dest_file = workspace / "src" / "calculator.py"

    normalizer = EventNormalizer(workspace_root=workspace)

    # CREATED
    ev_created = normalizer.normalize_event(
        event_type=FileEventType.CREATED,
        src_path=str(src_file),
    )
    assert ev_created is not None
    assert ev_created.event_type == FileEventType.CREATED
    assert ev_created.path == "src/calc.py"

    # MODIFIED
    ev_mod = normalizer.normalize_event(
        event_type=FileEventType.MODIFIED,
        src_path=str(src_file),
    )
    assert ev_mod is not None
    assert ev_mod.event_type == FileEventType.MODIFIED
    assert ev_mod.path == "src/calc.py"

    # DELETED
    ev_del = normalizer.normalize_event(
        event_type=FileEventType.DELETED,
        src_path=str(src_file),
    )
    assert ev_del is not None
    assert ev_del.event_type == FileEventType.DELETED
    assert ev_del.path == "src/calc.py"

    # MOVED (both valid)
    ev_moved = normalizer.normalize_event(
        event_type=FileEventType.MOVED,
        src_path=str(src_file),
        dest_path=str(dest_file),
    )
    assert ev_moved is not None
    assert ev_moved.event_type == FileEventType.MOVED
    assert ev_moved.path == "src/calculator.py"
    assert ev_moved.old_path == "src/calc.py"

    # DIRECTORY_CHANGED
    dir_path = workspace / "src"
    ev_dir = normalizer.normalize_event(
        event_type=FileEventType.MODIFIED,
        src_path=str(dir_path),
        is_directory=True,
    )
    assert ev_dir is not None
    assert ev_dir.event_type == FileEventType.DIRECTORY_CHANGED
    assert ev_dir.path == "src"
    assert ev_dir.is_directory is True
