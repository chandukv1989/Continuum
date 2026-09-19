"""Event normalization and workspace boundary enforcement for Continuum.

Normalizes raw filesystem observer events into deterministic Continuum domain events,
filtering out internal directories, generated artifacts, and editor temporary files.
"""
from pathlib import Path
from typing import List, Optional, Sequence, Set

from backend.app.core.logging import get_logger
from backend.app.core.security import SecurityManager
from backend.app.scanner.filtering import FileFilter, matches_any_pattern
from backend.app.watcher.contracts import FileEvent, FileEventType

logger = get_logger("continuum.watcher.normalizer")

# Patterns for ephemeral editor swap, lock, and autosave files that should never trigger scans
EPHEMERAL_EDITOR_SUFFIXES = {
    ".swp",
    ".swo",
    ".tmp",
    ".bak",
    "~",
    ".crdownload",
    ".part",
}


class EventNormalizer:
    """Normalizes raw filesystem events into Continuum domain events with boundary enforcement."""

    def __init__(
        self,
        workspace_root: Path | str,
        file_filter: Optional[FileFilter] = None,
        additional_ignore_patterns: Optional[Sequence[str]] = None,
    ) -> None:
        self.workspace_root = SecurityManager.canonical_path(workspace_root)
        self.file_filter = file_filter or FileFilter()

        # Combine filter patterns with any watcher-specific ignore rules
        self.ignore_patterns: Set[str] = set(self.file_filter.ignore_patterns)
        if additional_ignore_patterns:
            self.ignore_patterns.update(additional_ignore_patterns)

        # Critical: .continuum MUST be ignored to prevent self-triggering feedback loops
        self.ignore_patterns.add(".continuum")
        self.ignore_patterns.add(".git")

    def is_ignored_path(self, relative_path_str: str) -> bool:
        """Determine if a relative path should be ignored by the watcher."""
        if not relative_path_str or relative_path_str in (".", "/"):
            return True

        p = Path(relative_path_str)
        parts = p.parts

        # 1. Check directory segments against ignore patterns (.git, .continuum, node_modules, etc.)
        if matches_any_pattern(parts, list(self.ignore_patterns)):
            return True

        # 2. Check for editor temporary files (e.g. .index.ts.swp, index.ts~, tmp.tmp)
        filename = p.name
        if filename.startswith(".#") or (filename.startswith("#") and filename.endswith("#")):
            return True

        for suffix in EPHEMERAL_EDITOR_SUFFIXES:
            if filename.endswith(suffix):
                return True

        return False

    def normalize_path(self, raw_path: Path | str) -> Optional[str]:
        """Convert a raw filesystem path to a canonical workspace-relative POSIX path.

        Returns None if the path escapes workspace boundaries or matches ignore patterns.
        """
        try:
            canonical = SecurityManager.canonical_path(raw_path)
        except Exception as err:
            logger.debug(f"Failed to canonicalize path '{raw_path}': {err}")
            return None

        # Boundary enforcement: must reside within workspace_root
        try:
            rel_path = canonical.relative_to(self.workspace_root)
        except ValueError:
            # Path is outside workspace root - reject strictly
            logger.warning(
                f"Watcher event path '{raw_path}' escapes workspace boundary '{self.workspace_root}'"
            )
            return None

        rel_posix = rel_path.as_posix()
        if rel_posix in (".", ""):
            return "."

        if self.is_ignored_path(rel_posix):
            return None

        return rel_posix

    def normalize_event(
        self,
        event_type: FileEventType,
        src_path: str,
        dest_path: Optional[str] = None,
        is_directory: bool = False,
    ) -> Optional[FileEvent]:
        """Normalize raw event details into a validated Continuum FileEvent."""
        norm_src = self.normalize_path(src_path)

        if event_type == FileEventType.MOVED:
            norm_dest = self.normalize_path(dest_path) if dest_path else None

            # Case 1: Both source and destination are valid in-workspace paths -> genuine MOVED
            if norm_src and norm_dest:
                return FileEvent(
                    event_type=FileEventType.MOVED,
                    path=norm_dest,
                    old_path=norm_src,
                    is_directory=is_directory,
                )
            # Case 2: Moved into workspace from outside/ignored -> CREATED
            elif norm_dest and not norm_src:
                return FileEvent(
                    event_type=FileEventType.CREATED,
                    path=norm_dest,
                    old_path=None,
                    is_directory=is_directory,
                )
            # Case 3: Moved out of workspace or into ignored folder -> DELETED
            elif norm_src and not norm_dest:
                return FileEvent(
                    event_type=FileEventType.DELETED,
                    path=norm_src,
                    old_path=None,
                    is_directory=is_directory,
                )
            # Case 4: Both ignored/outside
            return None

        # For non-move events, if source path is ignored or outside, drop the event
        if not norm_src:
            return None

        if is_directory:
            return FileEvent(
                event_type=FileEventType.DIRECTORY_CHANGED,
                path=norm_src,
                is_directory=True,
            )

        return FileEvent(
            event_type=event_type,
            path=norm_src,
            is_directory=is_directory,
        )
