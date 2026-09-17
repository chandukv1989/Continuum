"""Tree-sitter AST parsing engine for Continuum Phase 2.

Manages grammar loading, parser initialization, and source code parsing
for Python, TypeScript, TSX, JavaScript, and JSX.
"""
from typing import Dict, Optional, Tuple
import tree_sitter
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript

from backend.app.core.exceptions import ParserException
from backend.app.core.logging import get_logger
from backend.app.scanner.contracts import Language

logger = get_logger("continuum.scanner.parser")


class TreeSitterEngine:
    """Authoritative Tree-sitter parser manager and execution engine."""

    def __init__(self) -> None:
        self._parsers: Dict[Language, tree_sitter.Parser] = {}
        self._initialize_parsers()

    def _initialize_parsers(self) -> None:
        """Initialize and cache Tree-sitter parsers for all supported languages."""
        try:
            # Python
            py_lang = tree_sitter.Language(tree_sitter_python.language())
            self._parsers[Language.PYTHON] = tree_sitter.Parser(py_lang)

            # TypeScript
            ts_lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
            self._parsers[Language.TYPESCRIPT] = tree_sitter.Parser(ts_lang)

            # TSX
            tsx_lang = tree_sitter.Language(tree_sitter_typescript.language_tsx())
            self._parsers[Language.TSX] = tree_sitter.Parser(tsx_lang)

            # JavaScript & JSX
            js_lang = tree_sitter.Language(tree_sitter_javascript.language())
            self._parsers[Language.JAVASCRIPT] = tree_sitter.Parser(js_lang)
            self._parsers[Language.JSX] = tree_sitter.Parser(js_lang)

        except Exception as err:
            raise ParserException(
                f"Failed to initialize Tree-sitter language grammars: {err}",
                details={"error": str(err)},
            )

    def get_parser(self, language: Language) -> tree_sitter.Parser:
        """Retrieve pre-initialized parser for the requested language."""
        if language not in self._parsers:
            raise ParserException(
                f"No Tree-sitter parser available for language: {language.value}",
                details={"language": language.value},
            )
        return self._parsers[language]

    def parse_source(
        self,
        source_bytes: bytes,
        language: Language,
    ) -> Tuple[tree_sitter.Tree, bool]:
        """Parse source code bytes into a Tree-sitter AST.

        Args:
            source_bytes: Raw source file bytes.
            language: Target Language enum.

        Returns:
            Tuple of (tree_sitter.Tree, has_syntax_errors: bool).

        Raises:
            ParserException: If the parser crashes unexpectedly or language is unsupported.
        """
        parser = self.get_parser(language)
        try:
            tree = parser.parse(source_bytes)
            if tree is None or tree.root_node is None:
                raise ParserException(
                    f"Tree-sitter returned empty AST for language {language.value}",
                    details={"language": language.value},
                )
            has_errors = tree.root_node.has_error
            return tree, has_errors
        except ParserException:
            raise
        except Exception as err:
            raise ParserException(
                f"Unexpected error parsing source with Tree-sitter ({language.value}): {err}",
                details={"language": language.value, "error": str(err)},
            )
