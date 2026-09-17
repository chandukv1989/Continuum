"""Pytest fixtures for Continuum Phase 1 tests.

Provides isolated temporary environments, deterministic git repositories,
and API test clients.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Generator
import pytest
from starlette.testclient import TestClient

from backend.app.core.config import ContinuumSettings, reset_settings
from backend.app.core.security import SecurityManager
from backend.app.main import create_app


def run_cmd(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Helper to run git setup commands in temporary test directories."""
    return subprocess.run(
        args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )


@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    """Provide a basic temporary workspace directory."""
    temp_dir = tempfile.mkdtemp(prefix="continuum_test_ws_")
    path = Path(temp_dir).resolve()
    yield path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_git_repo_with_remote() -> Generator[Path, None, None]:
    """Provide a temporary Git repository with an initial commit and a remote origin URL."""
    temp_dir = tempfile.mkdtemp(prefix="continuum_git_remote_")
    repo = Path(temp_dir).resolve()

    run_cmd(["git", "init", "-b", "main"], cwd=repo)
    run_cmd(["git", "config", "user.name", "Continuum Tester"], cwd=repo)
    run_cmd(["git", "config", "user.email", "tester@continuum.local"], cwd=repo)

    # Initial commit
    readme = repo / "README.md"
    readme.write_text("# Test Repo\n", encoding="utf-8")
    run_cmd(["git", "add", "README.md"], cwd=repo)
    run_cmd(["git", "commit", "-m", "Initial commit"], cwd=repo)

    # Add remote origin
    run_cmd(
        ["git", "remote", "add", "origin", "https://github.com/continuum-engine/test-repo.git"],
        cwd=repo,
    )

    yield repo
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_git_repo_no_remote() -> Generator[Path, None, None]:
    """Provide a temporary Git repository with an initial commit but NO remote origin."""
    temp_dir = tempfile.mkdtemp(prefix="continuum_git_local_")
    repo = Path(temp_dir).resolve()

    run_cmd(["git", "init", "-b", "main"], cwd=repo)
    run_cmd(["git", "config", "user.name", "Continuum Tester"], cwd=repo)
    run_cmd(["git", "config", "user.email", "tester@continuum.local"], cwd=repo)

    # Initial commit
    file1 = repo / "hello.py"
    file1.write_text("print('hello world')\n", encoding="utf-8")
    run_cmd(["git", "add", "hello.py"], cwd=repo)
    run_cmd(["git", "commit", "-m", "Initial commit"], cwd=repo)

    yield repo
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_git_repo_dirty(temp_git_repo_no_remote: Path) -> Path:
    """Provide a Git repository containing staged, modified, and untracked files."""
    repo = temp_git_repo_no_remote

    # 1. Staged change
    staged_file = repo / "staged.txt"
    staged_file.write_text("staged content\n", encoding="utf-8")
    run_cmd(["git", "add", "staged.txt"], cwd=repo)

    # 2. Modified tracked file (unstaged)
    hello_file = repo / "hello.py"
    hello_file.write_text("print('modified world')\n", encoding="utf-8")

    # 3. Untracked file
    untracked_file = repo / "untracked.py"
    untracked_file.write_text("# untracked file\n", encoding="utf-8")

    return repo


@pytest.fixture
def test_settings(temp_workspace: Path) -> ContinuumSettings:
    """Provide isolated ContinuumSettings pointing to temporary directory."""
    continuum_home = temp_workspace / ".continuum_home"
    settings = ContinuumSettings(
        app_name="Continuum Test",
        app_version="0.1.0-test",
        environment="test",
        log_level="DEBUG",
        command_timeout=5,
        git_timeout=5,
        CONTINUUM_HOME=continuum_home,
    )
    reset_settings(settings)
    return settings


@pytest.fixture
def test_security() -> SecurityManager:
    """Provide standard SecurityManager."""
    return SecurityManager()


@pytest.fixture
def test_client(test_settings: ContinuumSettings) -> Generator[TestClient, None, None]:
    """Provide synchronous FastAPI TestClient."""
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client
