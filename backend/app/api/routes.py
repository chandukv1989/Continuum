"""FastAPI route handlers for Continuum Phase 1."""
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, Query

from backend.app.api.schemas import (
    ChangeSetSchema,
    CodeBrainStatsResponse,
    ConfigResponse,
    FileChangeSchema,
    GitStatusSchema,
    HealthResponse,
    IncrementalScanResponse,
    ProjectIdentitySchema,
    RelationshipSchema,
    ScanMetricsSchema,
    ScanResponse,
    SymbolSchema,
    WorkspaceResponse,
)
from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.core.config import ContinuumSettings, get_settings
from backend.app.scanner.incremental import IncrementalRepositoryScanner
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


@router.post(
    "/api/v1/scanner/scan/incremental",
    response_model=IncrementalScanResponse,
    tags=["Scanner"],
)
async def scan_workspace_incremental(
    path: Optional[str] = Query(
        default=None,
        description="Path to workspace directory. Defaults to current directory.",
    ),
    reconcile: bool = Query(
        default=True,
        description="Whether to reconcile affected Project Brain references",
    ),
    use_git: bool = Query(
        default=False,
        description="Whether to use Git status for candidate change acceleration",
    ),
    settings: ContinuumSettings = Depends(get_settings),
) -> IncrementalScanResponse:
    """Run synchronous incremental scan on changed files and update Code Brain."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    scanner = IncrementalRepositoryScanner(context=context)
    result = scanner.scan_incremental(
        reconcile_project_brain=reconcile,
        use_git_acceleration=use_git,
    )

    change_schemas = [
        FileChangeSchema(
            path=c.path,
            change_type=c.change_type.value,
            old_path=c.old_path,
            old_content_hash=c.old_content_hash,
            new_content_hash=c.new_content_hash,
            size_bytes=c.size_bytes,
            mtime=c.mtime,
        )
        for c in result.change_set.changes
    ]

    return IncrementalScanResponse(
        project_id=result.project_id,
        canonical_root=result.canonical_root,
        symbols_db_path=result.symbols_db_path,
        change_set=ChangeSetSchema(
            changes=change_schemas,
            detected_at=result.change_set.detected_at,
            detection_source=result.change_set.detection_source,
            is_empty=result.change_set.is_empty,
        ),
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
        reconciliation_report=result.reconciliation_report,
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


# --------------------------------------------------------------------------
# Project Brain & Technology Brain Endpoints (Phase 3)
# --------------------------------------------------------------------------

from backend.app.project_brain.repository import ProjectBrainRepository
from backend.app.project_brain.sync import ProjectBrainReconciler
from backend.app.tech_brain.repository import TechnologyBrainRepository
from backend.app.project_brain.contracts import (
    ArchitectureEntity,
    ConceptEntity,
    ConventionEntity,
    DecisionEntity,
    DiscrepancyEntity,
    FeatureEntity,
    ProjectMetadata,
)
from backend.app.tech_brain.contracts import TechnologyCategory, TechnologyConcept


@router.get("/api/v1/project-brain/metadata", tags=["Project Brain"])
async def get_project_metadata(
    path: Optional[str] = Query(default=None, description="Workspace path"),
    settings: ContinuumSettings = Depends(get_settings),
) -> Optional[ProjectMetadata]:
    """Retrieve Project Brain metadata (.continuum/project.md)."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    repo = ProjectBrainRepository(context.project_brain_dir)
    return repo.get_metadata()


@router.get("/api/v1/project-brain/features", response_model=List[FeatureEntity], tags=["Project Brain"])
async def list_features(
    path: Optional[str] = Query(default=None, description="Workspace path"),
    settings: ContinuumSettings = Depends(get_settings),
) -> List[FeatureEntity]:
    """List all features documented in Project Brain."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    repo = ProjectBrainRepository(context.project_brain_dir)
    return repo.list_features()


@router.get("/api/v1/project-brain/decisions", response_model=List[DecisionEntity], tags=["Project Brain"])
async def list_decisions(
    path: Optional[str] = Query(default=None, description="Workspace path"),
    settings: ContinuumSettings = Depends(get_settings),
) -> List[DecisionEntity]:
    """List all architectural decisions (ADRs)."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    repo = ProjectBrainRepository(context.project_brain_dir)
    return repo.list_decisions()


@router.get("/api/v1/project-brain/concepts", response_model=List[ConceptEntity], tags=["Project Brain"])
async def list_concepts(
    path: Optional[str] = Query(default=None, description="Workspace path"),
    settings: ContinuumSettings = Depends(get_settings),
) -> List[ConceptEntity]:
    """List all domain concepts."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    repo = ProjectBrainRepository(context.project_brain_dir)
    return repo.list_concepts()


@router.get("/api/v1/project-brain/conventions", response_model=List[ConventionEntity], tags=["Project Brain"])
async def list_conventions(
    path: Optional[str] = Query(default=None, description="Workspace path"),
    settings: ContinuumSettings = Depends(get_settings),
) -> List[ConventionEntity]:
    """List all conventions."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    repo = ProjectBrainRepository(context.project_brain_dir)
    return repo.list_conventions()


@router.get("/api/v1/project-brain/architecture", response_model=List[ArchitectureEntity], tags=["Project Brain"])
async def list_architecture(
    path: Optional[str] = Query(default=None, description="Workspace path"),
    settings: ContinuumSettings = Depends(get_settings),
) -> List[ArchitectureEntity]:
    """List all architecture layers."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    repo = ProjectBrainRepository(context.project_brain_dir)
    return repo.list_architecture()


@router.get("/api/v1/project-brain/discrepancies", response_model=List[DiscrepancyEntity], tags=["Project Brain"])
async def list_discrepancies(
    path: Optional[str] = Query(default=None, description="Workspace path"),
    settings: ContinuumSettings = Depends(get_settings),
) -> List[DiscrepancyEntity]:
    """List all recorded discrepancies/conflicts."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    repo = ProjectBrainRepository(context.project_brain_dir)
    return repo.list_discrepancies()


@router.post("/api/v1/project-brain/reconcile", tags=["Project Brain"])
async def reconcile_project_brain(
    path: Optional[str] = Query(default=None, description="Workspace path"),
    settings: ContinuumSettings = Depends(get_settings),
):
    """Run non-destructive reconciliation between Code Brain and Project Brain."""
    target_path = path or "."
    context = WorkspaceContext.create(workspace_path=target_path, config=settings)
    project_repo = ProjectBrainRepository(context.project_brain_dir)
    code_repo = CodeBrainRepository(context.code_brain_db_path)
    reconciler = ProjectBrainReconciler(project_brain_repo=project_repo, code_brain_repo=code_repo)
    report = reconciler.reconcile()
    return {
        "entities_inspected": report.entities_inspected,
        "references_resolved": report.references_resolved,
        "references_unresolved": report.references_unresolved,
        "references_stale": report.references_stale,
        "discrepancies_recorded": report.discrepancies_recorded,
        "human_artifacts_preserved": report.human_artifacts_preserved,
    }


@router.get("/api/v1/tech-brain", response_model=List[TechnologyConcept], tags=["Technology Brain"])
async def list_technologies(
    category: Optional[TechnologyCategory] = Query(default=None, description="Filter by technology category"),
    settings: ContinuumSettings = Depends(get_settings),
) -> List[TechnologyConcept]:
    """List universal technology knowledge concepts from Technology Brain."""
    repo = TechnologyBrainRepository(settings.technology_dir)
    return repo.list_technologies(category=category)


@router.get("/api/v1/tech-brain/{tech_id}", response_model=Optional[TechnologyConcept], tags=["Technology Brain"])
async def get_technology(
    tech_id: str,
    settings: ContinuumSettings = Depends(get_settings),
) -> Optional[TechnologyConcept]:
    """Retrieve a specific universal technology concept by ID."""
    repo = TechnologyBrainRepository(settings.technology_dir)
    return repo.get_technology(tech_id=tech_id)

