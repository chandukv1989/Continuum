"""Integration tests for Phase 3 Project Brain and Technology Brain API routes."""
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.project_brain.contracts import (
    ArtifactOwnership,
    DecisionEntity,
    DecisionStatus,
    EvidenceState,
    FeatureEntity,
    Provenance,
    ProvenanceSource,
)
from backend.app.project_brain.repository import ProjectBrainRepository
from backend.app.workspace.context import WorkspaceContext

client = TestClient(app)


def test_tech_brain_api():
    # List technologies
    resp = client.get("/api/v1/tech-brain")
    assert resp.status_code == 200
    techs = resp.json()
    assert len(techs) >= 7

    # Filter by category
    resp_lang = client.get("/api/v1/tech-brain?category=LANGUAGE")
    assert resp_lang.status_code == 200
    langs = resp_lang.json()
    assert all(item["category"] == "LANGUAGE" for item in langs)

    # Get single technology
    resp_fastapi = client.get("/api/v1/tech-brain/tech:fastapi")
    assert resp_fastapi.status_code == 200
    fastapi = resp_fastapi.json()
    assert fastapi["name"] == "FastAPI"


def test_project_brain_endpoints_and_reconcile(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()

    # Create dummy source file
    src_file = workspace / "server.py"
    src_file.write_text("class AppServer:\n    pass\n", encoding="utf-8")

    # Run scan to populate Code Brain
    scan_resp = client.post(f"/api/v1/scanner/scan?path={workspace.as_posix()}&persist=true")
    assert scan_resp.status_code == 200

    # Populate Project Brain artifacts
    pb_dir = workspace / ".continuum"
    pb_repo = ProjectBrainRepository(pb_dir)

    prov = Provenance(
        source=ProvenanceSource.DEVELOPER,
        created_at="2026-09-18T10:00:00Z",
        updated_at="2026-09-18T10:00:00Z",
    )
    pb_repo.save_feature(
        FeatureEntity(
            id="feat:server",
            name="App Server",
            description="Runs core app server",
            code_refs=["sym://server.py#AppServer?kind=class"],
            ownership=ArtifactOwnership.HUMAN_AUTHORED,
            evidence=EvidenceState.CONFIRMED,
            provenance=prov,
        )
    )
    pb_repo.save_decision(
        DecisionEntity(
            id="ADR-0001",
            title="Single Server Model",
            status=DecisionStatus.ACCEPTED,
            context="Simple concurrency",
            decision="Use AppServer",
            consequences="Fast boot",
            code_refs=["sym://server.py#AppServer?kind=class"],
            date="2026-09-18",
            ownership=ArtifactOwnership.HUMAN_AUTHORED,
            evidence=EvidenceState.CONFIRMED,
            provenance=prov,
        )
    )

    # Test GET endpoints
    resp_feat = client.get(f"/api/v1/project-brain/features?path={workspace.as_posix()}")
    assert resp_feat.status_code == 200
    features = resp_feat.json()
    assert len(features) == 1
    assert features[0]["id"] == "feat:server"

    resp_dec = client.get(f"/api/v1/project-brain/decisions?path={workspace.as_posix()}")
    assert resp_dec.status_code == 200
    decisions = resp_dec.json()
    assert len(decisions) == 1
    assert decisions[0]["id"] == "ADR-0001"

    # Test reconcile endpoint
    resp_rec = client.post(f"/api/v1/project-brain/reconcile?path={workspace.as_posix()}")
    assert resp_rec.status_code == 200
    sync_data = resp_rec.json()
    assert sync_data["entities_inspected"] == 2
    assert sync_data["references_resolved"] == 2
    assert sync_data["human_artifacts_preserved"] == 2
