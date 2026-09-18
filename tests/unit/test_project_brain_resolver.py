"""Unit tests for soft Code Brain reference resolver."""
from backend.app.code_brain.database import CodeBrainDatabase
from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.project_brain.contracts import (
    CodeSymbolRef,
    ReferenceResolutionStatus,
)
from backend.app.project_brain.resolver import CodeReferenceResolver


def test_code_reference_resolver_lifecycle(tmp_path):
    db_path = tmp_path / "symbols.db"
    db = CodeBrainDatabase(db_path)
    db.initialize_schema()
    repo = CodeBrainRepository(db_path)

    # Insert sample files and symbols directly
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO files (path, canonical_path, size_bytes, mtime, language, parse_status) "
            "VALUES ('backend/app/scanner/repository.py', '/can/rep.py', 100, 1.0, 'python', 'success');"
        )
        conn.execute(
            "INSERT INTO files (path, canonical_path, size_bytes, mtime, language, parse_status) "
            "VALUES ('backend/app/core/security.py', '/can/sec.py', 100, 1.0, 'python', 'success');"
        )
        conn.execute(
            "INSERT INTO symbols (id, file_path, name, qualified_name, kind, language, start_line, start_col, end_line, end_col) "
            "VALUES ('sym_1', 'backend/app/scanner/repository.py', 'RepositoryScanner', 'RepositoryScanner', 'class', 'python', 10, 0, 50, 1);"
        )
        conn.execute(
            "INSERT INTO symbols (id, file_path, name, qualified_name, kind, language, start_line, start_col, end_line, end_col) "
            "VALUES ('sym_2', 'backend/app/core/security.py', 'SecurityManager', 'SecurityManager', 'class', 'python', 5, 0, 30, 1);"
        )

    resolver = CodeReferenceResolver(repo)

    # 1. Exact match -> RESOLVED
    res_exact = resolver.resolve("sym://backend/app/scanner/repository.py#RepositoryScanner?kind=class")
    assert res_exact.status == ReferenceResolutionStatus.RESOLVED
    assert res_exact.resolved_symbol_id == "sym_1"

    # 2. Relocated symbol -> STALE with moved_to_path
    res_stale = resolver.resolve("sym://old/path/security.py#SecurityManager?kind=class")
    assert res_stale.status == ReferenceResolutionStatus.STALE
    assert res_stale.moved_to_path == "backend/app/core/security.py"

    # 3. Missing symbol -> UNRESOLVED
    res_missing = resolver.resolve("sym://backend/app/missing.py#NonExistentClass?kind=class")
    assert res_missing.status == ReferenceResolutionStatus.UNRESOLVED
    assert res_missing.resolved_symbol_id is None

