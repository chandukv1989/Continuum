"""Unit tests for AST symbol extraction."""
import pytest

from backend.app.scanner.contracts import Language, SymbolKind
from backend.app.scanner.parser import TreeSitterEngine
from backend.app.scanner.symbols import SymbolExtractor, generate_symbol_id


def test_deterministic_symbol_id():
    """Verify symbol ID is deterministic and independent of line numbers."""
    id1 = generate_symbol_id("app/main.py", "app.main.run", SymbolKind.FUNCTION)
    id2 = generate_symbol_id("app/main.py", "app.main.run", SymbolKind.FUNCTION)
    assert id1 == id2
    assert len(id1) == 32

    id3 = generate_symbol_id("app/main.py", "app.main.run", SymbolKind.METHOD)
    assert id1 != id3


def test_extract_python_symbols():
    """Verify extracting Python classes, methods, functions, and docstrings."""
    source = b'''
"""Module docstring."""

class Calculator:
    """A calculator class."""

    def __init__(self):
        pass

    @property
    def precision(self):
        """Precision value."""
        return 2

    async def compute(self, x: int) -> int:
        return x * 2

def standalone_helper():
    pass
'''
    engine = TreeSitterEngine()
    tree, _ = engine.parse_source(source, Language.PYTHON)
    extractor = SymbolExtractor("math/calc.py", Language.PYTHON)
    symbols = extractor.extract(tree.root_node)

    names = {s.name: s for s in symbols}

    assert "Calculator" in names
    calc = names["Calculator"]
    assert calc.kind == SymbolKind.CLASS
    assert calc.docstring == "A calculator class."
    assert calc.parent_symbol_id is None
    assert calc.is_exported is True

    assert "__init__" in names
    init = names["__init__"]
    assert init.kind == SymbolKind.METHOD
    assert init.parent_symbol_id == calc.id

    assert "precision" in names
    prec = names["precision"]
    assert prec.kind == SymbolKind.METHOD
    assert prec.docstring == "Precision value."
    assert prec.parent_symbol_id == calc.id

    assert "compute" in names
    comp = names["compute"]
    assert comp.kind == SymbolKind.METHOD
    assert comp.parent_symbol_id == calc.id

    assert "standalone_helper" in names
    helper = names["standalone_helper"]
    assert helper.kind == SymbolKind.FUNCTION
    assert helper.parent_symbol_id is None


def test_extract_typescript_and_react_symbols():
    """Verify extracting TS interfaces, types, enums, React hooks, and components."""
    source = b"""
export interface UserProfile {
    id: string;
    name: string;
}

export type UserRole = 'admin' | 'member';

export enum Status {
    Active = 'ACTIVE',
    Inactive = 'INACTIVE',
}

export function useAuth() {
    return { user: null };
}

export const UserCard: React.FC<UserProfile> = ({ id, name }) => {
    return <div>{name}</div>;
};

export class UserService {
    async getUser(id: string) {
        return null;
    }
}
"""
    engine = TreeSitterEngine()
    tree, _ = engine.parse_source(source, Language.TSX)
    extractor = SymbolExtractor("src/components/UserCard.tsx", Language.TSX)
    symbols = extractor.extract(tree.root_node)

    names = {s.name: s for s in symbols}

    assert "UserProfile" in names
    assert names["UserProfile"].kind == SymbolKind.INTERFACE
    assert names["UserProfile"].is_exported is True

    assert "UserRole" in names
    assert names["UserRole"].kind == SymbolKind.TYPE_ALIAS

    assert "Status" in names
    assert names["Status"].kind == SymbolKind.ENUM

    assert "useAuth" in names
    assert names["useAuth"].kind == SymbolKind.REACT_HOOK

    assert "UserCard" in names
    assert names["UserCard"].kind == SymbolKind.REACT_COMPONENT

    assert "UserService" in names
    svc = names["UserService"]
    assert svc.kind == SymbolKind.CLASS

    assert "getUser" in names
    assert names["getUser"].kind == SymbolKind.METHOD
    assert names["getUser"].parent_symbol_id == svc.id
