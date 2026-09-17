"""Unit tests for Continuum Scanner file filtering."""
from pathlib import Path
import pytest

from backend.app.scanner.contracts import FileFilterStatus, Language
from backend.app.scanner.filtering import FileFilter, is_binary_file, is_generated_file
from backend.app.scanner.language import detect_language, is_supported_language


def test_language_detection():
    """Verify deterministic language mapping from file extensions."""
    assert detect_language("app.py") == Language.PYTHON
    assert detect_language("types.ts") == Language.TYPESCRIPT
    assert detect_language("Component.tsx") == Language.TSX
    assert detect_language("script.js") == Language.JAVASCRIPT
    assert detect_language("View.jsx") == Language.JSX
    assert detect_language("doc.md") == Language.UNKNOWN
    assert detect_language("data.json") == Language.UNKNOWN

    assert is_supported_language(Language.PYTHON) is True
    assert is_supported_language(Language.TYPESCRIPT) is True
    assert is_supported_language(Language.TSX) is True
    assert is_supported_language(Language.JAVASCRIPT) is True
    assert is_supported_language(Language.JSX) is True
    assert is_supported_language(Language.UNKNOWN) is False


def test_binary_file_detection(tmp_path: Path):
    """Verify binary detection via null byte inspection."""
    text_file = tmp_path / "normal.py"
    text_file.write_text("print('hello')", encoding="utf-8")
    assert is_binary_file(text_file) is False

    binary_file = tmp_path / "blob.py"
    binary_file.write_bytes(b"print('hello')\x00extra")
    assert is_binary_file(binary_file) is True


def test_generated_file_detection():
    """Verify generated/minified file detection."""
    assert is_generated_file(Path("bundle.min.js")) is True
    assert is_generated_file(Path("styles.min.css")) is True
    assert is_generated_file(Path("vendor.bundle.js")) is True
    assert is_generated_file(Path("index.ts")) is False


def test_file_filter_evaluation(tmp_path: Path):
    """Verify file filter rules across boundary, size, ignore, and binary checks."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Normal parseable file
    valid_file = workspace / "valid.py"
    valid_file.write_text("def foo(): pass", encoding="utf-8")

    # Ignored directory file
    ignored_dir = workspace / "node_modules" / "pkg"
    ignored_dir.mkdir(parents=True)
    ignored_file = ignored_dir / "index.js"
    ignored_file.write_text("console.log('ignored');", encoding="utf-8")

    # Unsupported file
    unsupported_file = workspace / "notes.txt"
    unsupported_file.write_text("just text", encoding="utf-8")

    # Oversized file
    large_file = workspace / "large.py"
    large_file.write_bytes(b"x" * 200)

    # Outside workspace file
    outside_file = tmp_path / "outside.py"
    outside_file.write_text("def bar(): pass", encoding="utf-8")

    # Filter with 100 byte limit
    filt = FileFilter(max_file_size_bytes=100)

    status, lang = filt.evaluate_file(valid_file, workspace)
    assert status == FileFilterStatus.PARSEABLE
    assert lang == Language.PYTHON

    status, lang = filt.evaluate_file(ignored_file, workspace)
    assert status == FileFilterStatus.IGNORED

    status, lang = filt.evaluate_file(unsupported_file, workspace)
    assert status == FileFilterStatus.UNSUPPORTED

    status, lang = filt.evaluate_file(large_file, workspace)
    assert status == FileFilterStatus.TOO_LARGE

    status, lang = filt.evaluate_file(outside_file, workspace)
    assert status == FileFilterStatus.OUTSIDE_WORKSPACE
