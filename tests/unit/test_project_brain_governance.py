"""Unit tests for Project Brain artifact governance and immutability rules."""
import pytest
from backend.app.core.exceptions import GovernanceViolationException
from backend.app.project_brain.contracts import (
    ArchitectureEntity,
    ArtifactOwnership,
    DecisionEntity,
    DecisionStatus,
    EvidenceState,
    FeatureEntity,
    ProjectMetadata,
    Provenance,
    ProvenanceSource,
)
from backend.app.project_brain.repository import ProjectBrainRepository


@pytest.fixture
def repo(tmp_path):
    return ProjectBrainRepository(tmp_path / ".continuum")


def test_human_authored_decision_cannot_be_overwritten_by_automation(repo):
    prov = Provenance(
        source=ProvenanceSource.DEVELOPER,
        created_at="2026-09-18T10:00:00Z",
        updated_at="2026-09-18T10:00:00Z",
        author="Lead Architect",
    )
    adr = DecisionEntity(
        id="ADR-0001",
        title="Three-Brain Architecture",
        status=DecisionStatus.ACCEPTED,
        context="Complex project knowledge requires separation of concerns",
        decision="Code Brain, Project Brain, and Technology Brain",
        consequences="Clean boundaries and git-trackable artifacts",
        date="2026-09-18",
        ownership=ArtifactOwnership.HUMAN_AUTHORED,
        evidence=EvidenceState.CONFIRMED,
        provenance=prov,
    )
    # Save as human
    repo.save_decision(adr, automated=False)

    # Verify saved
    loaded = repo.get_decision("ADR-0001")
    assert loaded is not None
    assert loaded.ownership == ArtifactOwnership.HUMAN_AUTHORED

    # Attempt automated overwrite - MUST FAIL with GovernanceViolationException
    with pytest.raises(GovernanceViolationException, match="Automated overwrite rejected"):
        mutated = adr.model_copy(update={"decision": "Automated modified decision"})
        repo.save_decision(mutated, automated=True)

    # Human overwrite IS allowed
    human_update = adr.model_copy(update={"decision": "Updated by human architect"})
    repo.save_decision(human_update, automated=False)
    reloaded = repo.get_decision("ADR-0001")
    assert "Updated by human architect" in reloaded.decision


def test_derived_artifacts_allow_automated_overwrite(repo):
    prov = Provenance(
        source=ProvenanceSource.SOURCE_CODE,
        created_at="2026-09-18T10:00:00Z",
        updated_at="2026-09-18T10:00:00Z",
    )
    meta = ProjectMetadata(
        project_id="proj_test_123",
        name="Continuum Test",
        repository_root="/tmp/test",
        created_at="2026-09-18T10:00:00Z",
        updated_at="2026-09-18T10:00:00Z",
        ownership=ArtifactOwnership.DERIVED,
        evidence=EvidenceState.CONFIRMED,
        provenance=prov,
    )
    repo.save_metadata(meta, automated=True)

    updated_meta = meta.model_copy(update={"description": "Updated automatically"})
    repo.save_metadata(updated_meta, automated=True)

    loaded = repo.get_metadata()
    assert loaded is not None
    assert "Updated automatically" in loaded.description
