"""Golden Equivalence Verification for Watcher-Triggered Incremental Intelligence.

Verifies the foundational theorem:
    CleanFullScan(S_final) == WatcherTriggeredIncremental(S_initial + delta)
record-by-record across normalized files, symbols, and relationships.
"""
from pathlib import Path
import sqlite3
import pytest

from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.core.config import ContinuumSettings
from backend.app.scanner.incremental import IncrementalRepositoryScanner
from backend.app.scanner.repository import RepositoryScanner
from backend.app.watcher.service import FilesystemWatcherService
from backend.app.workspace.context import WorkspaceContext


def _get_normalized_db_state(db_path: Path):
    """Extract normalized tuples for files, symbols, and relationships."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # 1. Files
    files_rows = conn.execute(
        "SELECT path, size_bytes, content_hash, language, parse_status FROM files ORDER BY path"
    ).fetchall()
    norm_files = [
        (r["path"], r["size_bytes"], r["content_hash"], r["language"], r["parse_status"])
        for r in files_rows
    ]

    # 2. Symbols
    symbols_rows = conn.execute(
        """
        SELECT id, file_path, name, qualified_name, kind, language,
               parent_id, start_line, start_col, end_line, end_col, is_exported
        FROM symbols
        ORDER BY file_path, qualified_name, start_line
        """
    ).fetchall()
    norm_symbols = [
        (
            r["id"],
            r["file_path"],
            r["name"],
            r["qualified_name"],
            r["kind"],
            r["language"],
            r["parent_id"],
            r["start_line"],
            r["start_col"],
            r["end_line"],
            r["end_col"],
            bool(r["is_exported"]),
        )
        for r in symbols_rows
    ]

    # 3. Relationships
    rel_rows = conn.execute(
        """
        SELECT id, source_id, target_name, target_id, relationship_type,
               evidence_type, file_path, line_number
        FROM relationships
        ORDER BY file_path, line_number, source_id, target_name
        """
    ).fetchall()
    norm_relationships = [
        (
            r["id"],
            r["source_id"],
            r["target_name"],
            r["target_id"],
            r["relationship_type"],
            r["evidence_type"],
            r["file_path"],
            r["line_number"],
        )
        for r in rel_rows
    ]

    conn.close()
    return norm_files, norm_symbols, norm_relationships


def test_watcher_golden_equivalence(tmp_path: Path):
    """Prove record-by-record equivalence between watcher-triggered incremental scan and full rebuild."""
    ws_watcher = tmp_path / "ws_watcher"
    ws_full = tmp_path / "ws_full"

    for ws in [ws_watcher, ws_full]:
        ws.mkdir()
        (ws / "src").mkdir()
        (ws / "lib").mkdir()
        # Initial files
        (ws / "src" / "A.ts").write_text(
            "import { Helper } from './B';\n"
            "export class Foo {\n"
            "    bar(): number { return 42; }\n"
            "}\n"
        )
        (ws / "src" / "B.ts").write_text(
            "export class Helper {\n"
            "    help(): string { return 'ok'; }\n"
            "}\n"
        )
        (ws / "lib" / "C.py").write_text(
            "class Calc:\n"
            "    def add(self, a, b):\n"
            "        return a + b\n"
        )

    # Configure workspaces
    settings_watcher = ContinuumSettings(
        CONTINUUM_HOME=tmp_path / ".home_watcher",
        watcher_debounce_seconds=0.05,
    )
    settings_full = ContinuumSettings(
        CONTINUUM_HOME=tmp_path / ".home_full",
    )

    ctx_watcher = WorkspaceContext.create(ws_watcher, config=settings_watcher)
    ctx_full = WorkspaceContext.create(ws_full, config=settings_full)

    # Initial baseline scans on both
    RepositoryScanner(context=ctx_watcher).scan(persist=True)
    RepositoryScanner(context=ctx_full).scan(persist=True)

    # Set up Watcher Service on ws_watcher
    code_brain_repo = CodeBrainRepository(ctx_watcher.code_brain_db_path)
    inc_scanner = IncrementalRepositoryScanner(
        context=ctx_watcher,
        code_brain_repo=code_brain_repo,
    )
    watcher_service = FilesystemWatcherService(
        context=ctx_watcher,
        scanner=inc_scanner,
        settings=settings_watcher,
    )
    watcher_service.start()

    try:
        # Apply identical mutations (delta) to both workspaces:
        # 1. Modify src/A.ts
        new_a = (
            "export class Foo {\n"
            "    bar(): number { return 42; }\n"
            "    baz(): string { return 'new_baz'; }\n"
            "}\n"
        )
        (ws_watcher / "src" / "A.ts").write_text(new_a)
        (ws_full / "src" / "A.ts").write_text(new_a)

        # 2. Add src/D.ts
        new_d = "export function standalone(): boolean { return true; }\n"
        (ws_watcher / "src" / "D.ts").write_text(new_d)
        (ws_full / "src" / "D.ts").write_text(new_d)

        # 3. Delete src/B.ts
        (ws_watcher / "src" / "B.ts").unlink()
        (ws_full / "src" / "B.ts").unlink()

        # 4. Rename lib/C.py -> lib/C_renamed.py
        c_content = (ws_watcher / "lib" / "C.py").read_text()
        (ws_watcher / "lib" / "C.py").unlink()
        (ws_watcher / "lib" / "C_renamed.py").write_text(c_content)

        (ws_full / "lib" / "C.py").unlink()
        (ws_full / "lib" / "C_renamed.py").write_text(c_content)

        # Execute watcher-triggered processing on ws_watcher
        watcher_result = watcher_service.flush_and_scan()
        assert watcher_result is not None

        # Execute clean full rebuild on ws_full
        full_scanner = RepositoryScanner(context=ctx_full)
        full_scanner.scan(persist=True)

        # Extract normalized DB records from both SQLite databases
        w_files, w_symbols, w_rel = _get_normalized_db_state(ctx_watcher.code_brain_db_path)
        f_files, f_symbols, f_rel = _get_normalized_db_state(ctx_full.code_brain_db_path)

        # Record-by-Record Invariant Assertion
        assert w_files == f_files, f"Files mismatch: {w_files} != {f_files}"
        assert w_symbols == f_symbols, f"Symbols mismatch: {w_symbols} != {f_symbols}"
        assert w_rel == f_rel, f"Relationships mismatch: {w_rel} != {f_rel}"

    finally:
        watcher_service.stop()
