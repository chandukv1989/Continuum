"""Unit tests for FilesystemWatcherService lifecycle and status reporting."""
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from backend.app.core.config import ContinuumSettings
from backend.app.watcher.service import FilesystemWatcherService
from backend.app.workspace.context import WorkspaceContext


def test_watcher_service_lifecycle(tmp_path: Path):
    """Verify start, stop, double start, and double stop behavior."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "src" / "index.ts").write_text("export const x = 1;")

    settings = ContinuumSettings(
        CONTINUUM_HOME=tmp_path / ".continuum_home",
        watcher_debounce_seconds=0.05,
    )
    context = WorkspaceContext.create(workspace, config=settings)

    mock_scanner = MagicMock()

    service = FilesystemWatcherService(
        context=context,
        scanner=mock_scanner,
        settings=settings,
    )

    assert not service.is_running

    # 1. Start service
    service.start()
    assert service.is_running

    # 2. Idempotent double start
    service.start()
    assert service.is_running

    status = service.get_status()
    assert status.is_running
    assert status.project_id == context.project_id
    assert status.workspace_root == context.repository_root.as_posix()

    # 3. Stop service
    service.stop()
    assert not service.is_running

    # 4. Idempotent double stop
    service.stop()
    assert not service.is_running


def test_watcher_service_flush_and_scan(tmp_path: Path):
    """Verify manual flush_and_scan() triggers synchronous incremental scan."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    settings = ContinuumSettings(
        CONTINUUM_HOME=tmp_path / ".continuum_home",
        watcher_debounce_seconds=1.0,
    )
    context = WorkspaceContext.create(workspace, config=settings)

    mock_scanner = MagicMock()
    mock_scanner.scan_incremental.return_value = MagicMock(
        change_set=MagicMock(changes=[])
    )

    service = FilesystemWatcherService(
        context=context,
        scanner=mock_scanner,
        settings=settings,
    )

    # Trigger flush and scan
    service.flush_and_scan()
    assert mock_scanner.scan_incremental.called
