"""Deterministic AST symbol extraction for Continuum Phase 2.

Extracts functions, async functions, classes, methods, interfaces, type aliases,
enums, React components, and React hooks from Python and TypeScript/JavaScript ASTs.
"""
import hashlib
import re
from pathlib import Path
from typing import List, Optional, Tuple
import tree_sitter

from backend.app.scanner.contracts import Language, SymbolKind, SymbolRecord

HOOK_REGEX = re.compile(r"^use[A-Z][a-zA-Z0-9_]*$")
COMPONENT_REGEX = re.compile(r"^[A-Z][a-zA-Z0-9_]*$")


def generate_symbol_id(file_path: str, qualified_name: str, kind: SymbolKind) -> str:
    """Generate deterministic 32-character SHA-256 symbol ID.

    Never uses raw line numbers, ensuring stability across unrelated edits.
    """
    raw = f"{file_path}:{qualified_name}:{kind.value}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def derive_module_prefix(file_path: str) -> str:
    """Derive dot-separated module prefix from relative POSIX file path.

    Example: 'backend/app/main.py' -> 'backend.app.main'
             'src/components/Header.tsx' -> 'src.components.Header'
    """
    path = Path(file_path)
    # Strip known extensions
    suffixes = [".py", ".pyi", ".ts", ".mts", ".cts", ".tsx", ".js", ".mjs", ".cjs", ".jsx"]
    name = path.name
    for s in suffixes:
        if name.endswith(s):
            name = name[: -len(s)]
            break
    parts = list(path.parent.parts) + ([name] if name else [])
    # Clean leading dots or empty parts
    clean_parts = [p for p in parts if p and p != "."]
    return ".".join(clean_parts) if clean_parts else name


def _get_python_docstring(body_node: Optional[tree_sitter.Node]) -> Optional[str]:
    """Extract docstring from Python function or class body."""
    if not body_node:
        return None
    for child in body_node.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "string":
                    text = sub.text.decode("utf-8", errors="replace")
                    # Clean triple quotes or single quotes
                    cleaned = text.strip()
                    for quote in ('"""', "'''", '"', "'"):
                        if cleaned.startswith(quote) and cleaned.endswith(quote) and len(cleaned) >= 2 * len(quote):
                            cleaned = cleaned[len(quote) : -len(quote)]
                            break
                    return cleaned.strip()
            break
    return None


def _get_js_docstring(node: tree_sitter.Node) -> Optional[str]:
    """Extract preceding JSDoc comment for TypeScript/JavaScript node."""
    prev = node.prev_sibling
    if prev and prev.type == "comment":
        text = prev.text.decode("utf-8", errors="replace").strip()
        if text.startswith("/**"):
            lines = []
            for line in text.splitlines():
                stripped = line.strip().lstrip("/*").rstrip("*/").strip()
                if stripped:
                    lines.append(stripped)
            return "\n".join(lines)
    return None


def _safe_node_location(node: tree_sitter.Node) -> Tuple[int, int, int, int]:
    """Extract (start_line, start_column, end_line, end_column) from node safely.

    Uses 0-indexed tuple access (point[0], point[1]) on start_point and end_point
    to avoid segfault bugs in tree-sitter 0.26.0 getset_descriptors (.row / .column).
    Converts 0-indexed row to 1-indexed line number.
    """
    sp = node.start_point
    ep = node.end_point
    return sp[0] + 1, sp[1], ep[0] + 1, ep[1]


class SymbolExtractor:
    """Extracts structural SymbolRecords from Tree-sitter syntax trees."""

    def __init__(self, file_path: str, language: Language) -> None:
        self.file_path = file_path
        self.language = language
        self.module_prefix = derive_module_prefix(file_path)
        self.symbols: List[SymbolRecord] = []

    def extract(self, root_node: tree_sitter.Node) -> List[SymbolRecord]:
        """Extract all deterministic symbols from root AST node."""
        self.symbols.clear()
        if self.language == Language.PYTHON:
            self._extract_python_symbols(root_node, parent_id=None, parent_qname=self.module_prefix)
        elif self.language in (Language.TYPESCRIPT, Language.TSX, Language.JAVASCRIPT, Language.JSX):
            self._extract_js_ts_symbols(root_node, parent_id=None, parent_qname=self.module_prefix)
        return self.symbols

    # -------------------------------------------------------------------------
    # PYTHON EXTRACTION
    # -------------------------------------------------------------------------

    def _extract_python_symbols(
        self,
        node: tree_sitter.Node,
        parent_id: Optional[str],
        parent_qname: str,
    ) -> None:
        for child in node.children:
            if child.type == "decorated_definition":
                inner_def = child.child_by_field_name("definition")
                if inner_def:
                    self._process_python_definition(inner_def, parent_id, parent_qname, wrapper_node=child)
            elif child.type in ("function_definition", "class_definition"):
                self._process_python_definition(child, parent_id, parent_qname, wrapper_node=child)

    def _process_python_definition(
        self,
        node: tree_sitter.Node,
        parent_id: Optional[str],
        parent_qname: str,
        wrapper_node: tree_sitter.Node,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = name_node.text.decode("utf-8", errors="replace")
        qualified_name = f"{parent_qname}.{name}" if parent_qname else name

        body = node.child_by_field_name("body")
        docstring = _get_python_docstring(body)

        start_line, start_col, end_line, end_col = _safe_node_location(wrapper_node)

        if node.type == "class_definition":
            kind = SymbolKind.CLASS
            symbol_id = generate_symbol_id(self.file_path, qualified_name, kind)
            # Top-level classes in python modules are exported
            is_exported = parent_id is None and not name.startswith("_")

            record = SymbolRecord(
                id=symbol_id,
                file_path=self.file_path,
                name=name,
                qualified_name=qualified_name,
                kind=kind,
                language=self.language,
                parent_symbol_id=parent_id,
                start_line=start_line,
                start_column=start_col,
                end_line=end_line,
                end_column=end_col,
                is_exported=is_exported,
                docstring=docstring,
            )
            self.symbols.append(record)

            # Traverse class body for methods
            if body:
                for b_child in body.children:
                    if b_child.type == "decorated_definition":
                        inner_def = b_child.child_by_field_name("definition")
                        if inner_def and inner_def.type == "function_definition":
                            self._process_python_definition(
                                inner_def,
                                parent_id=symbol_id,
                                parent_qname=qualified_name,
                                wrapper_node=b_child,
                            )
                    elif b_child.type == "function_definition":
                        self._process_python_definition(
                            b_child,
                            parent_id=symbol_id,
                            parent_qname=qualified_name,
                            wrapper_node=b_child,
                        )

        elif node.type == "function_definition":
            kind = SymbolKind.METHOD if parent_id is not None else SymbolKind.FUNCTION
            symbol_id = generate_symbol_id(self.file_path, qualified_name, kind)
            is_exported = parent_id is None and not name.startswith("_")

            record = SymbolRecord(
                id=symbol_id,
                file_path=self.file_path,
                name=name,
                qualified_name=qualified_name,
                kind=kind,
                language=self.language,
                parent_symbol_id=parent_id,
                start_line=start_line,
                start_column=start_col,
                end_line=end_line,
                end_column=end_col,
                is_exported=is_exported,
                docstring=docstring,
            )
            self.symbols.append(record)

            # Check nested functions
            if body:
                for b_child in body.children:
                    if b_child.type in ("function_definition", "decorated_definition"):
                        target = b_child.child_by_field_name("definition") if b_child.type == "decorated_definition" else b_child
                        if target and target.type == "function_definition":
                            self._process_python_definition(
                                target,
                                parent_id=symbol_id,
                                parent_qname=qualified_name,
                                wrapper_node=b_child,
                            )

    # -------------------------------------------------------------------------
    # JAVASCRIPT / TYPESCRIPT EXTRACTION
    # -------------------------------------------------------------------------

    def _extract_js_ts_symbols(
        self,
        node: tree_sitter.Node,
        parent_id: Optional[str],
        parent_qname: str,
    ) -> None:
        for child in node.children:
            is_exported = False
            target_node = child

            if child.type == "export_statement":
                is_exported = True
                decl = child.child_by_field_name("declaration")
                if decl:
                    target_node = decl
                else:
                    # Might be export default or export { x }
                    for sub in child.children:
                        if sub.type in (
                            "function_declaration",
                            "class_declaration",
                            "interface_declaration",
                            "type_alias_declaration",
                            "enum_declaration",
                            "lexical_declaration",
                            "variable_declaration",
                        ):
                            target_node = sub
                            break

            self._process_js_ts_node(target_node, parent_id, parent_qname, is_exported=is_exported)

    def _process_js_ts_node(
        self,
        node: tree_sitter.Node,
        parent_id: Optional[str],
        parent_qname: str,
        is_exported: bool,
    ) -> None:
        docstring = _get_js_docstring(node)
        start_line, start_col, end_line, end_col = _safe_node_location(node)

        # 1. Classes
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = name_node.text.decode("utf-8", errors="replace")
            qualified_name = f"{parent_qname}.{name}" if parent_qname else name
            kind = SymbolKind.CLASS
            symbol_id = generate_symbol_id(self.file_path, qualified_name, kind)

            self.symbols.append(
                SymbolRecord(
                    id=symbol_id,
                    file_path=self.file_path,
                    name=name,
                    qualified_name=qualified_name,
                    kind=kind,
                    language=self.language,
                    parent_symbol_id=parent_id,
                    start_line=start_line,
                    start_column=start_col,
                    end_line=end_line,
                    end_column=end_col,
                    is_exported=is_exported,
                    docstring=docstring,
                )
            )

            # Class body methods
            body = node.child_by_field_name("body")
            if body:
                for b_child in body.children:
                    if b_child.type == "method_definition":
                        m_name_node = b_child.child_by_field_name("name")
                        if m_name_node:
                            m_name = m_name_node.text.decode("utf-8", errors="replace")
                            m_qname = f"{qualified_name}.{m_name}"
                            m_kind = SymbolKind.METHOD
                            m_id = generate_symbol_id(self.file_path, m_qname, m_kind)
                            m_s_line, m_s_col, m_e_line, m_e_col = _safe_node_location(b_child)
                            self.symbols.append(
                                SymbolRecord(
                                    id=m_id,
                                    file_path=self.file_path,
                                    name=m_name,
                                    qualified_name=m_qname,
                                    kind=m_kind,
                                    language=self.language,
                                    parent_symbol_id=symbol_id,
                                    start_line=m_s_line,
                                    start_column=m_s_col,
                                    end_line=m_e_line,
                                    end_column=m_e_col,
                                    is_exported=False,
                                    docstring=_get_js_docstring(b_child),
                                )
                            )

        # 2. Functions
        elif node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = name_node.text.decode("utf-8", errors="replace")
            qualified_name = f"{parent_qname}.{name}" if parent_qname else name

            kind = self._classify_function_name(name)
            symbol_id = generate_symbol_id(self.file_path, qualified_name, kind)

            self.symbols.append(
                SymbolRecord(
                    id=symbol_id,
                    file_path=self.file_path,
                    name=name,
                    qualified_name=qualified_name,
                    kind=kind,
                    language=self.language,
                    parent_symbol_id=parent_id,
                    start_line=start_line,
                    start_column=start_col,
                    end_line=end_line,
                    end_column=end_col,
                    is_exported=is_exported,
                    docstring=docstring,
                )
            )

        # 3. Interfaces (TypeScript)
        elif node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = name_node.text.decode("utf-8", errors="replace")
            qualified_name = f"{parent_qname}.{name}" if parent_qname else name
            kind = SymbolKind.INTERFACE
            symbol_id = generate_symbol_id(self.file_path, qualified_name, kind)

            self.symbols.append(
                SymbolRecord(
                    id=symbol_id,
                    file_path=self.file_path,
                    name=name,
                    qualified_name=qualified_name,
                    kind=kind,
                    language=self.language,
                    parent_symbol_id=parent_id,
                    start_line=start_line,
                    start_column=start_col,
                    end_line=end_line,
                    end_column=end_col,
                    is_exported=is_exported,
                    docstring=docstring,
                )
            )

        # 4. Type Aliases (TypeScript)
        elif node.type == "type_alias_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = name_node.text.decode("utf-8", errors="replace")
            qualified_name = f"{parent_qname}.{name}" if parent_qname else name
            kind = SymbolKind.TYPE_ALIAS
            symbol_id = generate_symbol_id(self.file_path, qualified_name, kind)

            self.symbols.append(
                SymbolRecord(
                    id=symbol_id,
                    file_path=self.file_path,
                    name=name,
                    qualified_name=qualified_name,
                    kind=kind,
                    language=self.language,
                    parent_symbol_id=parent_id,
                    start_line=start_line,
                    start_column=start_col,
                    end_line=end_line,
                    end_column=end_col,
                    is_exported=is_exported,
                    docstring=docstring,
                )
            )

        # 5. Enums (TypeScript)
        elif node.type == "enum_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = name_node.text.decode("utf-8", errors="replace")
            qualified_name = f"{parent_qname}.{name}" if parent_qname else name
            kind = SymbolKind.ENUM
            symbol_id = generate_symbol_id(self.file_path, qualified_name, kind)

            self.symbols.append(
                SymbolRecord(
                    id=symbol_id,
                    file_path=self.file_path,
                    name=name,
                    qualified_name=qualified_name,
                    kind=kind,
                    language=self.language,
                    parent_symbol_id=parent_id,
                    start_line=start_line,
                    start_column=start_col,
                    end_line=end_line,
                    end_column=end_col,
                    is_exported=is_exported,
                    docstring=docstring,
                )
            )

        # 6. Variables, Constants, Arrow Functions, Components
        elif node.type in ("lexical_declaration", "variable_declaration"):
            for declarator in node.children:
                if declarator.type == "variable_declarator":
                    d_name_node = declarator.child_by_field_name("name")
                    if not d_name_node:
                        continue
                    name = d_name_node.text.decode("utf-8", errors="replace")
                    qualified_name = f"{parent_qname}.{name}" if parent_qname else name

                    value_node = declarator.child_by_field_name("value")
                    is_func_like = value_node and value_node.type in (
                        "arrow_function",
                        "function_expression",
                    )

                    if is_func_like:
                        kind = self._classify_function_name(name)
                    elif is_exported:
                        kind = SymbolKind.VARIABLE
                    else:
                        # Non-exported primitive variables are omitted to keep Code Brain focused
                        continue

                    symbol_id = generate_symbol_id(self.file_path, qualified_name, kind)
                    d_s_line, d_s_col, d_e_line, d_e_col = _safe_node_location(declarator)
                    self.symbols.append(
                        SymbolRecord(
                            id=symbol_id,
                            file_path=self.file_path,
                            name=name,
                            qualified_name=qualified_name,
                            kind=kind,
                            language=self.language,
                            parent_symbol_id=parent_id,
                            start_line=d_s_line,
                            start_column=d_s_col,
                            end_line=d_e_line,
                            end_column=d_e_col,
                            is_exported=is_exported,
                            docstring=docstring,
                        )
                    )

    def _classify_function_name(self, name: str) -> SymbolKind:
        """Classify function name deterministically according to naming patterns."""
        if HOOK_REGEX.match(name):
            return SymbolKind.REACT_HOOK
        if self.language in (Language.TSX, Language.JSX) and COMPONENT_REGEX.match(name):
            return SymbolKind.REACT_COMPONENT
        return SymbolKind.FUNCTION
