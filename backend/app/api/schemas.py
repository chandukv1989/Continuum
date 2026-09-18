"""Pydantic schemas for Continuum REST API."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """System health check response."""

    status: str = Field(default="ok", description="Service status")
    app_name: str = Field(description="Application name")
    app_version: str = Field(description="Semantic version")
    environment: str = Field(description="Active runtime environment")


class ConfigResponse(BaseModel):
    """Safe configuration response without sensitive tokens or credentials."""

    app_name: str
    app_version: str
    environment: str
    log_level: str
    command_timeout: int
    git_timeout: int
    continuum_home: str
    projects_dir: str
    technology_dir: str
    has_api_secret: bool
    max_file_size_bytes: int = 2 * 1024 * 1024
    scanner_ignore_patterns: List[str] = Field(default_factory=list)
    scanner_batch_size: int = 500


class ScanMetricsSchema(BaseModel):
    """Metrics recorded during a repository scan."""

    files_discovered: int
    files_filtered: int
    files_parsed: int
    parse_failures: int
    symbols_extracted: int
    relationships_extracted: int
    scan_duration_seconds: float
    persistence_duration_seconds: float


class ScanResponse(BaseModel):
    """Summary response for scanner execution."""

    project_id: str
    canonical_root: str
    symbols_db_path: str
    metrics: ScanMetricsSchema


class FileChangeSchema(BaseModel):
    """Schema representing an individual file change in a ChangeSet."""

    path: str
    change_type: str
    old_path: Optional[str] = None
    old_content_hash: Optional[str] = None
    new_content_hash: Optional[str] = None
    size_bytes: Optional[int] = None
    mtime: Optional[float] = None


class ChangeSetSchema(BaseModel):
    """Schema representing a batch of file changes."""

    changes: List[FileChangeSchema] = Field(default_factory=list)
    detected_at: Optional[str] = None
    detection_source: str
    is_empty: bool


class IncrementalScanResponse(BaseModel):
    """Response returned by incremental scanner execution."""

    project_id: str
    canonical_root: str
    symbols_db_path: str
    change_set: ChangeSetSchema
    metrics: ScanMetricsSchema
    reconciliation_report: Optional[Dict[str, Any]] = None



class CodeBrainStatsResponse(BaseModel):
    """Entity count stats for Code Brain."""

    files_count: int
    symbols_count: int
    relationships_count: int
    schema_version: str


class SymbolSchema(BaseModel):
    """Schema for individual symbol records."""

    id: str
    file_path: str
    name: str
    qualified_name: str
    kind: str
    language: str
    parent_id: Optional[str] = None
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    is_exported: int
    docstring: Optional[str] = None


class RelationshipSchema(BaseModel):
    """Schema for structural relationship records."""

    id: str
    source_id: str
    target_name: str
    target_id: Optional[str] = None
    relationship_type: str
    evidence_type: str
    file_path: str
    line_number: int


class ProjectIdentitySchema(BaseModel):
    """Stable project identity schema."""

    project_id: str
    tier: int
    tier_name: str
    raw_identifier: str
    canonical_path: str


class GitStatusSchema(BaseModel):
    """Read-only Git repository status schema."""

    is_git_repo: bool
    repository_root: Optional[str] = None
    branch: Optional[str] = None
    current_commit: Optional[str] = None
    remote_origin: Optional[str] = None
    modified_files: List[str] = Field(default_factory=list)
    staged_files: List[str] = Field(default_factory=list)
    untracked_files: List[str] = Field(default_factory=list)
    uncommitted_changes: bool = False
    status_state: str = "non_repo"


class WorkspaceResponse(BaseModel):
    """Workspace context query response."""

    canonical_root: str
    identity: ProjectIdentitySchema
    git: GitStatusSchema
    project_brain_dir: str
    code_brain_db_path: str


class ErrorResponse(BaseModel):
    """Structured safe error response."""

    error: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
