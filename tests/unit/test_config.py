"""Unit tests for configuration management."""
from pathlib import Path
from pydantic import SecretStr

from backend.app.core.config import ContinuumSettings


def test_config_defaults():
    """Test default configuration parameters."""
    settings = ContinuumSettings()
    assert settings.app_name == "Continuum"
    assert settings.app_version == "0.1.0"
    assert settings.environment in ("development", "test", "production")
    assert settings.command_timeout == 30
    assert settings.git_timeout == 15
    assert settings.continuum_home == (Path.home() / ".continuum").resolve()
    assert settings.projects_dir == (Path.home() / ".continuum" / "projects").resolve()
    assert settings.technology_dir == (Path.home() / ".continuum" / "technology").resolve()


def test_continuum_home_override(tmp_path: Path):
    """Test custom CONTINUUM_HOME override."""
    custom_home = tmp_path / "custom_continuum"
    settings = ContinuumSettings(CONTINUUM_HOME=custom_home)

    assert settings.continuum_home == custom_home.resolve()
    assert settings.projects_dir == (custom_home / "projects").resolve()
    assert settings.technology_dir == (custom_home / "technology").resolve()

    settings.ensure_directories()
    assert settings.projects_dir.exists()
    assert settings.technology_dir.exists()


def test_secret_str_masking():
    """Verify SecretStr never leaks raw secret in string representations."""
    raw_secret = "super_secret_token_12345"
    settings = ContinuumSettings(api_secret=SecretStr(raw_secret))

    # str() and repr() must not show the secret
    assert raw_secret not in str(settings.api_secret)
    assert raw_secret not in repr(settings.api_secret)
    assert "**********" in str(settings.api_secret)

    # get_secret_value() recovers it safely
    assert settings.api_secret.get_secret_value() == raw_secret


def test_safe_dict_serialization():
    """Verify to_safe_dict() omits sensitive fields and presents safe metadata."""
    settings = ContinuumSettings(api_secret=SecretStr("super_secret_token_12345"))
    safe_data = settings.to_safe_dict()

    assert "super_secret_token_12345" not in str(safe_data)
    assert "api_secret" not in safe_data
    assert safe_data["has_api_secret"] is True
    assert safe_data["app_name"] == "Continuum"
    assert "continuum_home" in safe_data
    assert "projects_dir" in safe_data
    assert "technology_dir" in safe_data
