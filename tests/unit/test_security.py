"""Unit tests for SecurityManager."""
import os
from pathlib import Path
import pytest

from backend.app.core.exceptions import (
    ProcessTimeoutException,
    SecurityException,
    WorkspaceBoundaryException,
)
from backend.app.core.security import SecurityManager


def test_path_normalization(tmp_path: Path):
    """Test canonical path resolution and POSIX formatting."""
    nested = tmp_path / "a" / "b" / ".." / "c"
    (tmp_path / "a" / "c").mkdir(parents=True)

    canonical = SecurityManager.canonical_path(nested)
    assert canonical == (tmp_path / "a" / "c").resolve()

    posix_str = SecurityManager.canonical_posix_path(nested)
    assert posix_str == canonical.as_posix()


def test_workspace_boundary_valid(tmp_path: Path):
    """Test accessing files within workspace boundary succeeds."""
    sec = SecurityManager()
    file_inside = tmp_path / "src" / "index.ts"
    file_inside.parent.mkdir(parents=True)
    file_inside.write_text("content", encoding="utf-8")

    res = sec.validate_workspace_boundary(tmp_path, file_inside)
    assert res == file_inside.resolve()


def test_workspace_boundary_violation(tmp_path: Path):
    """Test path traversal outside workspace triggers WorkspaceBoundaryException."""
    sec = SecurityManager()
    outside = tmp_path.parent / "outside_file.txt"

    with pytest.raises(WorkspaceBoundaryException) as exc_info:
        sec.validate_workspace_boundary(tmp_path, outside)

    assert "escapes designated workspace boundary" in exc_info.value.message


def test_workspace_boundary_traversal_string(tmp_path: Path):
    """Test ../../ traversal style string triggers WorkspaceBoundaryException."""
    sec = SecurityManager()
    traversal_path = str(tmp_path) + "/../../etc/passwd"

    with pytest.raises(WorkspaceBoundaryException):
        sec.validate_workspace_boundary(tmp_path, traversal_path)


def test_executable_allowlist_rejection(tmp_path: Path):
    """Test running an unapproved binary triggers SecurityException."""
    sec = SecurityManager(allowed_executables={"git", "python3"})

    with pytest.raises(SecurityException) as exc_info:
        sec.run_safe_subprocess(
            args=["sh", "-c", "echo hello"],
            cwd=tmp_path,
        )

    assert "not in the allowed executable list" in exc_info.value.message


def test_subprocess_timeout(tmp_path: Path):
    """Test subprocess execution exceeding timeout raises ProcessTimeoutException."""
    sec = SecurityManager(allowed_executables={"python3"})

    with pytest.raises(ProcessTimeoutException) as exc_info:
        sec.run_safe_subprocess(
            args=["python3", "-c", "import time; time.sleep(3)"],
            cwd=tmp_path,
            timeout=0.2,
        )

    assert exc_info.value.code == "PROCESS_TIMEOUT"


def test_environment_filtering():
    """Test sensitive variables are removed from child environment."""
    sec = SecurityManager()
    custom_env = {
        "CONTINUUM_ENV": "production",
        "API_KEY": "secret_api_key_123",
        "USER_PASSWORD": "my_password_xyz",
        "AUTH_TOKEN": "token_abc_def",
        "DATABASE_CREDENTIAL": "db_pass_123",
    }

    filtered = sec.filter_environment(custom_env)

    assert filtered["CONTINUUM_ENV"] == "production"
    assert "API_KEY" not in filtered
    assert "USER_PASSWORD" not in filtered
    assert "AUTH_TOKEN" not in filtered
    assert "DATABASE_CREDENTIAL" not in filtered
