"""Golden Equivalence Integration Test for Continuum Phase 4.1.

Validates the Critical Invariant:
FullScan(final_source_tree) == FullScan(initial_source_tree) + IncrementalScan(all_changes)

Comparing:
- files table (path, canonical_path, size_bytes, content_hash, language, parse_status)
- symbols table (id, file_path, name, qualified_name, kind, language, parent_id, start_line, etc.)
- relationships table (id, source_id, target_name, target_id, relationship_type, evidence_type, file_path, line_number)
"""
from pathlib import Path
import shutil
import pytest

from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.core.config import ContinuumSettings
from backend.app.scanner.incremental import IncrementalRepositoryScanner
from backend.app.scanner.repository import RepositoryScanner
from backend.app.workspace.context import WorkspaceContext


def test_golden_full_scan_incremental_scan_equivalence(tmp_path: Path) -> None:
    """Prove that incremental updates produce the exact same deterministic facts as a fresh full rebuild."""
    # 1. Setup workspace 1 (Incremental pipeline)
    ws_inc = tmp_path / "ws_inc"
    ws_inc.mkdir()

    # Initial files in ws_inc:
    # A.ts: exports Foo and Bar, imports Helper
    # B.ts: exports Helper
    # C.py: simple class Calc
    file_a = ws_inc / "src" / "A.ts"
    file_a.parent.mkdir(parents=True)
    file_b = ws_inc / "src" / "B.ts"
    file_c = ws_inc / "lib" / "C.py"
    file_c.parent.mkdir(parents=True)

    file_a.write_text(
        'import { Helper } from "./B";\n\nexport class Foo {\n  public bar(): void {}\n}\n',
        encoding="utf-8",
    )
    file_b.write_text(
        "export class Helper {\n  public help(): string { return 'ok'; }\n}\n",
        encoding="utf-8",
    )
    file_c.write_text(
        "class Calc:\n    def add(self, a, b):\n        return a + b\n",
        encoding="utf-8",
    )

    db_inc = tmp_path / "db_inc.db"
    code_repo_inc = CodeBrainRepository(db_inc)
    settings_inc = ContinuumSettings(continuum_home=tmp_path / ".continuum_inc")
    ctx_inc = WorkspaceContext.create(workspace_path=ws_inc, config=settings_inc)

    # Baseline full scan for ws_inc
    full_scanner_inc = RepositoryScanner(context=ctx_inc, code_brain_repo=code_repo_inc)
    full_scanner_inc.scan(persist=True)

    initial_stats = code_repo_inc.get_stats()
    assert initial_stats.files_count == 3
    assert initial_stats.symbols_count >= 5

    # 2. Mutate ws_inc:
    # - Modify A.ts (add a new method, modify signature)
    # - Add D.ts
    # - Delete B.ts
    # - Rename C.py -> C_renamed.py
    file_a.write_text(
        'export class Foo {\n  public bar(): void {}\n  public baz(): number { return 100; }\n}\n',
        encoding="utf-8",
    )
    file_d = ws_inc / "src" / "D.ts"
    file_d.write_text("export function standalone(): boolean { return true; }\n", encoding="utf-8")

    file_b.unlink()

    file_c.unlink()
    file_c_renamed = ws_inc / "lib" / "C_renamed.py"
    file_c_renamed.write_text(
        "class Calc:\n    def add(self, a, b):\n        return a + b\n",
        encoding="utf-8",
    )

    # 3. Run Incremental Scanner on ws_inc
    inc_scanner = IncrementalRepositoryScanner(
        context=ctx_inc,
        code_brain_repo=code_repo_inc,
    )
    inc_result = inc_scanner.scan_incremental(reconcile_project_brain=False)

    assert not inc_result.change_set.is_empty
    assert len(inc_result.change_set.changes) == 4

    # 4. Now create a parallel fresh workspace 2 (ws_full) with the EXACT SAME final contents
    ws_full = tmp_path / "ws_full"
    # Copy from final ws_inc
    shutil.copytree(ws_inc, ws_full)

    db_full = tmp_path / "db_full.db"
    code_repo_full = CodeBrainRepository(db_full)
    settings_full = ContinuumSettings(continuum_home=tmp_path / ".continuum_full")
    ctx_full = WorkspaceContext.create(workspace_path=ws_full, config=settings_full)

    # 5. Run Full Scan on ws_full from scratch
    full_scanner = RepositoryScanner(context=ctx_full, code_brain_repo=code_repo_full)
    full_scanner.scan(persist=True)

    # 6. Compare deterministic facts between db_inc and db_full
    inc_files = code_repo_inc.get_files()
    full_files = code_repo_full.get_files()

    inc_symbols = code_repo_inc.get_symbols()
    full_symbols = code_repo_full.get_symbols()

    inc_relationships = code_repo_inc.get_relationships()
    full_relationships = code_repo_full.get_relationships()

    # Normalization helper (strip ephemeral scanned_at / mtime / canonical_path differences)
    def normalize_file(f):
        return (f["path"], f["size_bytes"], f["content_hash"], f["language"], f["parse_status"])

    def normalize_symbol(s):
        return (
            s["id"],
            s["file_path"],
            s["name"],
            s["qualified_name"],
            s["kind"],
            s["language"],
            s["parent_id"],
            s["start_line"],
            s["start_col"],
            s["end_line"],
            s["end_col"],
            s["is_exported"],
        )

    def normalize_rel(r):
        return (
            r["id"],
            r["source_id"],
            r["target_name"],
            r["target_id"],
            r["relationship_type"],
            r["evidence_type"],
            r["file_path"],
            r["line_number"],
        )

    norm_inc_files = sorted([normalize_file(f) for f in inc_files])
    norm_full_files = sorted([normalize_file(f) for f in full_files])
    assert norm_inc_files == norm_full_files, f"Files mismatch!\nINC: {norm_inc_files}\nFULL: {norm_full_files}"

    norm_inc_symbols = sorted([normalize_symbol(s) for s in inc_symbols])
    norm_full_symbols = sorted([normalize_symbol(s) for s in full_symbols])
    assert norm_inc_symbols == norm_full_symbols, f"Symbols mismatch!\nINC: {norm_inc_symbols}\nFULL: {norm_full_symbols}"

    norm_inc_rel = sorted([normalize_rel(r) for r in inc_relationships])
    norm_full_rel = sorted([normalize_rel(r) for r in full_relationships])
    assert norm_inc_rel == norm_full_rel, f"Relationships mismatch!\nINC: {norm_inc_rel}\nFULL: {norm_full_rel}"
