"""Domain contracts and typed data structures for Continuum Scanner & Code Brain.

Defines the core facts, statuses, and representations extracted deterministically
from workspace source code.
"""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class Language(str, Enum):
    """Authoritatively supported languages in Continuum Phase 2."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    TSX = "tsx"
    JAVASCRIPT = "javascript"
    JSX = "jsx"
    UNKNOWN = "unknown"


class FileFilterStatus(str, Enum):
    """Classification status for discovered workspace files."""

    PARSEABLE = "parseable"
    IGNORED = "ignored"
    BINARY = "binary"
    TOO_LARGE = "too_large"
    UNSUPPORTED = "unsupported"
    GENERATED = "generated"
    OUTSIDE_WORKSPACE = "outside_workspace"


class ParseStatus(str, Enum):
    """Result status of Tree-sitter parsing for a specific file."""

    SUCCESS = "success"
    PARTIAL_ERROR = "partial_error"
    FAILED = "failed"
    SKIPPED = "skipped"


class SymbolKind(str, Enum):
    """Categorization of structural code constructs."""

    MODULE = "module"
    CLASS = "class"
    METHOD = "method"
    FUNCTION = "function"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    ENUM = "enum"
    VARIABLE = "variable"
    REACT_COMPONENT = "react_component"
    REACT_HOOK = "react_hook"


class RelationshipType(str, Enum):
    """Confirmed structural relationships extracted from ASTs."""

    CONTAINS = "contains"
    IMPORTS = "imports"
    EXPORTS = "exports"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"


class EvidenceType(str, Enum):
    """Evidence tier for Code Brain assertions."""

    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


@dataclass
class DiscoveredFile:
    """Metadata representing a single file discovered in the workspace."""

    canonical_path: Path
    relative_path: str
    size_bytes: int
    mtime: float
    status: FileFilterStatus
    language: Language
    content_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_path": self.canonical_path.as_posix(),
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "mtime": self.mtime,
            "status": self.status.value,
            "language": self.language.value,
            "content_hash": self.content_hash,
        }


@dataclass
class SymbolRecord:
    """A deterministic structural symbol declaration extracted from an AST."""

    id: str
    file_path: str
    name: str
    qualified_name: str
    kind: SymbolKind
    language: Language
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    parent_symbol_id: Optional[str] = None
    is_exported: bool = False
    docstring: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "kind": self.kind.value,
            "language": self.language.value,
            "parent_symbol_id": self.parent_symbol_id,
            "start_line": self.start_line,
            "start_column": self.start_column,
            "end_line": self.end_line,
            "end_column": self.end_column,
            "is_exported": self.is_exported,
            "docstring": self.docstring,
        }


@dataclass
class RelationshipRecord:
    """A confirmed structural relationship between symbols or files."""

    id: str
    source_id: str
    target_name: str
    relationship_type: RelationshipType
    evidence_type: EvidenceType
    file_path: str
    line_number: int
    target_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_name": self.target_name,
            "target_id": self.target_id,
            "relationship_type": self.relationship_type.value,
            "evidence_type": self.evidence_type.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
        }


@dataclass
class ParseResult:
    """Output of parsing a single file through the Tree-sitter pipeline."""

    file_path: str
    status: ParseStatus
    language: Language
    symbols: List[SymbolRecord] = field(default_factory=list)
    relationships: List[RelationshipRecord] = field(default_factory=list)
    has_syntax_errors: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "status": self.status.value,
            "language": self.language.value,
            "symbols": [s.to_dict() for s in self.symbols],
            "relationships": [r.to_dict() for r in self.relationships],
            "has_syntax_errors": self.has_syntax_errors,
            "error_message": self.error_message,
        }


@dataclass
class ScanMetrics:
    """Quantitative performance and volume metrics for a repository scan."""

    files_discovered: int = 0
    files_filtered: int = 0
    files_parsed: int = 0
    parse_failures: int = 0
    symbols_extracted: int = 0
    relationships_extracted: int = 0
    scan_duration_seconds: float = 0.0
    persistence_duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files_discovered": self.files_discovered,
            "files_filtered": self.files_filtered,
            "files_parsed": self.files_parsed,
            "parse_failures": self.parse_failures,
            "symbols_extracted": self.symbols_extracted,
            "relationships_extracted": self.relationships_extracted,
            "scan_duration_seconds": round(self.scan_duration_seconds, 4),
            "persistence_duration_seconds": round(self.persistence_duration_seconds, 4),
        }


@dataclass
class ScanResult:
    """Aggregate result of a repository scan run."""

    project_id: str
    canonical_root: str
    symbols_db_path: str
    scanned_files: List[DiscoveredFile]
    parse_results: List[ParseResult]
    metrics: ScanMetrics

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "canonical_root": self.canonical_root,
            "symbols_db_path": self.symbols_db_path,
            "scanned_files": [f.to_dict() for f in self.scanned_files],
            "parse_results": [p.to_dict() for p in self.parse_results],
            "metrics": self.metrics.to_dict(),
        }


class ChangeType(str, Enum):
    """Categorization of workspace file mutations for incremental intelligence."""

    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    RENAMED = "RENAMED"


@dataclass
class FileChange:
    """Normalized file-level mutation representation independent of Git, watchdog, or UI."""

    path: str
    change_type: ChangeType
    old_path: Optional[str] = None
    old_content_hash: Optional[str] = None
    new_content_hash: Optional[str] = None
    size_bytes: Optional[int] = None
    mtime: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "change_type": self.change_type.value,
            "old_path": self.old_path,
            "old_content_hash": self.old_content_hash,
            "new_content_hash": self.new_content_hash,
            "size_bytes": self.size_bytes,
            "mtime": self.mtime,
        }


@dataclass
class ChangeSet:
    """Aggregate set of detected file mutations across a repository scan boundary."""

    changes: List[FileChange] = field(default_factory=list)
    detected_at: Optional[str] = None
    detection_source: str = "FILESYSTEM_CONTENT_HASH"

    @property
    def is_empty(self) -> bool:
        return len(self.changes) == 0

    @property
    def added_paths(self) -> List[str]:
        return [c.path for c in self.changes if c.change_type == ChangeType.ADDED]

    @property
    def modified_paths(self) -> List[str]:
        return [c.path for c in self.changes if c.change_type == ChangeType.MODIFIED]

    @property
    def deleted_paths(self) -> List[str]:
        return [c.path for c in self.changes if c.change_type == ChangeType.DELETED]

    @property
    def renamed_pairs(self) -> List[tuple[str, str]]:
        return [(c.old_path, c.path) for c in self.changes if c.change_type == ChangeType.RENAMED and c.old_path]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "changes": [c.to_dict() for c in self.changes],
            "detected_at": self.detected_at,
            "detection_source": self.detection_source,
            "is_empty": self.is_empty,
        }


@dataclass
class IncrementalScanResult:
    """Outcome and metrics of a synchronous incremental scan run."""

    project_id: str
    canonical_root: str
    symbols_db_path: str
    change_set: ChangeSet
    parse_results: List[ParseResult]
    metrics: ScanMetrics
    reconciliation_report: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "canonical_root": self.canonical_root,
            "symbols_db_path": self.symbols_db_path,
            "change_set": self.change_set.to_dict(),
            "parse_results": [p.to_dict() for p in self.parse_results],
            "metrics": self.metrics.to_dict(),
            "reconciliation_report": self.reconciliation_report,
        }

