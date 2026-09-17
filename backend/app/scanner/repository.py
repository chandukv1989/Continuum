"""RepositoryScanner Orchestrator for Continuum Phase 2.

Coordinates file discovery, filtering, Tree-sitter parsing, symbol extraction,
relationship extraction, and Code Brain SQLite persistence within the workspace boundary.
"""
from __future__ import annotations

from pathlib import Path
import time
from typing import TYPE_CHECKING, List, Optional

from backend.app.core.exceptions import ScannerException
from backend.app.core.logging import get_logger

if TYPE_CHECKING:
    from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.scanner.contracts import (
    DiscoveredFile,
    FileFilterStatus,
    Language,
    ParseResult,
    ParseStatus,
    ScanMetrics,
    ScanResult,
)
from backend.app.scanner.discovery import FileDiscovery
from backend.app.scanner.filtering import FileFilter
from backend.app.scanner.parser import TreeSitterEngine
from backend.app.scanner.relationships import RelationshipExtractor
from backend.app.scanner.symbols import SymbolExtractor
from backend.app.workspace.context import WorkspaceContext

logger = get_logger("continuum.scanner.orchestrator")


class RepositoryScanner:
    """Headless orchestrator executing the deterministic Scanner & Code Brain pipeline."""

    def __init__(
        self,
        context: WorkspaceContext,
        parser_engine: Optional[TreeSitterEngine] = None,
        file_filter: Optional[FileFilter] = None,
        code_brain_repo: Optional[CodeBrainRepository] = None,
    ) -> None:
        self.context = context
        self.config = context.config
        self.parser_engine = parser_engine or TreeSitterEngine()

        # Configure file filter from workspace settings
        self.file_filter = file_filter or FileFilter(
            max_file_size_bytes=self.config.max_file_size_bytes,
            ignore_patterns=self.config.scanner_ignore_patterns,
        )

        self.discovery = FileDiscovery(
            workspace_root=context.canonical_root,
            file_filter=self.file_filter,
        )

        # Code Brain SQLite repository at ~/.continuum/projects/<project-id>/symbols.db
        self.db_path = context.code_brain_db_path
        if code_brain_repo is None:
            from backend.app.code_brain.repository import CodeBrainRepository
            self.code_brain_repo = CodeBrainRepository(self.db_path)
        else:
            self.code_brain_repo = code_brain_repo

    def scan(self, persist: bool = True) -> ScanResult:
        """Execute a full deterministic scan of the workspace.

        Args:
            persist: If True, writes the facts to SQLite Code Brain.

        Returns:
            ScanResult containing discovered files, parse results, and metrics.
        """
        start_time = time.perf_counter()
        metrics = ScanMetrics()

        logger.info(
            "Starting repository scan",
            extra={
                "project_id": self.context.identity.project_id,
                "workspace": self.context.canonical_root.as_posix(),
            },
        )

        # 1. File Discovery & Filtering
        discovered_files = self.discovery.discover()
        metrics.files_discovered = len(discovered_files)
        metrics.files_filtered = sum(
            1 for f in discovered_files if f.status != FileFilterStatus.PARSEABLE
        )

        parse_results: List[ParseResult] = []

        # 2. Parseable File Processing Pipeline
        for df in discovered_files:
            if df.status != FileFilterStatus.PARSEABLE:
                continue

            pr = self._process_single_file(df)
            parse_results.append(pr)

            if pr.status in (ParseStatus.SUCCESS, ParseStatus.PARTIAL_ERROR):
                metrics.files_parsed += 1
                metrics.symbols_extracted += len(pr.symbols)
                metrics.relationships_extracted += len(pr.relationships)
            else:
                metrics.parse_failures += 1

        scan_end_time = time.perf_counter()
        metrics.scan_duration_seconds = scan_end_time - start_time

        # 3. Persistence into SQLite Code Brain
        if persist:
            persist_start = time.perf_counter()
            try:
                self.code_brain_repo.rebuild(
                    scanned_files=discovered_files,
                    parse_results=parse_results,
                    batch_size=self.config.scanner_batch_size,
                )
            except Exception as err:
                logger.error(f"Failed to persist scan into Code Brain: {err}")
                raise ScannerException(
                    f"Code Brain persistence failed: {err}",
                    details={"db_path": self.db_path.as_posix(), "error": str(err)},
                )
            metrics.persistence_duration_seconds = time.perf_counter() - persist_start

        logger.info(
            "Repository scan complete",
            extra={
                "files_discovered": metrics.files_discovered,
                "files_parsed": metrics.files_parsed,
                "symbols_extracted": metrics.symbols_extracted,
                "relationships_extracted": metrics.relationships_extracted,
                "duration": round(metrics.scan_duration_seconds, 3),
            },
        )

        return ScanResult(
            project_id=self.context.identity.project_id,
            canonical_root=self.context.canonical_root.as_posix(),
            symbols_db_path=self.db_path.as_posix(),
            scanned_files=discovered_files,
            parse_results=parse_results,
            metrics=metrics,
        )

    def _process_single_file(self, discovered_file: DiscoveredFile) -> ParseResult:
        """Process a single file through the Tree-sitter and extraction pipeline with error isolation."""
        file_path_str = discovered_file.relative_path
        lang = discovered_file.language

        try:
            # Read source bytes
            with open(discovered_file.canonical_path, "rb") as f:
                source_bytes = f.read()

            tree, has_syntax_errors = self.parser_engine.parse_source(source_bytes, lang)
            root_node = tree.root_node

            # Extract symbols
            symbol_extractor = SymbolExtractor(file_path=file_path_str, language=lang)
            symbols = symbol_extractor.extract(root_node)

            # Extract relationships
            relationship_extractor = RelationshipExtractor(file_path=file_path_str, language=lang)
            relationships = relationship_extractor.extract(root_node, symbols)

            status = ParseStatus.PARTIAL_ERROR if has_syntax_errors else ParseStatus.SUCCESS

            return ParseResult(
                file_path=file_path_str,
                status=status,
                language=lang,
                symbols=symbols,
                relationships=relationships,
                has_syntax_errors=has_syntax_errors,
            )

        except Exception as err:
            logger.warning(
                f"Error processing file '{file_path_str}': {err}",
                extra={"file": file_path_str, "error": str(err)},
            )
            return ParseResult(
                file_path=file_path_str,
                status=ParseStatus.FAILED,
                language=lang,
                symbols=[],
                relationships=[],
                has_syntax_errors=True,
                error_message=str(err),
            )
