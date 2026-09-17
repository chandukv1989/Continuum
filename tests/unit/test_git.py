"""Unit tests for read-only GitAdapter."""
from pathlib import Path
import pytest

from backend.app.core.exceptions import GitCommandException
from backend.app.workspace.git import GitAdapter


def test_git_detection_on_git_repo(temp_git_repo_with_remote: Path):
    """Verify git repo detection and attributes."""
    adapter = GitAdapter(temp_git_repo_with_remote)

    assert adapter.check_is_git_repo() is True
    assert adapter.get_repository_root() == temp_git_repo_with_remote.resolve()
    assert adapter.get_remote_origin() == "https://github.com/continuum-engine/test-repo.git"
    assert adapter.get_root_commit() is not None
    assert adapter.get_head_commit() is not None


def test_git_detection_on_non_git_repo(temp_workspace: Path):
    """Verify non-git directory returns clean non-repo status."""
    adapter = GitAdapter(temp_workspace)

    assert adapter.check_is_git_repo() is False
    assert adapter.get_repository_root() is None
    assert adapter.get_remote_origin() is None
    assert adapter.get_root_commit() is None

    status = adapter.get_status()
    assert status.is_git_repo is False
    assert status.status_state == "non_repo"


def test_git_status_clean_repo(temp_git_repo_no_remote: Path):
    """Verify clean repo status parsing via porcelain v2."""
    adapter = GitAdapter(temp_git_repo_no_remote)
    status = adapter.get_status()

    assert status.is_git_repo is True
    assert status.status_state == "clean"
    assert status.uncommitted_changes is False
    assert len(status.modified_files) == 0
    assert len(status.staged_files) == 0
    assert len(status.untracked_files) == 0
    assert status.branch == "main"
    assert status.current_commit is not None


def test_git_status_dirty_repo(temp_git_repo_dirty: Path):
    """Verify dirty repo with staged, modified, and untracked files."""
    adapter = GitAdapter(temp_git_repo_dirty)
    status = adapter.get_status()

    assert status.is_git_repo is True
    assert status.uncommitted_changes is True
    assert status.status_state == "dirty"
    assert "staged.txt" in status.staged_files
    assert "hello.py" in status.modified_files
    assert "untracked.py" in status.untracked_files


def test_git_adapter_forbids_mutating_commands(temp_git_repo_no_remote: Path):
    """Verify GitAdapter strictly refuses mutating subcommands like add, commit, push."""
    adapter = GitAdapter(temp_git_repo_no_remote)

    for forbidden in ["add", "commit", "push", "checkout", "reset", "rebase"]:
        with pytest.raises(GitCommandException) as exc_info:
            adapter._execute_read_only_git([forbidden, "."])
        assert "Prohibited git command" in exc_info.value.message
