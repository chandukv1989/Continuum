"""Unit tests for Code Brain SQLite persistence repository."""
from pathlib import Path
import pytest

from backend.app.code_brain.database import CodeBrainDatabase
from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.scanner.contracts import (
    DiscoveredFile,
    EvidenceType,
    FileFilterStatus,
    Language,
    ParseResult,
    ParseStatus,
    RelationshipRecord,
    RelationshipType,
    SymbolKind,
    SymbolRecord,
)


def test_code_brain_initialization_and_pragmas(tmp_path: Path):
    """Verify SQLite WAL mode, foreign keys, and schema creation."""
    db_path = tmp_path / "brain" / "symbols.db"
    db = CodeBrainDatabase(db_path)
    db.initialize_schema()

    conn = db.get_connection()

    journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert journal_mode.lower() == "wal"

    foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert foreign_keys == 1

    # Verify tables exist
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
    }
    assert {"meta", "files", "symbols", "relationships"}.issubset(tables)
    db.close()


def test_code_brain_rebuild_and_queries(tmp_path: Path):
    """Verify batched atomic rebuild and entity querying."""
    db_path = tmp_path / "projects" / "test-proj" / "symbols.db"
    repo = CodeBrainRepository(db_path)

    # Prepare mock scan data
    files = [
        DiscoveredFile(
            canonical_path=tmp_path / "app" / "main.py",
            relative_path="app/main.py",
            size_bytes=150,
            mtime=1700000000.0,
            status=FileFilterStatus.PARSEABLE,
            language=Language.PYTHON,
            content_hash="abc123hash",
        )
    ]

    symbols = [
        SymbolRecord(
            id="sym_class_1",
            file_path="app/main.py",
            name="AppService",
            qualified_name="app.main.AppService",
            kind=SymbolKind.CLASS,
            language=Language.PYTHON,
            start_line=5,
            start_column=0,
            end_line=20,
            end_column=0,
            is_exported=True,
            docstring="Service docstring",
        ),
        SymbolRecord(
            id="sym_method_1",
            file_path="app/main.py",
            name="run",
            qualified_name="app.main.AppService.run",
            kind=SymbolKind.METHOD,
            language=Language.PYTHON,
            parent_symbol_id="sym_class_1",
            start_line=10,
            start_column=4,
            end_line=15,
            end_column=4,
            is_exported=False,
        ),
    ]

    relationships = [
        RelationshipRecord(
            id="rel_1",
            source_id="app/main.py",
            target_name="AppService",
            target_id="sym_class_1",
            relationship_type=RelationshipType.CONTAINS,
            evidence_type=EvidenceType.CONFIRMED,
            file_path="app/main.py",
            line_number=5,
        ),
        RelationshipRecord(
            id="rel_2",
            source_id="sym_class_1",
            target_name="run",
            target_id="sym_method_1",
            relationship_type=RelationshipType.CONTAINS,
            evidence_type=EvidenceType.CONFIRMED,
            file_path="app/main.py",
            line_number=10,
        ),
    ]

    parse_results = [
        ParseResult(
            file_path="app/main.py",
            status=ParseStatus.SUCCESS,
            language=Language.PYTHON,
            symbols=symbols,
            relationships=relationships,
        )
    ]

    # Rebuild
    repo.rebuild(scanned_files=files, parse_results=parse_results)

    stats = repo.get_stats()
    assert stats.files_count == 1
    assert stats.symbols_count == 2
    assert stats.relationships_count == 2

    # Query files
    file_records = repo.get_files()
    assert len(file_records) == 1
    assert file_records[0]["path"] == "app/main.py"
    assert file_records[0]["content_hash"] == "abc123hash"

    # Query symbols
    sym_records = repo.get_symbols(file_path="app/main.py")
    assert len(sym_records) == 2

    class_sym = repo.get_symbol_by_id("sym_class_1")
    assert class_sym is not None
    assert class_sym["name"] == "AppService"
    assert class_sym["docstring"] == "Service docstring"

    # Query relationships
    rels = repo.get_relationships(relationship_type="contains")
    assert len(rels) == 2

    # Second rebuild with new data wipes old data completely
    repo.rebuild(scanned_files=[], parse_results=[])
    stats_empty = repo.get_stats()
    assert stats_empty.files_count == 0
    assert stats_empty.symbols_count == 0
    assert stats_empty.relationships_count == 0

    repo.close()
