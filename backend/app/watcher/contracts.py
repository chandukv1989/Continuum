"""Domain contracts and data models for Continuum filesystem observation.

Independent of Watchdog, Git, or UI components.
"""
from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Set


class FileEventType(str, Enum):
    """Normalized filesystem event classification."""

    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    MOVED = "moved"
    DIRECTORY_CHANGED = "directory_changed"


@dataclass(frozen=True)
class FileEvent:
    """Normalized representation of a single filesystem activity occurrence."""

    event_type: FileEventType
    path: str  # Canonical POSIX relative path from workspace root
    old_path: Optional[str] = None  # Canonical POSIX relative path for MOVED events
    is_directory: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        return {
            "event_type": self.event_type.value,
            "path": self.path,
            "old_path": self.old_path,
            "is_directory": self.is_directory,
            "timestamp": self.timestamp,
        }


@dataclass
class WatchBatch:
    """A coalesced, debounced batch of affected paths requiring re-evaluation."""

    batch_id: str
    affected_paths: Set[str]
    events: List[FileEvent]
    created_at: float
    flushed_at: float = field(default_factory=time.time)

    @property
    def is_empty(self) -> bool:
        """True if batch contains no affected paths."""
        return len(self.affected_paths) == 0

    @property
    def paths_count(self) -> int:
        """Count of unique paths affected in this batch."""
        return len(self.affected_paths)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize batch metadata to dictionary."""
        return {
            "batch_id": self.batch_id,
            "affected_paths": sorted(list(self.affected_paths)),
            "events_count": len(self.events),
            "created_at": self.created_at,
            "flushed_at": self.flushed_at,
        }


@dataclass
class WatcherStatus:
    """Runtime status of the filesystem watcher service."""

    is_running: bool
    is_scanning: bool
    project_id: str
    workspace_root: str
    pending_paths_count: int = 0
    total_events_received: int = 0
    total_batches_processed: int = 0
    total_scans_triggered: int = 0
    total_scans_failed: int = 0
    last_event_timestamp: Optional[float] = None
    last_scan_timestamp: Optional[float] = None
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize watcher status to dictionary."""
        return {
            "is_running": self.is_running,
            "is_scanning": self.is_scanning,
            "project_id": self.project_id,
            "workspace_root": self.workspace_root,
            "pending_paths_count": self.pending_paths_count,
            "total_events_received": self.total_events_received,
            "total_batches_processed": self.total_batches_processed,
            "total_scans_triggered": self.total_scans_triggered,
            "total_scans_failed": self.total_scans_failed,
            "last_event_timestamp": self.last_event_timestamp,
            "last_scan_timestamp": self.last_scan_timestamp,
            "last_error": self.last_error,
        }
