"""Recursive workspace file discovery engine for Continuum Phase 2.

Discovers repository files starting from canonical_root, pruning ignored directories
early to maintain high performance, detecting symlink boundary escapes,
and applying FileFilter rules.
"""
import hashlib
import os
from pathlib import Path
from typing import List, Optional, Set, Tuple

from backend.app.core.exceptions import ScannerException
from backend.app.core.logging import get_logger
from backend.app.scanner.contracts import DiscoveredFile, FileFilterStatus, Language
from backend.app.scanner.filtering import FileFilter, matches_any_pattern

logger = get_logger("continuum.scanner.discovery")


def compute_content_hash(path: Path) -> str:
    """Compute deterministic SHA-256 hash of file content."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class FileDiscovery:
    """Discovers and categorizes repository files within workspace boundaries."""

    def __init__(
        self,
        workspace_root: Path,
        file_filter: Optional[FileFilter] = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.filter = file_filter or FileFilter()

    def discover(self) -> List[DiscoveredFile]:
        """Perform iterative traversal of workspace root to discover and categorize all files.

        Returns:
            List of DiscoveredFile records.
        """
        if not self.workspace_root.exists() or not self.workspace_root.is_dir():
            raise ScannerException(
                f"Cannot discover files: workspace root '{self.workspace_root}' is not a directory",
                details={"workspace_root": self.workspace_root.as_posix()},
            )

        discovered: List[DiscoveredFile] = []
        dir_stack: List[Path] = [self.workspace_root]
        visited_dirs: Set[Tuple[int, int]] = set()

        try:
            root_stat = self.workspace_root.stat()
            visited_dirs.add((root_stat.st_dev, root_stat.st_ino))
        except OSError:
            pass

        while dir_stack:
            current_dir = dir_stack.pop()

            try:
                with os.scandir(current_dir) as entries:
                    for entry in entries:
                        entry_path = Path(entry.path)

                        # Symlink safety check: resolve real target
                        if entry.is_symlink():
                            try:
                                resolved = entry_path.resolve()
                                resolved.relative_to(self.workspace_root)
                            except (ValueError, RuntimeError, OSError):
                                # Symlink points outside workspace or loops
                                discovered.append(
                                    DiscoveredFile(
                                        canonical_path=entry_path,
                                        relative_path=entry_path.relative_to(self.workspace_root).as_posix()
                                        if entry_path.is_relative_to(self.workspace_root)
                                        else entry_path.name,
                                        size_bytes=0,
                                        mtime=0.0,
                                        status=FileFilterStatus.OUTSIDE_WORKSPACE,
                                        language=Language.UNKNOWN,
                                    )
                                )
                                continue

                        if entry.is_dir(follow_symlinks=False):
                            # Early pruning of ignored directories (e.g. .git, node_modules)
                            if matches_any_pattern([entry.name], self.filter.ignore_patterns):
                                continue

                            try:
                                dstat = entry_path.stat()
                                dev_ino = (dstat.st_dev, dstat.st_ino)
                                if dev_ino in visited_dirs:
                                    # Prevent circular directory symlinks
                                    continue
                                visited_dirs.add(dev_ino)
                            except OSError:
                                continue

                            dir_stack.append(entry_path)

                        elif entry.is_file(follow_symlinks=False):
                            try:
                                fstat = entry.stat()
                                size = fstat.st_size
                                mtime = fstat.st_mtime
                            except OSError:
                                continue

                            status, lang = self.filter.evaluate_file(
                                entry_path,
                                self.workspace_root,
                                stat_size=size,
                            )

                            rel_posix = entry_path.relative_to(self.workspace_root).as_posix()

                            content_hash = None
                            if status == FileFilterStatus.PARSEABLE:
                                try:
                                    content_hash = compute_content_hash(entry_path)
                                except OSError:
                                    status = FileFilterStatus.IGNORED

                            discovered.append(
                                DiscoveredFile(
                                    canonical_path=entry_path,
                                    relative_path=rel_posix,
                                    size_bytes=size,
                                    mtime=mtime,
                                    status=status,
                                    language=lang,
                                    content_hash=content_hash,
                                )
                            )

            except (PermissionError, OSError) as err:
                logger.warning(
                    f"Skipping inaccessible directory: {current_dir}",
                    extra={"directory": current_dir.as_posix(), "error": str(err)},
                )
                continue

        # Sort discovered files deterministically by relative POSIX path
        discovered.sort(key=lambda d: d.relative_path)
        return discovered
