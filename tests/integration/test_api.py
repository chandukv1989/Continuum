"""Integration tests for FastAPI endpoints."""
from pathlib import Path
from starlette.testclient import TestClient


def test_health_endpoint(test_client: TestClient):
    """Test GET /health returns 200 and expected metadata."""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "app_name" in data
    assert "app_version" in data
    assert data["environment"] == "test"


def test_config_endpoint(test_client: TestClient):
    """Test GET /api/v1/config returns safe configuration without secrets."""
    response = test_client.get("/api/v1/config")
    assert response.status_code == 200
    data = response.json()
    assert "app_name" in data
    assert "continuum_home" in data
    assert "projects_dir" in data
    assert "technology_dir" in data
    assert "api_secret" not in data
    assert data["has_api_secret"] is False


def test_workspace_endpoint_valid(test_client: TestClient, temp_git_repo_with_remote: Path):
    """Test GET /api/v1/workspace with valid workspace path."""
    response = test_client.get(f"/api/v1/workspace?path={temp_git_repo_with_remote.as_posix()}")
    assert response.status_code == 200
    data = response.json()
    assert data["canonical_root"] == temp_git_repo_with_remote.as_posix()
    assert data["identity"]["tier"] == 1
    assert data["identity"]["tier_name"] == "REMOTE_ORIGIN"
    assert data["git"]["is_git_repo"] is True
    assert data["git"]["branch"] == "main"
    assert "project_brain_dir" in data
    assert "code_brain_db_path" in data


def test_workspace_endpoint_invalid_path(test_client: TestClient):
    """Test GET /api/v1/workspace with invalid path returns 400 and structured error response."""
    response = test_client.get("/api/v1/workspace?path=/nonexistent/path/xyz_12345")
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "INVALID_WORKSPACE"
    assert "message" in data
    assert "details" in data
    # Verify no raw python traceback is in response
    assert "Traceback (most recent call last)" not in str(data)
