"""Deterministic language detection for Continuum Phase 2.

Determines the programming language of workspace files based on canonical
file extensions without heuristic or probabilistic AI guesswork.
"""
from pathlib import Path
from typing import Dict, Set

from backend.app.scanner.contracts import Language

EXTENSION_LANGUAGE_MAP: Dict[str, Language] = {
    ".py": Language.PYTHON,
    ".pyi": Language.PYTHON,
    ".ts": Language.TYPESCRIPT,
    ".mts": Language.TYPESCRIPT,
    ".cts": Language.TYPESCRIPT,
    ".tsx": Language.TSX,
    ".js": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".cjs": Language.JAVASCRIPT,
    ".jsx": Language.JSX,
}

SUPPORTED_LANGUAGES: Set[Language] = {
    Language.PYTHON,
    Language.TYPESCRIPT,
    Language.TSX,
    Language.JAVASCRIPT,
    Language.JSX,
}


def detect_language(file_path: Path | str) -> Language:
    """Detect programming language strictly from file extension.

    Args:
        file_path: Path to the target file.

    Returns:
        Language enum (PYTHON, TYPESCRIPT, TSX, JAVASCRIPT, JSX, or UNKNOWN).
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    return EXTENSION_LANGUAGE_MAP.get(ext, Language.UNKNOWN)


def is_supported_language(language: Language) -> bool:
    """Check if the given language has a registered AST parser in Phase 2."""
    return language in SUPPORTED_LANGUAGES
