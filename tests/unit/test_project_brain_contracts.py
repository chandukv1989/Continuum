"""Unit tests for Project Brain domain contracts, schemas, and URI serialization."""
import pytest
from backend.app.project_brain.contracts import (
    ArchitectureEntity,
    ArtifactOwnership,
    CodeSymbolRef,
    ConceptEntity,
    ConventionEntity,
    DecisionEntity,
    DecisionStatus,
    DiscrepancyEntity,
    DiscrepancyStatus,
    EvidenceState,
    FeatureEntity,
    ProjectMetadata,
    Provenance,
    ProvenanceSource,
    ReferenceResolutionStatus,
)


def test_code_symbol_ref_serialization_roundtrip():
    ref = CodeSymbolRef(
        file_path="backend/app/scanner/repository.py",
        qualified_name="RepositoryScanner",
        kind="class",
    )
    uri = ref.to_uri()
    assert uri == "sym://backend/app/scanner/repository.py#RepositoryScanner?kind=class"

    parsed = CodeSymbolRef.from_uri(uri)
    assert parsed.file_path == "backend/app/scanner/repository.py"
    assert parsed.qualified_name == "RepositoryScanner"
    assert parsed.kind == "class"


def test_code_symbol_ref_without_kind():
    ref = CodeSymbolRef(
        file_path="backend/app/core/logging.py",
        qualified_name="get_logger",
    )
    uri = ref.to_uri()
    assert uri == "sym://backend/app/core/logging.py#get_logger"

    parsed = CodeSymbolRef.from_uri(uri)
    assert parsed.file_path == "backend/app/core/logging.py"
    assert parsed.qualified_name == "get_logger"
    assert parsed.kind is None


def test_code_symbol_ref_invalid_uri():
    with pytest.raises(ValueError, match="must start with 'sym://'"):
        CodeSymbolRef.from_uri("http://example.com#func")

    with pytest.raises(ValueError, match="missing qualified name"):
        CodeSymbolRef.from_uri("sym://backend/app/main.py#")

    with pytest.raises(ValueError, match="missing file path"):
        CodeSymbolRef.from_uri("sym://#my_func")


def test_provenance_and_governance_models():
    prov = Provenance(
        source=ProvenanceSource.DEVELOPER,
        source_ref="git:commit-abc",
        created_at="2026-09-18T10:00:00Z",
        updated_at="2026-09-18T10:00:00Z",
        author="Architect",
    )
    assert prov.source == ProvenanceSource.DEVELOPER
    assert prov.author == "Architect"


def test_decision_entity_adr():
    prov = Provenance(
        source=ProvenanceSource.DEVELOPER,
        created_at="2026-09-18T10:00:00Z",
        updated_at="2026-09-18T10:00:00Z",
    )
    decision = DecisionEntity(
        id="ADR-0001",
        title="Use SQLite WAL for Code Brain",
        status=DecisionStatus.ACCEPTED,
        context="Need local-first high performance symbol index",
        decision="Adopt SQLite with WAL pragma",
        consequences="High read concurrency, zero remote database dependency",
        code_refs=["sym://backend/app/code_brain/database.py#CodeBrainDatabase?kind=class"],
        date="2026-09-18",
        ownership=ArtifactOwnership.HUMAN_AUTHORED,
        evidence=EvidenceState.CONFIRMED,
        provenance=prov,
    )
    assert decision.id == "ADR-0001"
    assert decision.status == DecisionStatus.ACCEPTED
    assert decision.ownership == ArtifactOwnership.HUMAN_AUTHORED


def test_discrepancy_entity():
    disc = DiscrepancyEntity(
        id="disc:ADR-0001:CodeBrainDatabase",
        entity_id="ADR-0001",
        entity_type="decision",
        human_statement="References CodeBrainDatabase",
        conflicting_evidence="Symbol moved or deleted",
        detected_at="2026-09-18T10:00:00Z",
        status=DiscrepancyStatus.OPEN,
    )
    assert disc.status == DiscrepancyStatus.OPEN
    assert disc.entity_id == "ADR-0001"
