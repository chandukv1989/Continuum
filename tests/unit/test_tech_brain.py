"""Unit tests for Technology Brain contracts and repository."""
import pytest
from backend.app.core.exceptions import TechnologyBrainException
from backend.app.tech_brain.contracts import TechnologyCategory, TechnologyConcept
from backend.app.tech_brain.repository import TechnologyBrainRepository


def test_technology_brain_default_seeds(tmp_path):
    repo = TechnologyBrainRepository(tmp_path / "technology")
    techs = repo.list_technologies()
    assert len(techs) >= 7

    fastapi = repo.get_technology("tech:fastapi")
    assert fastapi is not None
    assert fastapi.name == "FastAPI"
    assert fastapi.category == TechnologyCategory.FRAMEWORK
    assert "https://fastapi.tiangolo.com/" in (fastapi.official_docs or "")


def test_technology_brain_filtering(tmp_path):
    repo = TechnologyBrainRepository(tmp_path / "technology")
    frameworks = repo.list_technologies(category=TechnologyCategory.FRAMEWORK)
    assert any(t.id == "tech:fastapi" for t in frameworks)
    assert all(t.category == TechnologyCategory.FRAMEWORK for t in frameworks)

    languages = repo.list_technologies(category=TechnologyCategory.LANGUAGE)
    assert any(t.id == "tech:python" for t in languages)
    assert any(t.id == "tech:typescript" for t in languages)


def test_technology_brain_project_independence_enforcement(tmp_path):
    repo = TechnologyBrainRepository(tmp_path / "technology")

    # Clean technology - succeeds
    clean_tech = TechnologyConcept(
        id="tech:docker",
        name="Docker",
        category=TechnologyCategory.TOOL,
        description="OS-level virtualization delivering software in packages called containers.",
        best_practices=["Use multi-stage builds to minimize image sizes"],
        tags=["containers", "devops"],
    )
    repo.save_technology(clean_tech)
    assert repo.get_technology("tech:docker") is not None

    # Polluted technology with project path - must be rejected
    polluted_tech = TechnologyConcept(
        id="tech:custom-runner",
        name="Custom Runner",
        category=TechnologyCategory.TOOL,
        description="Runs scripts inside /home/developer/continuum/runner.sh",
        best_practices=[],
        tags=["runner"],
    )
    with pytest.raises(TechnologyBrainException, match="Violates project independence"):
        repo.save_technology(polluted_tech)
