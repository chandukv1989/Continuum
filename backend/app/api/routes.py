"""FastAPI route handlers for Continuum Phase 1."""
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, Query

from backend.app.api.schemas import (
    CodeBrainStatsResponse,
    ConfigResponse,
    GitStatusSchema,
    HealthResponse,
    ProjectIdentitySchema,
    RelationshipSchema,
    ScanMetricsSchema,
    ScanResponse,
    SymbolSchema,
    WorkspaceResponse,
)
from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.core.config import ContinuumSettings, get_settings
from backend.app.scanner.repository import RepositoryScanner
from backend.app.workspace.context import WorkspaceContext

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check(
    settings: ContinuumSettings = Depends(get_settings),
) -> HealthResponse:
    """Return health status and app metadata."""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        app_version=settings.app_version,
        environment=settings.environment,
    )


@router.get("/api/v1/config", response_model=ConfigResponse, tags=["Configuration"])
async def get_config(
    settings: ContinuumSettings = Depends(get_settings),
) -> ConfigResponse:
    """Retrieve safe application configuration."""
    safe = settings.to_safe_dict()
    return ConfigResponse(**safe)


@router.get("/api/v1/workspace", response_model=WorkspaceResponse, tags=["Workspace"])
async def get_workspace(
    path: Optional[str] = Query(
        default=None,
        description="Path to workspace directory. Defaults to current directory.",
    ),
    settings: ContinuumSettings = Depends(get_settings),
) -> WorkspaceResponse:
    """Inspect and resolve workspace context, identity, and Git state."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)

    return WorkspaceResponse(
        canonical_root=context.canonical_root.as_posix(),
        identity=ProjectIdentitySchema(
            project_id=context.identity.project_id,
            tier=context.identity.tier,
            tier_name=context.identity.tier_name,
            raw_identifier=context.identity.raw_identifier,
            canonical_path=context.identity.canonical_path,
        ),
        git=GitStatusSchema(
            is_git_repo=context.git_state.is_git_repo,
            repository_root=context.git_state.repository_root.as_posix()
            if context.git_state.repository_root
            else None,
            branch=context.git_state.branch,
            current_commit=context.git_state.current_commit,
            remote_origin=context.git_state.remote_origin,
            modified_files=context.git_state.modified_files,
            staged_files=context.git_state.staged_files,
            untracked_files=context.git_state.untracked_files,
            uncommitted_changes=context.git_state.uncommitted_changes,
            status_state=context.git_state.status_state,
        ),
        project_brain_dir=context.project_brain_dir.as_posix(),
        code_brain_db_path=context.code_brain_db_path.as_posix(),
    )


@router.post("/api/v1/scanner/scan", response_model=ScanResponse, tags=["Scanner"])
async def trigger_scan(
    path: Optional[str] = Query(
        default=None,
        description="Path to workspace directory. Defaults to current directory.",
    ),
    persist: bool = Query(
        default=True,
        description="Whether to persist extracted facts into Code Brain symbols.db",
    ),
    settings: ContinuumSettings = Depends(get_settings),
) -> ScanResponse:
    """Run deterministic repository scan and persist structural facts into Code Brain."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    scanner = RepositoryScanner(context=context)
    result = scanner.scan(persist=persist)

    return ScanResponse(
        project_id=result.project_id,
        canonical_root=result.canonical_root,
        symbols_db_path=result.symbols_db_path,
        metrics=ScanMetricsSchema(
            files_discovered=result.metrics.files_discovered,
            files_filtered=result.metrics.files_filtered,
            files_parsed=result.metrics.files_parsed,
            parse_failures=result.metrics.parse_failures,
            symbols_extracted=result.metrics.symbols_extracted,
            relationships_extracted=result.metrics.relationships_extracted,
            scan_duration_seconds=result.metrics.scan_duration_seconds,
            persistence_duration_seconds=result.metrics.persistence_duration_seconds,
        ),
    )


@router.get("/api/v1/code-brain/stats", response_model=CodeBrainStatsResponse, tags=["Code Brain"])
async def get_code_brain_stats(
    path: Optional[str] = Query(
        default=None,
        description="Path to workspace directory. Defaults to current directory.",
    ),
    settings: ContinuumSettings = Depends(get_settings),
) -> CodeBrainStatsResponse:
    """Retrieve statistical summary of Code Brain entities."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    repo = CodeBrainRepository(context.code_brain_db_path)
    stats = repo.get_stats()
    return CodeBrainStatsResponse(**stats.to_dict())


@router.get("/api/v1/code-brain/symbols", response_model=List[SymbolSchema], tags=["Code Brain"])
async def get_symbols(
    path: Optional[str] = Query(default=None, description="Workspace path"),
    file_path: Optional[str] = Query(default=None, description="Filter by relative file path"),
    kind: Optional[str] = Query(default=None, description="Filter by symbol kind"),
    settings: ContinuumSettings = Depends(get_settings),
) -> List[SymbolSchema]:
    """Retrieve symbols from Code Brain."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    repo = CodeBrainRepository(context.code_brain_db_path)
    symbols = repo.get_symbols(file_path=file_path, kind=kind)
    return [SymbolSchema(**s) for s in symbols]


@router.get(
    "/api/v1/code-brain/relationships",
    response_model=List[RelationshipSchema],
    tags=["Code Brain"],
)
async def get_relationships(
    path: Optional[str] = Query(default=None, description="Workspace path"),
    source_id: Optional[str] = Query(default=None, description="Filter by source ID"),
    relationship_type: Optional[str] = Query(default=None, description="Filter by relationship type"),
    file_path: Optional[str] = Query(default=None, description="Filter by file path"),
    settings: ContinuumSettings = Depends(get_settings),
) -> List[RelationshipSchema]:
    """Retrieve relationships from Code Brain."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    repo = CodeBrainRepository(context.code_brain_db_path)
    relationships = repo.get_relationships(
        source_id=source_id,
        relationship_type=relationship_type,
        file_path=file_path,
    )
    return [RelationshipSchema(**r) for r in relationships]

