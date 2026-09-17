"""Stable project identity resolution following the three-tier hierarchy.

Hierarchy:
1. TIER 1: Git Remote Origin URL
2. TIER 2: Git Root Commit SHA (`git rev-list --max-parents=0 HEAD`)
3. TIER 3: SHA-256 of Canonical POSIX Path (`Path.resolve().as_posix()`)

Ensures project identity survives repository directory relocation whenever a
stronger (Tier 1 or Tier 2) Git identity exists.
"""
import hashlib
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Optional

from backend.app.core.logging import get_logger
from backend.app.core.security import SecurityManager
from backend.app.workspace.git import GitAdapter

logger = get_logger("continuum.identity")


class IdentityTier(IntEnum):
    """Identity resolution tier."""

    TIER_1_REMOTE_ORIGIN = 1
    TIER_2_ROOT_COMMIT = 2
    TIER_3_CANONICAL_PATH = 3


@dataclass(frozen=True)
class ProjectIdentity:
    """Stable project identifier and provenance."""

    project_id: str
    tier: int
    tier_name: str
    raw_identifier: str
    canonical_path: str

    def to_dict(self) -> dict:
        """Convert identity to dictionary representation."""
        return {
            "project_id": self.project_id,
            "tier": self.tier,
            "tier_name": self.tier_name,
            "raw_identifier": self.raw_identifier,
            "canonical_path": self.canonical_path,
        }


def compute_project_id(raw_identifier: str) -> str:
    """Compute deterministic, filesystem-safe project_id hex digest."""
    clean = raw_identifier.strip()
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:32]


def resolve_project_identity(
    workspace_path: Path | str,
    git_adapter: Optional[GitAdapter] = None,
) -> ProjectIdentity:
    """Resolve project identity adhering to the 3-tier evidence hierarchy."""
    canonical_root = SecurityManager.canonical_path(workspace_path)
    canonical_posix = canonical_root.as_posix()

    adapter = git_adapter or GitAdapter(canonical_root)

    # Check Tier 1: Git Remote Origin URL
    if adapter.check_is_git_repo():
        remote_url = adapter.get_remote_origin()
        if remote_url and remote_url.strip():
            raw_id = remote_url.strip()
            project_id = compute_project_id(raw_id)
            logger.info(
                "Resolved project identity via Tier 1 (Remote Origin)",
                extra={"project_id": project_id, "tier": 1},
            )
            return ProjectIdentity(
                project_id=project_id,
                tier=IdentityTier.TIER_1_REMOTE_ORIGIN.value,
                tier_name="REMOTE_ORIGIN",
                raw_identifier=raw_id,
                canonical_path=canonical_posix,
            )

        # Check Tier 2: Root Commit SHA
        root_commit = adapter.get_root_commit()
        if root_commit and root_commit.strip():
            raw_id = root_commit.strip()
            project_id = compute_project_id(raw_id)
            logger.info(
                "Resolved project identity via Tier 2 (Root Commit)",
                extra={"project_id": project_id, "tier": 2},
            )
            return ProjectIdentity(
                project_id=project_id,
                tier=IdentityTier.TIER_2_ROOT_COMMIT.value,
                tier_name="ROOT_COMMIT",
                raw_identifier=raw_id,
                canonical_path=canonical_posix,
            )

    # Fallback Tier 3: SHA-256 of Canonical POSIX Path
    raw_id = canonical_posix
    project_id = compute_project_id(raw_id)
    logger.info(
        "Resolved project identity via Tier 3 (Canonical Path)",
        extra={"project_id": project_id, "tier": 3},
    )
    return ProjectIdentity(
        project_id=project_id,
        tier=IdentityTier.TIER_3_CANONICAL_PATH.value,
        tier_name="CANONICAL_PATH",
        raw_identifier=raw_id,
        canonical_path=canonical_posix,
    )
