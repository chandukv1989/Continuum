"""Unit tests for TreeSitterEngine parsing."""
import pytest

from backend.app.core.exceptions import ParserException
from backend.app.scanner.contracts import Language
from backend.app.scanner.parser import TreeSitterEngine


def test_parser_initialization():
    """Verify parser initializes for all supported languages."""
    engine = TreeSitterEngine()
    for lang in (
        Language.PYTHON,
        Language.TYPESCRIPT,
        Language.TSX,
        Language.JAVASCRIPT,
        Language.JSX,
    ):
        parser = engine.get_parser(lang)
        assert parser is not None

    with pytest.raises(ParserException):
        engine.get_parser(Language.UNKNOWN)


def test_parse_valid_python():
    """Verify parsing valid Python source."""
    engine = TreeSitterEngine()
    source = b"""
def add(a: int, b: int) -> int:
    return a + b
"""
    tree, has_errors = engine.parse_source(source, Language.PYTHON)
    assert tree is not None
    assert has_errors is False
    assert tree.root_node.type == "module"


def test_parse_broken_python_syntax():
    """Verify error detection on malformed source code."""
    engine = TreeSitterEngine()
    source = b"def broken(:"
    tree, has_errors = engine.parse_source(source, Language.PYTHON)
    assert tree is not None
    assert has_errors is True


def test_parse_typescript_and_tsx():
    """Verify parsing TypeScript and TSX."""
    engine = TreeSitterEngine()
    ts_source = b"export interface Config { timeout: number; }"
    tree, has_errors = engine.parse_source(ts_source, Language.TYPESCRIPT)
    assert tree is not None
    assert has_errors is False

    tsx_source = b"export const App = () => <div>Hello</div>;"
    tree, has_errors = engine.parse_source(tsx_source, Language.TSX)
    assert tree is not None
    assert has_errors is False
