"""Reconciliation and synchronization engine between Code Brain and Project Brain.

Maintains reference integrity across repository rescans without mutating or deleting human-authored knowledge.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Set

from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.core.logging import get_logger
from backend.app.project_brain.contracts import (
    ArtifactOwnership,
    CodeReferenceResolution,
    CodeSymbolRef,
    DiscrepancyEntity,
    DiscrepancyStatus,
    EvidenceState,
    ReferenceResolutionStatus,
)
from backend.app.project_brain.repository import ProjectBrainRepository
from backend.app.project_brain.resolver import CodeReferenceResolver

logger = get_logger("continuum.project_brain.sync")


@dataclass
class SyncReport:
    """Summary metrics of a reconciliation run."""

    entities_inspected: int = 0
    references_resolved: int = 0
    references_unresolved: int = 0
    references_stale: int = 0
    discrepancies_recorded: int = 0
    human_artifacts_preserved: int = 0
    resolutions: List[CodeReferenceResolution] = field(default_factory=list)


class ProjectBrainReconciler:
    """Reconciles soft Code Brain references in Project Brain while preserving human knowledge."""

    def __init__(
        self,
        project_brain_repo: ProjectBrainRepository,
        code_brain_repo: CodeBrainRepository,
    ) -> None:
        self.project_repo = project_brain_repo
        self.code_repo = code_brain_repo
        self.resolver = CodeReferenceResolver(code_brain_repo)

    def reconcile(self) -> SyncReport:
        """Run full non-destructive reconciliation across all Project Brain artifacts."""
        report = SyncReport()
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Architecture
        for arch in self.project_repo.list_architecture():
            report.entities_inspected += 1
            if arch.ownership == ArtifactOwnership.HUMAN_AUTHORED:
                report.human_artifacts_preserved += 1
            self._reconcile_refs(arch.id, "architecture", arch.code_refs, arch.ownership, report, now_iso)

        # 2. Features
        for feat in self.project_repo.list_features():
            report.entities_inspected += 1
            if feat.ownership == ArtifactOwnership.HUMAN_AUTHORED:
                report.human_artifacts_preserved += 1
            self._reconcile_refs(feat.id, "feature", feat.code_refs, feat.ownership, report, now_iso)

        # 3. Concepts
        for concept in self.project_repo.list_concepts():
            report.entities_inspected += 1
            if concept.ownership == ArtifactOwnership.HUMAN_AUTHORED:
                report.human_artifacts_preserved += 1
            self._reconcile_refs(concept.id, "concept", concept.code_refs, concept.ownership, report, now_iso)

        # 4. Conventions
        for conv in self.project_repo.list_conventions():
            report.entities_inspected += 1
            if conv.ownership == ArtifactOwnership.HUMAN_AUTHORED:
                report.human_artifacts_preserved += 1
            self._reconcile_refs(conv.id, "convention", conv.code_refs, conv.ownership, report, now_iso)

        # 5. Decisions
        for dec in self.project_repo.list_decisions():
            report.entities_inspected += 1
            if dec.ownership == ArtifactOwnership.HUMAN_AUTHORED:
                report.human_artifacts_preserved += 1
            self._reconcile_refs(dec.id, "decision", dec.code_refs, dec.ownership, report, now_iso)

        return report

    def reconcile_scoped(self, affected_paths: Set[str]) -> SyncReport:
        """Run scoped non-destructive reconciliation targeting only entities referencing affected paths.

        If an entity references at least one symbol whose file path matches affected_paths,
        or if affected_paths is empty (reconciles all), its references are re-evaluated.
        """
        report = SyncReport()
        now_iso = datetime.now(timezone.utc).isoformat()

        def entity_affected(code_refs: List[str]) -> bool:
            if not affected_paths:
                return True
            for uri in code_refs:
                try:
                    ref = CodeSymbolRef.from_uri(uri)
                    if ref.file_path in affected_paths:
                        return True
                except Exception:
                    pass
            return False

        # 1. Architecture
        for arch in self.project_repo.list_architecture():
            if not entity_affected(arch.code_refs):
                continue
            report.entities_inspected += 1
            if arch.ownership == ArtifactOwnership.HUMAN_AUTHORED:
                report.human_artifacts_preserved += 1
            self._reconcile_refs(arch.id, "architecture", arch.code_refs, arch.ownership, report, now_iso)

        # 2. Features
        for feat in self.project_repo.list_features():
            if not entity_affected(feat.code_refs):
                continue
            report.entities_inspected += 1
            if feat.ownership == ArtifactOwnership.HUMAN_AUTHORED:
                report.human_artifacts_preserved += 1
            self._reconcile_refs(feat.id, "feature", feat.code_refs, feat.ownership, report, now_iso)

        # 3. Concepts
        for concept in self.project_repo.list_concepts():
            if not entity_affected(concept.code_refs):
                continue
            report.entities_inspected += 1
            if concept.ownership == ArtifactOwnership.HUMAN_AUTHORED:
                report.human_artifacts_preserved += 1
            self._reconcile_refs(concept.id, "concept", concept.code_refs, concept.ownership, report, now_iso)

        # 4. Conventions
        for conv in self.project_repo.list_conventions():
            if not entity_affected(conv.code_refs):
                continue
            report.entities_inspected += 1
            if conv.ownership == ArtifactOwnership.HUMAN_AUTHORED:
                report.human_artifacts_preserved += 1
            self._reconcile_refs(conv.id, "convention", conv.code_refs, conv.ownership, report, now_iso)

        # 5. Decisions
        for dec in self.project_repo.list_decisions():
            if not entity_affected(dec.code_refs):
                continue
            report.entities_inspected += 1
            if dec.ownership == ArtifactOwnership.HUMAN_AUTHORED:
                report.human_artifacts_preserved += 1
            self._reconcile_refs(dec.id, "decision", dec.code_refs, dec.ownership, report, now_iso)

        return report


    def _reconcile_refs(
        self,
        entity_id: str,
        entity_type: str,
        code_refs: List[str],
        ownership: ArtifactOwnership,
        report: SyncReport,
        now_iso: str,
    ) -> None:
        """Resolve individual reference URIs for an entity and record discrepancies without mutating human data."""
        for uri in code_refs:
            try:
                res = self.resolver.resolve(uri)
                report.resolutions.append(res)

                if res.status == ReferenceResolutionStatus.RESOLVED:
                    report.references_resolved += 1
                elif res.status == ReferenceResolutionStatus.UNRESOLVED:
                    report.references_unresolved += 1
                    # Record discrepancy for tracking without modifying the entity
                    discrepancy = DiscrepancyEntity(
                        id=f"disc:{entity_id}:{res.ref.qualified_name}",
                        entity_id=entity_id,
                        entity_type=entity_type,
                        human_statement=f"References code symbol {uri}",
                        conflicting_evidence="Symbol not found in Code Brain after rescan",
                        detected_at=now_iso,
                        status=DiscrepancyStatus.OPEN,
                    )
                    self.project_repo.record_discrepancy(discrepancy)
                    report.discrepancies_recorded += 1
                elif res.status == ReferenceResolutionStatus.STALE:
                    report.references_stale += 1
                    discrepancy = DiscrepancyEntity(
                        id=f"disc:{entity_id}:{res.ref.qualified_name}",
                        entity_id=entity_id,
                        entity_type=entity_type,
                        human_statement=f"References code symbol at {res.ref.file_path}",
                        conflicting_evidence=f"Symbol relocated to {res.moved_to_path}",
                        detected_at=now_iso,
                        status=DiscrepancyStatus.OPEN,
                    )
                    self.project_repo.record_discrepancy(discrepancy)
                    report.discrepancies_recorded += 1
            except Exception as err:
                logger.warning(f"Failed resolving ref {uri} on {entity_id}: {err}")
                report.references_unresolved += 1
