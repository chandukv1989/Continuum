"""Integration tests for WorkspaceContext."""
from pathlib import Path
import pytest

from backend.app.core.config import ContinuumSettings
from backend.app.core.exceptions import (
    InvalidWorkspaceException,
    WorkspaceBoundaryException,
)
from backend.app.workspace.context import WorkspaceContext


def test_workspace_context_creation_git(
    temp_git_repo_with_remote: Path,
    test_settings: ContinuumSettings,
):
    """Test full context initialization on a Git repository."""
    ctx = WorkspaceContext.create(temp_git_repo_with_remote, config=test_settings)

    assert ctx.canonical_root == temp_git_repo_with_remote.resolve()
    assert ctx.identity.tier == 1
    assert ctx.identity.tier_name == "REMOTE_ORIGIN"
    assert ctx.git_state.is_git_repo is True
    assert ctx.git_state.branch == "main"
    assert ctx.project_brain_dir == temp_git_repo_with_remote / ".continuum"
    assert ctx.code_brain_db_path == (
        test_settings.projects_dir / ctx.identity.project_id / "symbols.db"
    )

    summary = ctx.to_summary_dict()
    assert "identity" in summary
    assert "git" in summary
    assert summary["canonical_root"] == temp_git_repo_with_remote.as_posix()


def test_workspace_context_creation_non_git(
    temp_workspace: Path,
    test_settings: ContinuumSettings,
):
    """Test full context initialization on a non-Git workspace directory."""
    ctx = WorkspaceContext.create(temp_workspace, config=test_settings)

    assert ctx.canonical_root == temp_workspace.resolve()
    assert ctx.identity.tier == 3
    assert ctx.identity.tier_name == "CANONICAL_PATH"
    assert ctx.git_state.is_git_repo is False


def test_workspace_context_nonexistent_directory(test_settings: ContinuumSettings, tmp_path: Path):
    """Test initializing context with non-existent directory raises InvalidWorkspaceException."""
    non_existent = tmp_path / "does_not_exist_xyz"

    with pytest.raises(InvalidWorkspaceException) as exc_info:
        WorkspaceContext.create(non_existent, config=test_settings)

    assert "does not exist" in exc_info.value.message


def test_workspace_context_file_not_directory(
    temp_workspace: Path,
    test_settings: ContinuumSettings,
):
    """Test initializing context with a file instead of directory raises InvalidWorkspaceException."""
    dummy_file = temp_workspace / "file.txt"
    dummy_file.write_text("hello", encoding="utf-8")

    with pytest.raises(InvalidWorkspaceException) as exc_info:
        WorkspaceContext.create(dummy_file, config=test_settings)

    assert "not a directory" in exc_info.value.message


def test_workspace_file_resolution_and_boundary(temp_workspace: Path, test_settings: ContinuumSettings):
    """Test boundary validation via WorkspaceContext.resolve_file."""
    ctx = WorkspaceContext.create(temp_workspace, config=test_settings)

    src_file = temp_workspace / "main.py"
    src_file.write_text("x = 1", encoding="utf-8")

    # Valid relative file
    resolved = ctx.resolve_file("main.py")
    assert resolved == src_file.resolve()

    # Traversal outside workspace boundary
    with pytest.raises(WorkspaceBoundaryException):
        ctx.resolve_file("../outside.txt")
