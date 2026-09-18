"""Synchronous Incremental Repository Scanner for Continuum Phase 4.1.

Coordinates:
1. Change detection (Filesystem content hash diff)
2. Targeted Tree-sitter parsing of modified and added files
3. Atomic SQLite Code Brain updates
4. Scoped Project Brain reconciliation
Preserves the critical invariant:
FullScan(final_state) == FullScan(initial_state) + IncrementalScan(delta)
"""
from pathlib import Path
import time
from typing import Dict, List, Optional, Set

from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.core.exceptions import ScannerException
from backend.app.core.logging import get_logger
from backend.app.project_brain.repository import ProjectBrainRepository
from backend.app.project_brain.sync import ProjectBrainReconciler, SyncReport
from backend.app.scanner.contracts import (
    ChangeSet,
    ChangeType,
    DiscoveredFile,
    FileFilterStatus,
    IncrementalScanResult,
    ParseResult,
    ParseStatus,
    ScanMetrics,
)
from backend.app.scanner.detector import ChangeDetector
from backend.app.scanner.filtering import FileFilter
from backend.app.scanner.parser import TreeSitterEngine
from backend.app.scanner.relationships import RelationshipExtractor
from backend.app.scanner.symbols import SymbolExtractor
from backend.app.workspace.context import WorkspaceContext

logger = get_logger("continuum.scanner.incremental")


class IncrementalRepositoryScanner:
    """Headless orchestrator executing targeted incremental scans."""

    def __init__(
        self,
        context: WorkspaceContext,
        parser_engine: Optional[TreeSitterEngine] = None,
        file_filter: Optional[FileFilter] = None,
        code_brain_repo: Optional[CodeBrainRepository] = None,
        project_brain_repo: Optional[ProjectBrainRepository] = None,
    ) -> None:
        self.context = context
        self.config = context.config
        self.parser_engine = parser_engine or TreeSitterEngine()

        self.file_filter = file_filter or FileFilter(
            max_file_size_bytes=self.config.max_file_size_bytes,
            ignore_patterns=self.config.scanner_ignore_patterns,
        )

        self.db_path = context.code_brain_db_path
        if code_brain_repo is None:
            self.code_brain_repo = CodeBrainRepository(self.db_path)
        else:
            self.code_brain_repo = code_brain_repo

        if project_brain_repo is None:
            project_brain_dir = context.canonical_root / ".continuum"
            self.project_brain_repo = ProjectBrainRepository(project_brain_dir)
        else:
            self.project_brain_repo = project_brain_repo

        self.detector = ChangeDetector(
            context=self.context,
            code_brain_repo=self.code_brain_repo,
            file_filter=self.file_filter,
        )

    def scan_incremental(
        self,
        reconcile_project_brain: bool = True,
        use_git_acceleration: bool = False,
    ) -> IncrementalScanResult:
        """Perform a synchronous, targeted incremental scan of repository changes.

        Returns:
            IncrementalScanResult containing change_set, parse_results, and metrics.
        """
        start_time = time.perf_counter()
        metrics = ScanMetrics()

        # 1. Detect changes
        change_set, parseable_candidates = self.detector.detect_changes(
            use_git_acceleration=use_git_acceleration
        )

        metrics.files_discovered = len(change_set.changes)

        if change_set.is_empty:
            metrics.scan_duration_seconds = time.perf_counter() - start_time
            return IncrementalScanResult(
                project_id=self.context.identity.project_id,
                canonical_root=self.context.canonical_root.as_posix(),
                symbols_db_path=self.db_path.as_posix(),
                change_set=change_set,
                parse_results=[],
                metrics=metrics,
                reconciliation_report=None,
            )

        # 2. Determine affected files and paths to delete
        deleted_paths: List[str] = []
        for change in change_set.changes:
            if change.change_type == ChangeType.DELETED:
                deleted_paths.append(change.path)
            elif change.change_type == ChangeType.RENAMED and change.old_path:
                deleted_paths.append(change.old_path)

        # 3. Parse only changed files (ADDED, MODIFIED, RENAMED)
        parse_results: List[ParseResult] = []
        files_to_persist: List[DiscoveredFile] = []

        for path, df in parseable_candidates.items():
            files_to_persist.append(df)
            if df.status != FileFilterStatus.PARSEABLE:
                metrics.files_filtered += 1
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

        # 4. Atomic SQLite Code Brain Transaction
        persist_start = time.perf_counter()
        try:
            self.code_brain_repo.apply_incremental_scan(
                deleted_paths=deleted_paths,
                scanned_files=files_to_persist,
                parse_results=parse_results,
                batch_size=self.config.scanner_batch_size,
            )
        except Exception as err:
            logger.error(f"Failed to apply incremental scan into Code Brain: {err}")
            raise ScannerException(
                f"Incremental Code Brain update failed: {err}",
                details={"db_path": self.db_path.as_posix(), "error": str(err)},
            )
        metrics.persistence_duration_seconds = time.perf_counter() - persist_start

        # 5. Scoped Project Brain Reconciliation
        reconcile_report_dict = None
        if reconcile_project_brain:
            reconciler = ProjectBrainReconciler(
                project_brain_repo=self.project_brain_repo,
                code_brain_repo=self.code_brain_repo,
            )
            affected_paths: Set[str] = set()
            for c in change_set.changes:
                affected_paths.add(c.path)
                if c.old_path:
                    affected_paths.add(c.old_path)

            report = reconciler.reconcile_scoped(affected_paths=affected_paths)
            reconcile_report_dict = {
                "entities_inspected": report.entities_inspected,
                "references_resolved": report.references_resolved,
                "references_unresolved": report.references_unresolved,
                "references_stale": report.references_stale,
                "discrepancies_recorded": report.discrepancies_recorded,
                "human_artifacts_preserved": report.human_artifacts_preserved,
            }

        logger.info(
            "Incremental repository scan complete",
            extra={
                "changes": len(change_set.changes),
                "files_parsed": metrics.files_parsed,
                "symbols_extracted": metrics.symbols_extracted,
                "duration": round(metrics.scan_duration_seconds, 4),
            },
        )

        return IncrementalScanResult(
            project_id=self.context.identity.project_id,
            canonical_root=self.context.canonical_root.as_posix(),
            symbols_db_path=self.db_path.as_posix(),
            change_set=change_set,
            parse_results=parse_results,
            metrics=metrics,
            reconciliation_report=reconcile_report_dict,
        )

    def _process_single_file(self, discovered_file: DiscoveredFile) -> ParseResult:
        """Process a single file through the Tree-sitter and extraction pipeline."""
        file_path_str = discovered_file.relative_path
        lang = discovered_file.language

        try:
            with open(discovered_file.canonical_path, "rb") as f:
                source_bytes = f.read()

            tree, has_syntax_errors = self.parser_engine.parse_source(source_bytes, lang)
            root_node = tree.root_node

            symbol_extractor = SymbolExtractor(file_path=file_path_str, language=lang)
            symbols = symbol_extractor.extract(root_node)

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
