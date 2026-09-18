"""Unit tests for non-destructive Project Brain reconciliation."""
from backend.app.code_brain.database import CodeBrainDatabase
from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.project_brain.contracts import (
    ArtifactOwnership,
    ConceptEntity,
    DecisionEntity,
    DecisionStatus,
    DiscrepancyStatus,
    EvidenceState,
    FeatureEntity,
    Provenance,
    ProvenanceSource,
)
from backend.app.project_brain.repository import ProjectBrainRepository
from backend.app.project_brain.sync import ProjectBrainReconciler


def test_reconciler_non_destructive_synchronization(tmp_path):
    # Setup Code Brain
    db_path = tmp_path / "symbols.db"
    db = CodeBrainDatabase(db_path)
    db.initialize_schema()
    code_repo = CodeBrainRepository(db_path)

    # Insert files and symbols
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO files (path, canonical_path, size_bytes, mtime, language, parse_status) "
            "VALUES ('src/engine.py', '/can/src/engine.py', 100, 1.0, 'python', 'success');"
        )
        conn.execute(
            "INSERT INTO files (path, canonical_path, size_bytes, mtime, language, parse_status) "
            "VALUES ('src/new_location/helper.py', '/can/src/new_location/helper.py', 100, 1.0, 'python', 'success');"
        )
        conn.execute(
            "INSERT INTO symbols (id, file_path, name, qualified_name, kind, language, start_line, start_col, end_line, end_col) "
            "VALUES ('sym_active', 'src/engine.py', 'Engine', 'Engine', 'class', 'python', 1, 0, 20, 1);"
        )
        conn.execute(
            "INSERT INTO symbols (id, file_path, name, qualified_name, kind, language, start_line, start_col, end_line, end_col) "
            "VALUES ('sym_moved', 'src/new_location/helper.py', 'Helper', 'Helper', 'class', 'python', 1, 0, 20, 1);"
        )

    # Setup Project Brain

    pb_dir = tmp_path / ".continuum"
    project_repo = ProjectBrainRepository(pb_dir)

    prov = Provenance(
        source=ProvenanceSource.DEVELOPER,
        created_at="2026-09-18T10:00:00Z",
        updated_at="2026-09-18T10:00:00Z",
    )

    # 1. ADR with active symbol
    project_repo.save_decision(
        DecisionEntity(
            id="ADR-0001",
            title="Use Engine",
            status=DecisionStatus.ACCEPTED,
            context="Context",
            decision="Decision",
            consequences="Consequences",
            code_refs=["sym://src/engine.py#Engine?kind=class"],
            date="2026-09-18",
            ownership=ArtifactOwnership.HUMAN_AUTHORED,
            evidence=EvidenceState.CONFIRMED,
            provenance=prov,
        )
    )

    # 2. Feature with relocated symbol
    project_repo.save_feature(
        FeatureEntity(
            id="feat:helper",
            name="Helper Utility",
            description="Utility routines",
            code_refs=["sym://src/old_location/helper.py#Helper?kind=class"],
            ownership=ArtifactOwnership.HUMAN_AUTHORED,
            evidence=EvidenceState.CONFIRMED,
            provenance=prov,
        )
    )

    # 3. Concept with missing symbol
    project_repo.save_concept(
        ConceptEntity(
            id="concept:legacy",
            name="Legacy Core",
            description="Deprecated module",
            code_refs=["sym://src/legacy.py#DeletedSymbol?kind=class"],
            ownership=ArtifactOwnership.HUMAN_AUTHORED,
            evidence=EvidenceState.CONFIRMED,
            provenance=prov,
        )
    )

    reconciler = ProjectBrainReconciler(project_brain_repo=project_repo, code_brain_repo=code_repo)
    report = reconciler.reconcile()

    assert report.entities_inspected == 3
    assert report.human_artifacts_preserved == 3
    assert report.references_resolved == 1
    assert report.references_stale == 1
    assert report.references_unresolved == 1
    assert report.discrepancies_recorded == 2

    # Verify discrepancies were recorded in discrepancies.yaml
    discrepancies = project_repo.list_discrepancies()
    assert len(discrepancies) == 2
    assert all(d.status == DiscrepancyStatus.OPEN for d in discrepancies)

    # Verify human files remain 100% intact and unchanged
    adr = project_repo.get_decision("ADR-0001")
    assert adr.ownership == ArtifactOwnership.HUMAN_AUTHORED
    assert adr.decision == "Decision"
