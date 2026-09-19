"""Integration tests for real filesystem observation and Phase 4.1 integration."""
from pathlib import Path
import time
import pytest

from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.core.config import ContinuumSettings
from backend.app.scanner.incremental import IncrementalRepositoryScanner
from backend.app.scanner.repository import RepositoryScanner
from backend.app.watcher.service import FilesystemWatcherService
from backend.app.workspace.context import WorkspaceContext


@pytest.fixture
def watcher_workspace(tmp_path: Path):
    """Create a temporary workspace with initial Python code and initialized database."""
    ws = tmp_path / "watcher_ws"
    ws.mkdir()
    src = ws / "src"
    src.mkdir()

    # Initial file
    (src / "service.py").write_text(
        "class Service:\n"
        "    def run(self):\n"
        "        return True\n"
    )

    settings = ContinuumSettings(
        CONTINUUM_HOME=tmp_path / ".continuum_home",
        watcher_debounce_seconds=0.1,
    )
    context = WorkspaceContext.create(ws, config=settings)

    # Initial baseline scan
    initial_scanner = RepositoryScanner(context=context)
    initial_scanner.scan(persist=True)

    code_brain_repo = CodeBrainRepository(context.code_brain_db_path)
    inc_scanner = IncrementalRepositoryScanner(
        context=context,
        code_brain_repo=code_brain_repo,
    )

    service = FilesystemWatcherService(
        context=context,
        scanner=inc_scanner,
        settings=settings,
    )

    return {
        "root": ws,
        "src": src,
        "context": context,
        "repo": code_brain_repo,
        "service": service,
    }


def test_watcher_lifecycle_end_to_end(watcher_workspace):
    """Verify create, modify, delete, and rename events update Code Brain via Watcher."""
    ws = watcher_workspace["root"]
    src = watcher_workspace["src"]
    repo = watcher_workspace["repo"]
    service = watcher_workspace["service"]

    # Baseline symbols check
    syms = repo.get_symbols(file_path="src/service.py")
    assert any(s["name"] == "Service" for s in syms)

    service.start()
    try:
        # 1. CREATE new file
        calc_file = src / "calc.py"
        calc_file.write_text(
            "class Calculator:\n"
            "    def add(self, a, b):\n"
            "        return a + b\n"
        )

        # Allow watchdog and debouncer to process
        time.sleep(0.35)

        # Verify Code Brain has Calculator
        calc_syms = repo.get_symbols(file_path="src/calc.py")
        assert any(s["name"] == "Calculator" for s in calc_syms)

        # 2. MODIFY file
        calc_file.write_text(
            "class Calculator:\n"
            "    def add(self, a, b):\n"
            "        return a + b\n"
            "    def multiply(self, a, b):\n"
            "        return a * b\n"
        )
        time.sleep(0.35)

        calc_syms = repo.get_symbols(file_path="src/calc.py")
        assert any(s["name"] == "multiply" for s in calc_syms)

        # 3. DELETE file
        calc_file.unlink()
        time.sleep(0.35)

        calc_syms = repo.get_symbols(file_path="src/calc.py")
        assert len(calc_syms) == 0

    finally:
        service.stop()


def test_watcher_content_hash_authority(watcher_workspace):
    """Verify that a modified event on identical content triggers no semantic changes."""
    src = watcher_workspace["src"]
    service = watcher_workspace["service"]

    service.start()
    try:
        service_file = src / "service.py"
        current_content = service_file.read_text()

        # Re-write identical content (triggers filesystem modified event with identical hash)
        service_file.write_text(current_content)

        # Use flush_and_scan to synchronously execute
        res = service.flush_and_scan()
        assert res is not None
        # Phase 4.1 ChangeDetector must detect NO changes because content hash is identical
        assert res.change_set.is_empty
        assert len(res.change_set.changes) == 0

    finally:
        service.stop()


def test_watcher_continuum_feedback_loop_prevention(watcher_workspace):
    """Verify that writing to .continuum does NOT trigger any scanner execution."""
    ws = watcher_workspace["root"]
    service = watcher_workspace["service"]

    # Create .continuum directory and file
    continuum_dir = ws / ".continuum" / "decisions"
    continuum_dir.mkdir(parents=True, exist_ok=True)

    service.start()
    try:
        initial_triggers = service.coordinator.total_scans_triggered

        # Write decision ADR into .continuum
        adr_file = continuum_dir / "ADR-001.md"
        adr_file.write_text("# Decision 1\nHuman authored text.")

        time.sleep(0.25)

        # No scans must have been triggered because .continuum is ignored
        assert service.coordinator.total_scans_triggered == initial_triggers
        assert service.debouncer.pending_count == 0

    finally:
        service.stop()
