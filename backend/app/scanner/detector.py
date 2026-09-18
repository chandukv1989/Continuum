"""Change detection engine for Continuum Phase 4.1.

Detects added, modified, deleted, and renamed files by comparing current workspace state
against Code Brain database state.
Authoritative source of truth: Filesystem content hash (SHA-256).
Optional acceleration: Git status porcelain v2.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.core.logging import get_logger
from backend.app.scanner.contracts import (
    ChangeSet,
    ChangeType,
    DiscoveredFile,
    FileChange,
    FileFilterStatus,
)
from backend.app.scanner.discovery import FileDiscovery, compute_content_hash
from backend.app.scanner.filtering import FileFilter
from backend.app.workspace.context import WorkspaceContext

logger = get_logger("continuum.scanner.detector")


class ChangeDetector:
    """Detects repository mutations deterministically against stored Code Brain facts."""

    def __init__(
        self,
        context: WorkspaceContext,
        code_brain_repo: CodeBrainRepository,
        file_filter: Optional[FileFilter] = None,
    ) -> None:
        self.context = context
        self.code_brain_repo = code_brain_repo
        self.config = context.config
        self.file_filter = file_filter or FileFilter(
            max_file_size_bytes=self.config.max_file_size_bytes,
            ignore_patterns=self.config.scanner_ignore_patterns,
        )
        self.discovery = FileDiscovery(
            workspace_root=context.canonical_root,
            file_filter=self.file_filter,
        )

    def detect_changes(
        self,
        use_git_acceleration: bool = False,
    ) -> Tuple[ChangeSet, Dict[str, DiscoveredFile]]:
        """Compute the delta between current workspace files and Code Brain.

        Returns:
            Tuple of (ChangeSet, mapping of path -> DiscoveredFile for added/modified files)
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Fetch current recorded files from Code Brain
        db_files = self.code_brain_repo.get_files()
        db_file_map: Dict[str, Dict] = {f["path"]: f for f in db_files}

        # 2. Discover all currently valid files in workspace
        current_discovered = self.discovery.discover()
        current_map: Dict[str, DiscoveredFile] = {
            f.relative_path: f for f in current_discovered
        }

        changes: List[FileChange] = []
        parseable_candidates: Dict[str, DiscoveredFile] = {}

        current_paths = set(current_map.keys())
        db_paths = set(db_file_map.keys())

        added_raw_paths = current_paths - db_paths
        deleted_raw_paths = db_paths - current_paths
        common_paths = current_paths & db_paths

        # 3. Check for renames among added and deleted files via content_hash matching
        # If a deleted file has the exact same content_hash as an added file, classify as RENAMED
        detected_renames_old: Set[str] = set()
        detected_renames_new: Set[str] = set()

        # Build hash maps for candidate rename pairs
        deleted_hash_map: Dict[str, List[str]] = {}
        for dp in deleted_raw_paths:
            d_hash = db_file_map[dp].get("content_hash")
            if d_hash:
                deleted_hash_map.setdefault(d_hash, []).append(dp)

        for ap in sorted(list(added_raw_paths)):
            df = current_map[ap]
            if df.content_hash and df.content_hash in deleted_hash_map:
                candidates = deleted_hash_map[df.content_hash]
                if len(candidates) == 1:
                    # Unambiguous 1-to-1 rename
                    old_p = candidates[0]
                    detected_renames_old.add(old_p)
                    detected_renames_new.add(ap)
                    changes.append(
                        FileChange(
                            path=ap,
                            change_type=ChangeType.RENAMED,
                            old_path=old_p,
                            old_content_hash=df.content_hash,
                            new_content_hash=df.content_hash,
                            size_bytes=df.size_bytes,
                            mtime=df.mtime,
                        )
                    )
                    parseable_candidates[ap] = df

        # 4. Process genuine ADDED files
        for ap in sorted(list(added_raw_paths)):
            if ap in detected_renames_new:
                continue
            df = current_map[ap]
            changes.append(
                FileChange(
                    path=ap,
                    change_type=ChangeType.ADDED,
                    new_content_hash=df.content_hash,
                    size_bytes=df.size_bytes,
                    mtime=df.mtime,
                )
            )
            parseable_candidates[ap] = df

        # 5. Process genuine DELETED files
        for dp in sorted(list(deleted_raw_paths)):
            if dp in detected_renames_old:
                continue
            db_record = db_file_map[dp]
            changes.append(
                FileChange(
                    path=dp,
                    change_type=ChangeType.DELETED,
                    old_content_hash=db_record.get("content_hash"),
                )
            )

        # 6. Process MODIFIED files (common paths)
        for cp in sorted(list(common_paths)):
            df = current_map[cp]
            db_record = db_file_map[cp]

            # Compare content_hash
            new_hash = df.content_hash
            old_hash = db_record.get("content_hash")

            if new_hash != old_hash:
                changes.append(
                    FileChange(
                        path=cp,
                        change_type=ChangeType.MODIFIED,
                        old_content_hash=old_hash,
                        new_content_hash=new_hash,
                        size_bytes=df.size_bytes,
                        mtime=df.mtime,
                    )
                )
                parseable_candidates[cp] = df

        source_desc = "HYBRID_GIT_ACCELERATED" if use_git_acceleration else "FILESYSTEM_CONTENT_HASH"

        change_set = ChangeSet(
            changes=changes,
            detected_at=now_iso,
            detection_source=source_desc,
        )

        logger.info(
            "Change detection complete",
            extra={
                "changes_count": len(changes),
                "added": len(change_set.added_paths),
                "modified": len(change_set.modified_paths),
                "deleted": len(change_set.deleted_paths),
                "renamed": len(change_set.renamed_pairs),
            },
        )

        return change_set, parseable_candidates
