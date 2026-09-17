"""Deterministic structural relationship extraction for Continuum Phase 2.

Extracts CONFIRMED structural relationships (CONTAINS, IMPORTS, EXPORTS, EXTENDS, IMPLEMENTS)
directly from AST nodes without heuristic or probabilistic AI guesswork.
"""
import hashlib
from typing import List, Optional
import tree_sitter

from backend.app.scanner.contracts import (
    EvidenceType,
    Language,
    RelationshipRecord,
    RelationshipType,
    SymbolRecord,
)


def generate_relationship_id(
    source_id: str,
    rel_type: RelationshipType,
    target_name: str,
    file_path: str,
) -> str:
    """Generate deterministic 32-character SHA-256 relationship ID."""
    raw = f"{source_id}:{rel_type.value}:{target_name}:{file_path}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class RelationshipExtractor:
    """Extracts confirmed structural relationships from AST nodes and extracted symbols."""

    def __init__(self, file_path: str, language: Language) -> None:
        self.file_path = file_path
        self.language = language
        self.relationships: List[RelationshipRecord] = []

    def extract(
        self,
        root_node: tree_sitter.Node,
        symbols: List[SymbolRecord],
    ) -> List[RelationshipRecord]:
        """Extract all confirmed relationships for the file."""
        self.relationships.clear()

        # 1. CONTAINS and EXPORTS from symbols
        self._extract_symbol_hierarchy_and_exports(symbols)

        # 2. IMPORTS and EXTENDS/IMPLEMENTS from AST
        if self.language == Language.PYTHON:
            self._extract_python_relationships(root_node, symbols)
        elif self.language in (Language.TYPESCRIPT, Language.TSX, Language.JAVASCRIPT, Language.JSX):
            self._extract_js_ts_relationships(root_node, symbols)

        return self.relationships

    def _extract_symbol_hierarchy_and_exports(self, symbols: List[SymbolRecord]) -> None:
        for sym in symbols:
            # CONTAINS relationship
            if sym.parent_symbol_id:
                # Parent symbol contains child symbol
                rel_id = generate_relationship_id(
                    sym.parent_symbol_id,
                    RelationshipType.CONTAINS,
                    sym.id,
                    self.file_path,
                )
                self.relationships.append(
                    RelationshipRecord(
                        id=rel_id,
                        source_id=sym.parent_symbol_id,
                        target_name=sym.name,
                        target_id=sym.id,
                        relationship_type=RelationshipType.CONTAINS,
                        evidence_type=EvidenceType.CONFIRMED,
                        file_path=self.file_path,
                        line_number=sym.start_line,
                    )
                )
            else:
                # File contains top-level symbol
                rel_id = generate_relationship_id(
                    self.file_path,
                    RelationshipType.CONTAINS,
                    sym.id,
                    self.file_path,
                )
                self.relationships.append(
                    RelationshipRecord(
                        id=rel_id,
                        source_id=self.file_path,
                        target_name=sym.name,
                        target_id=sym.id,
                        relationship_type=RelationshipType.CONTAINS,
                        evidence_type=EvidenceType.CONFIRMED,
                        file_path=self.file_path,
                        line_number=sym.start_line,
                    )
                )

            # EXPORTS relationship
            if sym.is_exported:
                rel_id = generate_relationship_id(
                    self.file_path,
                    RelationshipType.EXPORTS,
                    sym.name,
                    self.file_path,
                )
                self.relationships.append(
                    RelationshipRecord(
                        id=rel_id,
                        source_id=self.file_path,
                        target_name=sym.name,
                        target_id=sym.id,
                        relationship_type=RelationshipType.EXPORTS,
                        evidence_type=EvidenceType.CONFIRMED,
                        file_path=self.file_path,
                        line_number=sym.start_line,
                    )
                )

    # -------------------------------------------------------------------------
    # PYTHON RELATIONSHIPS
    # -------------------------------------------------------------------------

    def _extract_python_relationships(
        self,
        root_node: tree_sitter.Node,
        symbols: List[SymbolRecord],
    ) -> None:
        symbol_by_name = {s.name: s for s in symbols}

        for child in root_node.children:
            line_num = child.start_point[0] + 1

            # Imports
            if child.type == "import_statement":
                # import a, b as c
                for name_node in child.children:
                    if name_node.type == "dotted_name":
                        mod = name_node.text.decode("utf-8", errors="replace")
                        self._add_import(mod, line_num)
                    elif name_node.type == "aliased_import":
                        dotted = name_node.child_by_field_name("name")
                        if dotted:
                            mod = dotted.text.decode("utf-8", errors="replace")
                            self._add_import(mod, line_num)

            elif child.type == "import_from_statement":
                # from a.b import c, d
                mod_name_node = child.child_by_field_name("module_name")
                mod_prefix = mod_name_node.text.decode("utf-8", errors="replace") if mod_name_node else ""
                self._add_import(mod_prefix, line_num)

            # Class inheritance (EXTENDS)
            elif child.type in ("class_definition", "decorated_definition"):
                cls_node = child if child.type == "class_definition" else child.child_by_field_name("definition")
                if cls_node and cls_node.type == "class_definition":
                    cls_name_node = cls_node.child_by_field_name("name")
                    if cls_name_node:
                        cls_name = cls_name_node.text.decode("utf-8", errors="replace")
                        sym = symbol_by_name.get(cls_name)
                        if sym:
                            superclasses = cls_node.child_by_field_name("superclasses")
                            if superclasses:
                                for arg in superclasses.children:
                                    if arg.type in ("identifier", "attribute"):
                                        base_name = arg.text.decode("utf-8", errors="replace")
                                        rel_id = generate_relationship_id(
                                            sym.id,
                                            RelationshipType.EXTENDS,
                                            base_name,
                                            self.file_path,
                                        )
                                        self.relationships.append(
                                            RelationshipRecord(
                                                id=rel_id,
                                                source_id=sym.id,
                                                target_name=base_name,
                                                relationship_type=RelationshipType.EXTENDS,
                                                evidence_type=EvidenceType.CONFIRMED,
                                                file_path=self.file_path,
                                                line_number=cls_node.start_point[0] + 1,
                                            )
                                        )

    # -------------------------------------------------------------------------
    # TYPESCRIPT / JAVASCRIPT RELATIONSHIPS
    # -------------------------------------------------------------------------

    def _extract_js_ts_relationships(
        self,
        root_node: tree_sitter.Node,
        symbols: List[SymbolRecord],
    ) -> None:
        symbol_by_name = {s.name: s for s in symbols}

        for child in root_node.children:
            line_num = child.start_point[0] + 1

            # 1. Imports
            if child.type == "import_statement":
                source = child.child_by_field_name("source")
                if source:
                    # Strip surrounding quotes
                    raw = source.text.decode("utf-8", errors="replace").strip("'\"")
                    self._add_import(raw, line_num)

            # 2. Re-exports e.g. export { X } from './X'
            elif child.type == "export_statement":
                source = child.child_by_field_name("source")
                if source:
                    raw = source.text.decode("utf-8", errors="replace").strip("'\"")
                    self._add_import(raw, line_num)

            # 3. Class EXTENDS and IMPLEMENTS
            target = child
            if child.type == "export_statement":
                decl = child.child_by_field_name("declaration")
                if decl:
                    target = decl

            if target.type == "class_declaration":
                c_name_node = target.child_by_field_name("name")
                if c_name_node:
                    c_name = c_name_node.text.decode("utf-8", errors="replace")
                    sym = symbol_by_name.get(c_name)
                    if sym:
                        for sub in target.children:
                            if sub.type == "class_heritage":
                                self._extract_class_heritage(sym, sub)

            # 4. Interface EXTENDS
            elif target.type == "interface_declaration":
                i_name_node = target.child_by_field_name("name")
                if i_name_node:
                    i_name = i_name_node.text.decode("utf-8", errors="replace")
                    sym = symbol_by_name.get(i_name)
                    if sym:
                        for sub in target.children:
                            if sub.type == "extends_type_clause":
                                for clause_child in sub.children:
                                    if clause_child.type in ("type_identifier", "identifier"):
                                        base_name = clause_child.text.decode("utf-8", errors="replace")
                                        rel_id = generate_relationship_id(
                                            sym.id,
                                            RelationshipType.EXTENDS,
                                            base_name,
                                            self.file_path,
                                        )
                                        self.relationships.append(
                                            RelationshipRecord(
                                                id=rel_id,
                                                source_id=sym.id,
                                                target_name=base_name,
                                                relationship_type=RelationshipType.EXTENDS,
                                                evidence_type=EvidenceType.CONFIRMED,
                                                file_path=self.file_path,
                                                line_number=target.start_point[0] + 1,
                                            )
                                        )

    def _extract_class_heritage(self, sym: SymbolRecord, heritage_node: tree_sitter.Node) -> None:
        """Extract extends and implements clauses from class heritage node."""
        for clause in heritage_node.children:
            if clause.type == "extends_clause":
                for c in clause.children:
                    if c.type in ("identifier", "type_identifier"):
                        base_name = c.text.decode("utf-8", errors="replace")
                        rel_id = generate_relationship_id(
                            sym.id,
                            RelationshipType.EXTENDS,
                            base_name,
                            self.file_path,
                        )
                        self.relationships.append(
                            RelationshipRecord(
                                id=rel_id,
                                source_id=sym.id,
                                target_name=base_name,
                                relationship_type=RelationshipType.EXTENDS,
                                evidence_type=EvidenceType.CONFIRMED,
                                file_path=self.file_path,
                                line_number=clause.start_point[0] + 1,
                            )
                        )
            elif clause.type == "implements_clause":
                for c in clause.children:
                    if c.type in ("identifier", "type_identifier"):
                        if_name = c.text.decode("utf-8", errors="replace")
                        rel_id = generate_relationship_id(
                            sym.id,
                            RelationshipType.IMPLEMENTS,
                            if_name,
                            self.file_path,
                        )
                        self.relationships.append(
                            RelationshipRecord(
                                id=rel_id,
                                source_id=sym.id,
                                target_name=if_name,
                                relationship_type=RelationshipType.IMPLEMENTS,
                                evidence_type=EvidenceType.CONFIRMED,
                                file_path=self.file_path,
                                line_number=clause.start_point[0] + 1,
                            )
                        )

    def _add_import(self, target_module: str, line_num: int) -> None:
        if not target_module:
            return
        rel_id = generate_relationship_id(
            self.file_path,
            RelationshipType.IMPORTS,
            target_module,
            self.file_path,
        )
        self.relationships.append(
            RelationshipRecord(
                id=rel_id,
                source_id=self.file_path,
                target_name=target_module,
                relationship_type=RelationshipType.IMPORTS,
                evidence_type=EvidenceType.CONFIRMED,
                file_path=self.file_path,
                line_number=line_num,
            )
        )
