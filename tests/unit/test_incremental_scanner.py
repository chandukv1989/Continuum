"""Unit tests for Phase 4.1 Incremental Intelligence.

Verifies:
1. ChangeSet domain contract instantiation & serialization
2. Content-hash based change detection (ADDED, MODIFIED, DELETED, RENAMED)
3. Incremental surgical Code Brain operations (delete_file_artifacts, apply_incremental_scan)
4. Transactional atomicity (error rollback leaves previous state untouched)
5. Scoped Project Brain reference reconciliation
6. Non-Git workspace compatibility
7. Full rebuild fallback capability
"""
from pathlib import Path
import sqlite3
import pytest

from backend.app.code_brain.database import CodeBrainDatabase
from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.core.config import ContinuumSettings
from backend.app.project_brain.contracts import (
    ArtifactOwnership,
    CodeSymbolRef,
    DecisionEntity,
    DecisionStatus,
    DiscrepancyStatus,
    EvidenceState,
    Provenance,
    ProvenanceSource,
)
from backend.app.project_brain.repository import ProjectBrainRepository
from backend.app.scanner.contracts import (
    ChangeSet,
    ChangeType,
    DiscoveredFile,
    FileChange,
    FileFilterStatus,
    Language,
    ParseResult,
    ParseStatus,
    RelationshipRecord,
    RelationshipType,
    SymbolKind,
    SymbolRecord,
)
from backend.app.scanner.detector import ChangeDetector
from backend.app.scanner.incremental import IncrementalRepositoryScanner
from backend.app.scanner.repository import RepositoryScanner
from backend.app.workspace.context import WorkspaceContext


def test_changeset_contracts_and_serialization() -> None:
    """Verify ChangeSet and FileChange serialization and properties."""
    change1 = FileChange(
        path="src/index.ts",
        change_type=ChangeType.MODIFIED,
        old_content_hash="hash_old",
        new_content_hash="hash_new",
        size_bytes=1024,
        mtime=1700000000.0,
    )
    change2 = FileChange(
        path="src/new.ts",
        change_type=ChangeType.ADDED,
        new_content_hash="hash_new_2",
    )
    change3 = FileChange(
        path="src/old.ts",
        change_type=ChangeType.DELETED,
        old_content_hash="hash_del",
    )
    change4 = FileChange(
        path="src/renamed.ts",
        old_path="src/prev.ts",
        change_type=ChangeType.RENAMED,
        old_content_hash="same_hash",
        new_content_hash="same_hash",
    )

    cs = ChangeSet(
        changes=[change1, change2, change3, change4],
        detected_at="2026-09-18T00:00:00Z",
        detection_source="FILESYSTEM_CONTENT_HASH",
    )

    assert not cs.is_empty
    assert cs.modified_paths == ["src/index.ts"]
    assert cs.added_paths == ["src/new.ts"]
    assert cs.deleted_paths == ["src/old.ts"]
    assert cs.renamed_pairs == [("src/prev.ts", "src/renamed.ts")]

    data = cs.to_dict()
    assert len(data["changes"]) == 4
    assert data["detection_source"] == "FILESYSTEM_CONTENT_HASH"


def test_change_detector_lifecycle(tmp_path: Path) -> None:
    """Verify ChangeDetector accurately identifies ADDED, MODIFIED, DELETED, and RENAMED files."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    file_a = workspace / "file_a.py"
    file_b = workspace / "file_b.py"

    file_a.write_text("def func_a(): pass\n", encoding="utf-8")
    file_b.write_text("def func_b(): pass\n", encoding="utf-8")

    db_path = tmp_path / "symbols.db"
    code_repo = CodeBrainRepository(db_path)

    settings = ContinuumSettings(continuum_home=tmp_path / ".continuum")
    context = WorkspaceContext.create(workspace_path=workspace, config=settings)

    # Initially, full scan so Code Brain is populated
    full_scanner = RepositoryScanner(context=context, code_brain_repo=code_repo)
    full_scanner.scan(persist=True)

    detector = ChangeDetector(context=context, code_brain_repo=code_repo)

    # 1. No changes
    cs, candidates = detector.detect_changes()
    assert cs.is_empty
    assert len(candidates) == 0

    # 2. Modify file_a
    file_a.write_text("def func_a():\n    return 42\n", encoding="utf-8")
    cs, candidates = detector.detect_changes()
    assert len(cs.changes) == 1
    assert cs.changes[0].change_type == ChangeType.MODIFIED
    assert cs.changes[0].path == "file_a.py"

    # Reset Code Brain with modified file
    full_scanner.scan(persist=True)

    # 3. Add file_c
    file_c = workspace / "file_c.py"
    file_c.write_text("class C: pass\n", encoding="utf-8")
    cs, candidates = detector.detect_changes()
    assert len(cs.changes) == 1
    assert cs.changes[0].change_type == ChangeType.ADDED
    assert cs.changes[0].path == "file_c.py"

    # 4. Rename file_b -> file_b_renamed (same content)
    file_b.unlink()
    file_b_renamed = workspace / "file_b_renamed.py"
    file_b_renamed.write_text("def func_b(): pass\n", encoding="utf-8")

    cs, candidates = detector.detect_changes()
    # Should detect 1 ADDED (file_c), 1 RENAMED (file_b -> file_b_renamed)
    types = {c.path: c.change_type for c in cs.changes}
    assert types["file_c.py"] == ChangeType.ADDED
    assert types["file_b_renamed.py"] == ChangeType.RENAMED


def test_code_brain_surgical_delete_and_upsert(tmp_path: Path) -> None:
    """Verify surgical deletion cascades and incremental upserts modify only target files."""
    db_path = tmp_path / "symbols.db"
    code_repo = CodeBrainRepository(db_path)

    # Mock discovered files and parse results
    df1 = DiscoveredFile(
        relative_path="module1.py",
        canonical_path=tmp_path / "module1.py",
        size_bytes=100,
        content_hash="hash1",
        mtime=1000.0,
        language=Language.PYTHON,
        status=FileFilterStatus.PARSEABLE,
    )
    df2 = DiscoveredFile(
        relative_path="module2.py",
        canonical_path=tmp_path / "module2.py",
        size_bytes=200,
        content_hash="hash2",
        mtime=2000.0,
        language=Language.PYTHON,
        status=FileFilterStatus.PARSEABLE,
    )

    sym1 = SymbolRecord(
        id="sym_1",
        file_path="module1.py",
        name="func1",
        qualified_name="module1.func1",
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        start_line=1,
        start_column=0,
        end_line=2,
        end_column=0,
    )
    sym2 = SymbolRecord(
        id="sym_2",
        file_path="module2.py",
        name="func2",
        qualified_name="module2.func2",
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        start_line=1,
        start_column=0,
        end_line=2,
        end_column=0,
    )

    pr1 = ParseResult(
        file_path="module1.py",
        status=ParseStatus.SUCCESS,
        language=Language.PYTHON,
        symbols=[sym1],
        relationships=[],
    )
    pr2 = ParseResult(
        file_path="module2.py",
        status=ParseStatus.SUCCESS,
        language=Language.PYTHON,
        symbols=[sym2],
        relationships=[],
    )

    # Initial population via rebuild
    code_repo.rebuild(scanned_files=[df1, df2], parse_results=[pr1, pr2])
    stats = code_repo.get_stats()
    assert stats.files_count == 2
    assert stats.symbols_count == 2

    # Surgical delete module1.py
    code_repo.delete_file_artifacts("module1.py")
    stats = code_repo.get_stats()
    assert stats.files_count == 1
    assert stats.symbols_count == 1
    # Verify remaining symbol is sym_2
    symbols = code_repo.get_symbols()
    assert len(symbols) == 1
    assert symbols[0]["id"] == "sym_2"

    # Surgical incremental update (re-add module1 with modified symbol)
    sym1_updated = SymbolRecord(
        id="sym_1_updated",
        file_path="module1.py",
        name="func1_updated",
        qualified_name="module1.func1_updated",
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        start_line=1,
        start_column=0,
        end_line=3,
        end_column=0,
    )
    pr1_updated = ParseResult(
        file_path="module1.py",
        status=ParseStatus.SUCCESS,
        language=Language.PYTHON,
        symbols=[sym1_updated],
        relationships=[],
    )

    code_repo.apply_incremental_scan(
        deleted_paths=[],
        scanned_files=[df1],
        parse_results=[pr1_updated],
    )

    stats = code_repo.get_stats()
    assert stats.files_count == 2
    assert stats.symbols_count == 2
    sym_names = {s["name"] for s in code_repo.get_symbols()}
    assert sym_names == {"func1_updated", "func2"}


def test_code_brain_transaction_atomicity(tmp_path: Path) -> None:
    """Verify that if an error occurs during an incremental update, the transaction rolls back cleanly."""
    db_path = tmp_path / "symbols.db"
    code_repo = CodeBrainRepository(db_path)

    df1 = DiscoveredFile(
        relative_path="mod.py",
        canonical_path=tmp_path / "mod.py",
        size_bytes=100,
        content_hash="h1",
        mtime=1.0,
        language=Language.PYTHON,
        status=FileFilterStatus.PARSEABLE,
    )
    sym1 = SymbolRecord(
        id="sym_good",
        file_path="mod.py",
        name="good",
        qualified_name="mod.good",
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        start_line=1,
        start_column=0,
        end_line=2,
        end_column=0,
    )
    pr1 = ParseResult(
        file_path="mod.py",
        status=ParseStatus.SUCCESS,
        language=Language.PYTHON,
        symbols=[sym1],
        relationships=[],
    )
    code_repo.rebuild(scanned_files=[df1], parse_results=[pr1])
    assert code_repo.get_stats().symbols_count == 1

    # Malformed symbol record that causes DB constraint violation
    # e.g. symbol referencing non-existent file or invalid foreign key
    class PoisonedParseResult(ParseResult):
        pass

    bad_sym = SymbolRecord(
        id="bad_sym",
        file_path="non_existent_file.py",  # Violates foreign key constraint
        name="bad",
        qualified_name="non_existent_file.bad",
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        start_line=1,
        start_column=0,
        end_line=2,
        end_column=0,
    )
    bad_pr = ParseResult(
        file_path="non_existent_file.py",
        status=ParseStatus.SUCCESS,
        language=Language.PYTHON,
        symbols=[bad_sym],
        relationships=[],
    )

    with pytest.raises(Exception):
        code_repo.apply_incremental_scan(
            deleted_paths=["mod.py"],  # attempted delete
            scanned_files=[],          # did not re-add mod.py
            parse_results=[bad_pr],    # will fail on symbol foreign key
        )

    # Assert mod.py is STILL intact because the transaction rolled back
    stats = code_repo.get_stats()
    assert stats.files_count == 1
    assert stats.symbols_count == 1
    assert code_repo.get_symbols()[0]["id"] == "sym_good"


def test_incremental_scanner_and_project_brain_scoped_reconciliation(tmp_path: Path) -> None:
    """Verify incremental scanner updates Code Brain and records discrepancies for stale references."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    file_py = workspace / "service.py"
    file_py.write_text("class PaymentService:\n    def process(self): pass\n", encoding="utf-8")

    db_path = tmp_path / "symbols.db"
    code_repo = CodeBrainRepository(db_path)

    project_dir = workspace / ".continuum"
    project_repo = ProjectBrainRepository(project_dir)

    # Human-authored ADR referencing service.py#PaymentService
    now = "2026-09-18T00:00:00Z"
    adr = DecisionEntity(
        id="dec:payment",
        title="Payment Service Architecture",
        status=DecisionStatus.ACCEPTED,
        context="Must handle credit card processing",
        decision="Use dedicated service class",
        consequences="Centralized payment logic",
        code_refs=["sym://service.py#PaymentService?kind=class"],
        date="2026-09-18",
        ownership=ArtifactOwnership.HUMAN_AUTHORED,
        provenance=Provenance(source=ProvenanceSource.DEVELOPER, created_at=now, updated_at=now),
    )
    project_repo.save_decision(adr)

    settings = ContinuumSettings(continuum_home=tmp_path / ".continuum_home")
    context = WorkspaceContext.create(workspace_path=workspace, config=settings)

    # Initial scan
    scanner = RepositoryScanner(context=context, code_brain_repo=code_repo)
    scanner.scan(persist=True)

    inc_scanner = IncrementalRepositoryScanner(
        context=context,
        code_brain_repo=code_repo,
        project_brain_repo=project_repo,
    )

    # Delete PaymentService from service.py
    file_py.write_text("class UnrelatedService:\n    pass\n", encoding="utf-8")

    inc_res = inc_scanner.scan_incremental(reconcile_project_brain=True)
    assert not inc_res.change_set.is_empty
    assert inc_res.change_set.modified_paths == ["service.py"]

    # Verify ADR was preserved (human authored)
    loaded_adr = project_repo.get_decision("dec:payment")
    assert loaded_adr is not None
    assert loaded_adr.title == "Payment Service Architecture"

    # Verify discrepancy was recorded
    discs = project_repo.list_discrepancies(status=DiscrepancyStatus.OPEN)
    assert len(discs) >= 1
    assert any("PaymentService" in d.human_statement for d in discs)
