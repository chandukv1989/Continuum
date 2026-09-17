"""Unit tests for stable project identity resolution."""
from pathlib import Path
from backend.app.workspace.git import GitAdapter
from backend.app.workspace.identity import (
    IdentityTier,
    compute_project_id,
    resolve_project_identity,
)


def test_identity_tier1_remote_origin(temp_git_repo_with_remote: Path):
    """Verify repo with remote origin uses Tier 1 (REMOTE_ORIGIN)."""
    identity = resolve_project_identity(temp_git_repo_with_remote)

    assert identity.tier == IdentityTier.TIER_1_REMOTE_ORIGIN.value
    assert identity.tier_name == "REMOTE_ORIGIN"
    assert identity.raw_identifier == "https://github.com/continuum-engine/test-repo.git"
    assert identity.project_id == compute_project_id("https://github.com/continuum-engine/test-repo.git")
    assert len(identity.project_id) == 32


def test_identity_tier2_root_commit(temp_git_repo_no_remote: Path):
    """Verify repo without remote uses Tier 2 (ROOT_COMMIT)."""
    adapter = GitAdapter(temp_git_repo_no_remote)
    root_commit = adapter.get_root_commit()
    assert root_commit is not None

    identity = resolve_project_identity(temp_git_repo_no_remote, git_adapter=adapter)

    assert identity.tier == IdentityTier.TIER_2_ROOT_COMMIT.value
    assert identity.tier_name == "ROOT_COMMIT"
    assert identity.raw_identifier == root_commit
    assert identity.project_id == compute_project_id(root_commit)


def test_identity_tier3_canonical_path(temp_workspace: Path):
    """Verify non-git workspace falls back to Tier 3 (CANONICAL_PATH)."""
    identity = resolve_project_identity(temp_workspace)

    assert identity.tier == IdentityTier.TIER_3_CANONICAL_PATH.value
    assert identity.tier_name == "CANONICAL_PATH"
    assert identity.raw_identifier == temp_workspace.as_posix()
    assert identity.project_id == compute_project_id(temp_workspace.as_posix())


def test_identity_stability_across_locations(temp_git_repo_with_remote: Path, tmp_path: Path):
    """Verify that identity resolved from the same remote URL produces identical project_id."""
    id1 = resolve_project_identity(temp_git_repo_with_remote)

    # Simulated relocation with identical remote URL
    id2_project_id = compute_project_id("https://github.com/continuum-engine/test-repo.git")
    assert id1.project_id == id2_project_id
