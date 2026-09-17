"""Unit tests for structural relationship extraction."""
import pytest

from backend.app.scanner.contracts import (
    EvidenceType,
    Language,
    RelationshipType,
    SymbolKind,
)
from backend.app.scanner.parser import TreeSitterEngine
from backend.app.scanner.relationships import RelationshipExtractor
from backend.app.scanner.symbols import SymbolExtractor


def test_extract_python_relationships():
    """Verify extracting Python CONTAINS, IMPORTS, EXPORTS, and EXTENDS relationships."""
    source = b"""
import os
from pathlib import Path

class Animal:
    pass

class Dog(Animal):
    def bark(self):
        pass
"""
    file_path = "app/models.py"
    engine = TreeSitterEngine()
    tree, _ = engine.parse_source(source, Language.PYTHON)

    sym_extractor = SymbolExtractor(file_path, Language.PYTHON)
    symbols = sym_extractor.extract(tree.root_node)

    rel_extractor = RelationshipExtractor(file_path, Language.PYTHON)
    relationships = rel_extractor.extract(tree.root_node, symbols)

    types = [r.relationship_type for r in relationships]
    assert RelationshipType.CONTAINS in types
    assert RelationshipType.IMPORTS in types
    assert RelationshipType.EXPORTS in types
    assert RelationshipType.EXTENDS in types

    # Check IMPORTS
    imports = [r for r in relationships if r.relationship_type == RelationshipType.IMPORTS]
    imported_targets = {i.target_name for i in imports}
    assert "os" in imported_targets
    assert "pathlib" in imported_targets

    # Check EXTENDS
    extends = [r for r in relationships if r.relationship_type == RelationshipType.EXTENDS]
    assert len(extends) >= 1
    assert extends[0].target_name == "Animal"
    assert extends[0].evidence_type == EvidenceType.CONFIRMED

    # Check CONTAINS: Dog contains bark
    dog_sym = next(s for s in symbols if s.name == "Dog")
    dog_contains = [
        r
        for r in relationships
        if r.relationship_type == RelationshipType.CONTAINS and r.source_id == dog_sym.id
    ]
    assert len(dog_contains) == 1
    assert dog_contains[0].target_name == "bark"


def test_extract_typescript_relationships():
    """Verify extracting TypeScript IMPORTS, EXPORTS, EXTENDS, and IMPLEMENTS relationships."""
    source = b"""
import React from 'react';
import { BaseService } from './base';

export interface IService {
    execute(): void;
}

export class AppService extends BaseService implements IService {
    execute(): void {}
}
"""
    file_path = "src/services/app.ts"
    engine = TreeSitterEngine()
    tree, _ = engine.parse_source(source, Language.TYPESCRIPT)

    sym_extractor = SymbolExtractor(file_path, Language.TYPESCRIPT)
    symbols = sym_extractor.extract(tree.root_node)

    rel_extractor = RelationshipExtractor(file_path, Language.TYPESCRIPT)
    relationships = rel_extractor.extract(tree.root_node, symbols)

    types = [r.relationship_type for r in relationships]
    assert RelationshipType.IMPORTS in types
    assert RelationshipType.EXPORTS in types
    assert RelationshipType.EXTENDS in types
    assert RelationshipType.IMPLEMENTS in types

    # Check imports
    imports = [r for r in relationships if r.relationship_type == RelationshipType.IMPORTS]
    import_targets = {i.target_name for i in imports}
    assert "react" in import_targets
    assert "./base" in import_targets

    # Check extends and implements
    extends = [r for r in relationships if r.relationship_type == RelationshipType.EXTENDS]
    assert any(e.target_name == "BaseService" for e in extends)

    implements = [r for r in relationships if r.relationship_type == RelationshipType.IMPLEMENTS]
    assert any(i.target_name == "IService" for i in implements)
