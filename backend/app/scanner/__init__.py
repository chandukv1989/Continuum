"""Continuum Scanner Module.

Deterministic repository parsing, symbol extraction, and structural relationship extraction.
"""
from backend.app.scanner.contracts import (
    DiscoveredFile,
    EvidenceType,
    FileFilterStatus,
    Language,
    ParseResult,
    ParseStatus,
    RelationshipRecord,
    RelationshipType,
    ScanMetrics,
    ScanResult,
    SymbolKind,
    SymbolRecord,
)
from backend.app.scanner.discovery import FileDiscovery
from backend.app.scanner.filtering import FileFilter
from backend.app.scanner.language import detect_language, is_supported_language
from backend.app.scanner.parser import TreeSitterEngine
from backend.app.scanner.relationships import RelationshipExtractor
from backend.app.scanner.symbols import SymbolExtractor

__all__ = [
    "Language",
    "FileFilterStatus",
    "ParseStatus",
    "SymbolKind",
    "RelationshipType",
    "EvidenceType",
    "DiscoveredFile",
    "SymbolRecord",
    "RelationshipRecord",
    "ParseResult",
    "ScanMetrics",
    "ScanResult",
    "FileDiscovery",
    "FileFilter",
    "detect_language",
    "is_supported_language",
    "TreeSitterEngine",
    "SymbolExtractor",
    "RelationshipExtractor",
]
