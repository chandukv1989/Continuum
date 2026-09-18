"""Persistence repository for Continuum Code Brain (symbols.db).

Handles batched transactional writes, querying, and full rebuilds.
"""
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from backend.app.core.exceptions import CodeBrainException
from backend.app.core.logging import get_logger
from backend.app.code_brain.database import CodeBrainDatabase
from backend.app.code_brain.models import CodeBrainStats, SCHEMA_VERSION
from backend.app.scanner.contracts import (
    DiscoveredFile,
    ParseResult,
    RelationshipRecord,
    SymbolRecord,
)

logger = get_logger("continuum.code_brain.repository")


class CodeBrainRepository:
    """Provides high-level transactional storage and querying for Code Brain."""

    def __init__(self, db_path: Path | str) -> None:
        self.db = CodeBrainDatabase(db_path)
        self.db.initialize_schema()

    def rebuild(
        self,
        scanned_files: List[DiscoveredFile],
        parse_results: List[ParseResult],
        batch_size: int = 500,
    ) -> None:
        """Perform a complete atomic rebuild of Code Brain from fresh scan results.

        Wipes existing files, symbols, and relationships in an atomic transaction,
        guaranteeing no stale or orphaned records remain.
        """
        all_symbols: List[SymbolRecord] = []
        all_relationships: List[RelationshipRecord] = []

        for pr in parse_results:
            all_symbols.extend(pr.symbols)
            all_relationships.extend(pr.relationships)

        with self.db.transaction() as conn:
            # Clear existing tables (foreign key cascade removes child symbols/relationships)
            conn.execute("DELETE FROM relationships;")
            conn.execute("DELETE FROM symbols;")
            conn.execute("DELETE FROM files;")

            # 1. Insert files
            file_params = [
                (
                    f.relative_path,
                    f.canonical_path.as_posix(),
                    f.size_bytes,
                    f.content_hash,
                    f.mtime,
                    f.language.value,
                    f.status.value,
                )
                for f in scanned_files
            ]
            for i in range(0, len(file_params), batch_size):
                conn.executemany(
                    """
                    INSERT INTO files (
                        path, canonical_path, size_bytes, content_hash, mtime, language, parse_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    file_params[i : i + batch_size],
                )

            # 2. Insert symbols
            # To respect self-referential foreign keys (parent_id), insert root symbols first, then children
            root_symbols = [s for s in all_symbols if not s.parent_symbol_id]
            child_symbols = [s for s in all_symbols if s.parent_symbol_id]
            ordered_symbols = root_symbols + child_symbols

            symbol_params = [
                (
                    s.id,
                    s.file_path,
                    s.name,
                    s.qualified_name,
                    s.kind.value,
                    s.language.value,
                    s.parent_symbol_id,
                    s.start_line,
                    s.start_column,
                    s.end_line,
                    s.end_column,
                    1 if s.is_exported else 0,
                    s.docstring,
                )
                for s in ordered_symbols
            ]
            for i in range(0, len(symbol_params), batch_size):
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO symbols (
                        id, file_path, name, qualified_name, kind, language, parent_id,
                        start_line, start_col, end_line, end_col, is_exported, docstring
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    symbol_params[i : i + batch_size],
                )

            # 3. Insert relationships
            rel_params = [
                (
                    r.id,
                    r.source_id,
                    r.target_name,
                    r.target_id,
                    r.relationship_type.value,
                    r.evidence_type.value,
                    r.file_path,
                    r.line_number,
                )
                for r in all_relationships
            ]
            for i in range(0, len(rel_params), batch_size):
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO relationships (
                        id, source_id, target_name, target_id, relationship_type,
                        evidence_type, file_path, line_number
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    rel_params[i : i + batch_size],
                )

    def delete_file_artifacts(self, file_path: str) -> None:
        """Surgically delete a single file and cascade all its symbols and relationships.

        Transactional guarantee: executes in an atomic transaction.
        """
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM files WHERE path = ?;", (file_path,))

    def delete_files_artifacts(self, file_paths: List[str]) -> None:
        """Surgically delete multiple files and cascade all their symbols and relationships."""
        if not file_paths:
            return
        with self.db.transaction() as conn:
            for path in file_paths:
                conn.execute("DELETE FROM files WHERE path = ?;", (path,))

    def apply_incremental_scan(
        self,
        deleted_paths: List[str],
        scanned_files: List[DiscoveredFile],
        parse_results: List[ParseResult],
        batch_size: int = 500,
    ) -> None:
        """Atomically apply an incremental delta to Code Brain.

        1. Deletes files in deleted_paths (cascading to their symbols and relationships).
        2. Deletes existing records for any files in scanned_files (updating them).
        3. Inserts updated files, symbols, and relationships.
        All steps execute within a single atomic SQLite transaction. If any step fails,
        the entire transaction rolls back preserving the previous consistent state.
        """
        all_symbols: List[SymbolRecord] = []
        all_relationships: List[RelationshipRecord] = []

        for pr in parse_results:
            all_symbols.extend(pr.symbols)
            all_relationships.extend(pr.relationships)

        with self.db.transaction() as conn:
            # 1. Delete explicit deleted files
            for p in deleted_paths:
                conn.execute("DELETE FROM files WHERE path = ?;", (p,))

            # 2. Delete existing records for files being added/modified (upsert semantics)
            for f in scanned_files:
                conn.execute("DELETE FROM files WHERE path = ?;", (f.relative_path,))

            # 3. Insert updated file records
            file_params = [
                (
                    f.relative_path,
                    f.canonical_path.as_posix(),
                    f.size_bytes,
                    f.content_hash,
                    f.mtime,
                    f.language.value,
                    f.status.value,
                )
                for f in scanned_files
            ]
            for i in range(0, len(file_params), batch_size):
                conn.executemany(
                    """
                    INSERT INTO files (
                        path, canonical_path, size_bytes, content_hash, mtime, language, parse_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    file_params[i : i + batch_size],
                )

            # 4. Insert updated symbols (root symbols first, then children for parent_id FK)
            root_symbols = [s for s in all_symbols if not s.parent_symbol_id]
            child_symbols = [s for s in all_symbols if s.parent_symbol_id]
            ordered_symbols = root_symbols + child_symbols

            symbol_params = [
                (
                    s.id,
                    s.file_path,
                    s.name,
                    s.qualified_name,
                    s.kind.value,
                    s.language.value,
                    s.parent_symbol_id,
                    s.start_line,
                    s.start_column,
                    s.end_line,
                    s.end_column,
                    1 if s.is_exported else 0,
                    s.docstring,
                )
                for s in ordered_symbols
            ]
            for i in range(0, len(symbol_params), batch_size):
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO symbols (
                        id, file_path, name, qualified_name, kind, language, parent_id,
                        start_line, start_col, end_line, end_col, is_exported, docstring
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    symbol_params[i : i + batch_size],
                )

            # 5. Insert updated relationships
            rel_params = [
                (
                    r.id,
                    r.source_id,
                    r.target_name,
                    r.target_id,
                    r.relationship_type.value,
                    r.evidence_type.value,
                    r.file_path,
                    r.line_number,
                )
                for r in all_relationships
            ]
            for i in range(0, len(rel_params), batch_size):
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO relationships (
                        id, source_id, target_name, target_id, relationship_type,
                        evidence_type, file_path, line_number
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    rel_params[i : i + batch_size],
                )

    # -------------------------------------------------------------------------
    # QUERY METHODS
    # -------------------------------------------------------------------------

    def get_stats(self) -> CodeBrainStats:
        """Retrieve count of stored entities."""
        conn = self.db.get_connection()
        f_count = conn.execute("SELECT COUNT(*) FROM files;").fetchone()[0]
        s_count = conn.execute("SELECT COUNT(*) FROM symbols;").fetchone()[0]
        r_count = conn.execute("SELECT COUNT(*) FROM relationships;").fetchone()[0]
        meta_ver = conn.execute("SELECT value FROM meta WHERE key = 'schema_version';").fetchone()
        version = meta_ver[0] if meta_ver else SCHEMA_VERSION

        return CodeBrainStats(
            files_count=f_count,
            symbols_count=s_count,
            relationships_count=r_count,
            schema_version=version,
        )

    def get_files(self) -> List[Dict[str, Any]]:
        """Retrieve all registered files."""
        conn = self.db.get_connection()
        rows = conn.execute("SELECT * FROM files ORDER BY path ASC;").fetchall()
        return [dict(row) for row in rows]

    def get_file(self, path: str) -> Optional[Dict[str, Any]]:
        """Retrieve single file by relative path."""
        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM files WHERE path = ?;", (path,)).fetchone()
        return dict(row) if row else None

    def get_symbols(
        self,
        file_path: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query symbols with optional file path and kind filters."""
        conn = self.db.get_connection()
        query = "SELECT * FROM symbols WHERE 1=1"
        params: List[Any] = []

        if file_path:
            query += " AND file_path = ?"
            params.append(file_path)
        if kind:
            query += " AND kind = ?"
            params.append(kind)

        query += " ORDER BY file_path ASC, start_line ASC, start_col ASC;"
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_symbol_by_id(self, symbol_id: str) -> Optional[Dict[str, Any]]:
        """Query single symbol by its deterministic symbol_id."""
        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM symbols WHERE id = ?;", (symbol_id,)).fetchone()
        return dict(row) if row else None

    def get_relationships(
        self,
        source_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query relationships with optional filters."""
        conn = self.db.get_connection()
        query = "SELECT * FROM relationships WHERE 1=1"
        params: List[Any] = []

        if source_id:
            query += " AND source_id = ?"
            params.append(source_id)
        if relationship_type:
            query += " AND relationship_type = ?"
            params.append(relationship_type)
        if file_path:
            query += " AND file_path = ?"
            params.append(file_path)

        query += " ORDER BY file_path ASC, line_number ASC;"
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        """Close database connection."""
        self.db.close()
