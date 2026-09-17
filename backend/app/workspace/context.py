"""WorkspaceContext: Central project boundary and environment aggregation contract.

Encapsulates all foundational project boundaries:
- Root paths (input vs canonical POSIX)
- Stable project identity (Tier 1 -> Tier 2 -> Tier 3)
- Read-only Git state
- Configuration settings
- Security boundaries
- Project Brain directory (<repo>/.continuum/)
- Local Code Brain persistence path (~/.continuum/projects/<project-id>/symbols.db)

Does NOT depend on FastAPI or presentation layers.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.app.core.config import ContinuumSettings, get_settings
from backend.app.core.exceptions import InvalidWorkspaceException
from backend.app.core.logging import get_logger
from backend.app.core.security import SecurityManager
from backend.app.workspace.git import GitAdapter, GitStatus
from backend.app.workspace.identity import ProjectIdentity, resolve_project_identity

logger = get_logger("continuum.context")


@dataclass
class WorkspaceContext:
    """Central project context contract for Continuum."""

    workspace_root: Path
    canonical_root: Path
    identity: ProjectIdentity
    git_state: GitStatus
    config: ContinuumSettings
    security: SecurityManager

    @property
    def project_brain_dir(self) -> Path:
        """Path to portable Project Brain directory (<repo>/.continuum/)."""
        return self.canonical_root / ".continuum"

    @property
    def code_brain_db_path(self) -> Path:
        """Path to local Code Brain database (~/.continuum/projects/<project-id>/symbols.db)."""
        return self.config.projects_dir / self.identity.project_id / "symbols.db"

    def ensure_code_brain_dir(self) -> Path:
        """Provision the directory for the Code Brain database idempotently (~/.continuum/projects/<project-id>/)."""
        db_dir = self.code_brain_db_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir

    def resolve_file(self, target_path: Path | str) -> Path:
        """Resolve a file path and verify it respects the workspace boundary."""
        if not Path(target_path).is_absolute():
            candidate = self.canonical_root / target_path
        else:
            candidate = Path(target_path)
        return self.security.validate_workspace_boundary(self.canonical_root, candidate)

    @classmethod
    def create(
        cls,
        workspace_path: Path | str,
        config: Optional[ContinuumSettings] = None,
        security_manager: Optional[SecurityManager] = None,
    ) -> "WorkspaceContext":
        """Construct a validated WorkspaceContext from a directory path."""
        cfg = config or get_settings()
        sec = security_manager or SecurityManager()

        try:
            canonical = sec.canonical_path(workspace_path)
        except Exception as err:
            raise InvalidWorkspaceException(
                f"Failed to resolve workspace path '{workspace_path}': {err}",
                details={"input_path": str(workspace_path)},
            )

        if not canonical.exists():
            raise InvalidWorkspaceException(
                f"Workspace path does not exist: '{canonical.as_posix()}'",
                details={"canonical_path": canonical.as_posix()},
            )

        if not canonical.is_dir():
            raise InvalidWorkspaceException(
                f"Workspace path is not a directory: '{canonical.as_posix()}'",
                details={"canonical_path": canonical.as_posix()},
            )

        logger.info(
            "Initializing workspace context",
            extra={"workspace": canonical.as_posix()},
        )

        # Initialize GitAdapter
        git_adapter = GitAdapter(
            workspace_root=canonical,
            security_manager=sec,
            timeout=cfg.git_timeout,
        )
        git_state = git_adapter.get_status()

        # Resolve stable 3-tier project identity
        identity = resolve_project_identity(
            workspace_path=canonical,
            git_adapter=git_adapter,
        )

        return cls(
            workspace_root=Path(workspace_path),
            canonical_root=canonical,
            identity=identity,
            git_state=git_state,
            config=cfg,
            security=sec,
        )

    def to_summary_dict(self) -> dict:
        """Produce safe summary dictionary representation for API and logging."""
        return {
            "canonical_root": self.canonical_root.as_posix(),
            "identity": self.identity.to_dict(),
            "git": self.git_state.to_dict(),
            "project_brain_dir": self.project_brain_dir.as_posix(),
            "code_brain_db_path": self.code_brain_db_path.as_posix(),
        }
