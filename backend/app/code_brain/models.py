"""Typed data models and schema definitions for Code Brain SQLite storage."""
from dataclasses import dataclass
from typing import Any, Dict, Optional

SCHEMA_VERSION = "2.0.0"

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    canonical_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    content_hash TEXT,
    mtime REAL NOT NULL,
    language TEXT NOT NULL,
    parse_status TEXT NOT NULL,
    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS symbols (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    language TEXT NOT NULL,
    parent_id TEXT,
    start_line INTEGER NOT NULL,
    start_col INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    end_col INTEGER NOT NULL,
    is_exported INTEGER NOT NULL DEFAULT 0,
    docstring TEXT,
    FOREIGN KEY(file_path) REFERENCES files(path) ON DELETE CASCADE,
    FOREIGN KEY(parent_id) REFERENCES symbols(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_name TEXT NOT NULL,
    target_id TEXT,
    relationship_type TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    FOREIGN KEY(file_path) REFERENCES files(path) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_files_language ON files(language);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(parse_status);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
CREATE INDEX IF NOT EXISTS idx_symbols_parent ON symbols(parent_id);
CREATE INDEX IF NOT EXISTS idx_rel_source ON relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_rel_type ON relationships(relationship_type);
CREATE INDEX IF NOT EXISTS idx_rel_file ON relationships(file_path);
"""


@dataclass
class CodeBrainStats:
    """Summary counts of stored entities in Code Brain."""

    files_count: int
    symbols_count: int
    relationships_count: int
    schema_version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files_count": self.files_count,
            "symbols_count": self.symbols_count,
            "relationships_count": self.relationships_count,
            "schema_version": self.schema_version,
        }
