"""Deterministic file filtering for Continuum Phase 2.

Determines whether discovered repository files are parseable, ignored, binary,
oversized, generated, or unsupported before passing them to Tree-sitter.
"""
from pathlib import Path
from typing import List, Optional, Sequence

from backend.app.scanner.contracts import FileFilterStatus, Language
from backend.app.scanner.language import detect_language, is_supported_language

# Chunk size used for binary inspection
BINARY_CHECK_BYTES = 8192

# Common suffixes for minified / generated files
GENERATED_FILE_SUFFIXES = {
    ".min.js",
    ".min.css",
    ".bundle.js",
    ".bundle.css",
    ".d.ts.map",
    ".js.map",
}


def is_binary_file(path: Path) -> bool:
    """Detect if a file contains null bytes in its initial chunk."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(BINARY_CHECK_BYTES)
            return b"\x00" in chunk
    except (OSError, PermissionError):
        return True


def matches_any_pattern(path_parts: Sequence[str], patterns: Sequence[str]) -> bool:
    """Check if any directory segment or file name matches an ignore pattern."""
    pattern_set = set(patterns)
    for part in path_parts:
        if part in pattern_set:
            return True
        # Check wildcard prefix/suffix matching if present
        for pat in patterns:
            if pat.startswith("*") and part.endswith(pat[1:]):
                return True
            if pat.endswith("*") and part.startswith(pat[:-1]):
                return True
    return False


def is_generated_file(path: Path) -> bool:
    """Check if file matches known generated file conventions."""
    name = path.name.lower()
    for suffix in GENERATED_FILE_SUFFIXES:
        if name.endswith(suffix):
            return True
    return False


class FileFilter:
    """Configurable file filter determining processing eligibility."""

    def __init__(
        self,
        max_file_size_bytes: int = 2 * 1024 * 1024,
        ignore_patterns: Optional[List[str]] = None,
    ) -> None:
        self.max_file_size_bytes = max_file_size_bytes
        self.ignore_patterns = ignore_patterns or [
            ".git",
            "node_modules",
            "dist",
            "build",
            "coverage",
            ".venv",
            "__pycache__",
            ".continuum",
            ".next",
            "out",
            ".pytest_cache",
            ".mypy_cache",
        ]

    def evaluate_file(
        self,
        file_path: Path,
        workspace_root: Path,
        stat_size: Optional[int] = None,
    ) -> tuple[FileFilterStatus, Language]:
        """Evaluate a file against all filtering rules in deterministic sequence.

        Args:
            file_path: Canonical path to the file.
            workspace_root: Canonical workspace root directory.
            stat_size: Optional pre-computed size in bytes.

        Returns:
            Tuple of (FileFilterStatus, Language).
        """
        # 1. Boundary check: must be inside workspace_root
        try:
            rel_path = file_path.relative_to(workspace_root)
        except ValueError:
            return FileFilterStatus.OUTSIDE_WORKSPACE, Language.UNKNOWN

        # 2. Pattern ignore check
        if matches_any_pattern(rel_path.parts, self.ignore_patterns):
            return FileFilterStatus.IGNORED, Language.UNKNOWN

        # 3. File existence & type check
        if not file_path.is_file():
            return FileFilterStatus.IGNORED, Language.UNKNOWN

        # 4. Language detection
        lang = detect_language(file_path)
        if not is_supported_language(lang):
            return FileFilterStatus.UNSUPPORTED, lang

        # 5. Generated file convention check
        if is_generated_file(file_path):
            return FileFilterStatus.GENERATED, lang

        # 6. File size check
        size = stat_size if stat_size is not None else file_path.stat().st_size
        if size > self.max_file_size_bytes:
            return FileFilterStatus.TOO_LARGE, lang

        # 7. Binary check
        if is_binary_file(file_path):
            return FileFilterStatus.BINARY, lang

        # All checks passed: parseable source file
        return FileFilterStatus.PARSEABLE, lang
