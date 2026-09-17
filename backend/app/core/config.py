"""Configuration management for Continuum using Pydantic Settings.

Supports environment overrides, directory path resolution, and safe serialization
to ensure secrets and sensitive internal variables are never leaked.
"""
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ContinuumSettings(BaseSettings):
    """Central configuration for Continuum Phase 1 Foundation."""

    model_config = SettingsConfigDict(
        env_prefix="CONTINUUM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Continuum", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application semantic version")
    environment: str = Field(default="development", description="Runtime environment")
    log_level: str = Field(default="INFO", description="Logging level")
    command_timeout: int = Field(default=30, ge=1, le=300, description="Default command execution timeout in seconds")
    git_timeout: int = Field(default=15, ge=1, le=120, description="Git operation timeout in seconds")

    # Continuum persistence root (~/.continuum)
    home_dir: Path = Field(
        default_factory=lambda: Path.home() / ".continuum",
        alias="CONTINUUM_HOME",
        description="Root directory for global Continuum data",
    )

    # Scanner configuration (Phase 2)
    max_file_size_bytes: int = Field(
        default=2 * 1024 * 1024, ge=1024, description="Max file size in bytes to scan (default 2MB)"
    )
    scanner_ignore_patterns: list[str] = Field(
        default_factory=lambda: [
            ".git",
            "node_modules",
            "dist",
            "build",
            "coverage",
            ".venv",
            "__pycache__",
            ".continuum",
            ".next",
            "out",
            ".pytest_cache",
            ".mypy_cache",
        ],
        description="Directories and patterns to ignore during file discovery",
    )
    scanner_batch_size: int = Field(
        default=500, ge=1, le=10000, description="Batch size for database writes"
    )

    # Optional internal token/secret for API or internal communication
    api_secret: Optional[SecretStr] = Field(default=None, description="Optional internal authorization token")

    @property
    def continuum_home(self) -> Path:
        """Resolved canonical Continuum home directory."""
        return self.home_dir.expanduser().resolve()

    @property
    def projects_dir(self) -> Path:
        """Path to local project data cache (~/.continuum/projects/)."""
        return self.continuum_home / "projects"

    @property
    def technology_dir(self) -> Path:
        """Path to global technology brain cache (~/.continuum/technology/)."""
        return self.continuum_home / "technology"

    def ensure_directories(self) -> None:
        """Ensure necessary Continuum home directories exist."""
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.technology_dir.mkdir(parents=True, exist_ok=True)

    def to_safe_dict(self) -> Dict[str, Any]:
        """Produce a safe, secret-free representation suitable for API exposure and logs."""
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "environment": self.environment,
            "log_level": self.log_level,
            "command_timeout": self.command_timeout,
            "git_timeout": self.git_timeout,
            "continuum_home": self.continuum_home.as_posix(),
            "projects_dir": self.projects_dir.as_posix(),
            "technology_dir": self.technology_dir.as_posix(),
            "max_file_size_bytes": self.max_file_size_bytes,
            "scanner_ignore_patterns": self.scanner_ignore_patterns,
            "scanner_batch_size": self.scanner_batch_size,
            "has_api_secret": self.api_secret is not None,
        }


# Global cached settings instance
_settings_instance: Optional[ContinuumSettings] = None


def get_settings() -> ContinuumSettings:
    """Get or initialize the global settings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = ContinuumSettings()
    return _settings_instance


def reset_settings(new_settings: Optional[ContinuumSettings] = None) -> ContinuumSettings:
    """Reset global settings, useful in test fixtures."""
    global _settings_instance
    _settings_instance = new_settings
    return get_settings()
