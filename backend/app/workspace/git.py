"""Read-only Git Adapter for Continuum.

Strictly enforces read-only access to Git repository state.
Uses `git status --porcelain=v2 --branch` for deterministic status parsing.

NEVER executes mutating git commands:
- No git add
- No git commit
- No git push
- No git checkout
- No git reset
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from backend.app.core.exceptions import (
    GitCommandException,
    GitUnavailableException,
    ProcessTimeoutException,
)
from backend.app.core.logging import get_logger
from backend.app.core.security import SecurityManager

logger = get_logger("continuum.git")


@dataclass(frozen=True)
class GitStatus:
    """Structured representation of repository Git state."""

    is_git_repo: bool
    repository_root: Optional[Path] = None
    branch: Optional[str] = None
    current_commit: Optional[str] = None
    remote_origin: Optional[str] = None
    modified_files: List[str] = field(default_factory=list)
    staged_files: List[str] = field(default_factory=list)
    untracked_files: List[str] = field(default_factory=list)
    uncommitted_changes: bool = False
    status_state: str = "non_repo"

    def to_dict(self) -> dict:
        """Serialize status to dict."""
        return {
            "is_git_repo": self.is_git_repo,
            "repository_root": self.repository_root.as_posix() if self.repository_root else None,
            "branch": self.branch,
            "current_commit": self.current_commit,
            "remote_origin": self.remote_origin,
            "modified_files": self.modified_files,
            "staged_files": self.staged_files,
            "untracked_files": self.untracked_files,
            "uncommitted_changes": self.uncommitted_changes,
            "status_state": self.status_state,
        }


class GitAdapter:
    """Read-only adapter for interacting with Git repositories."""

    # Explicit allowlist of permissible read-only git subcommands
    ALLOWED_GIT_SUBCOMMANDS = {
        "status",
        "rev-parse",
        "rev-list",
        "remote",
        "log",
        "diff",
    }

    def __init__(
        self,
        workspace_root: Path | str,
        security_manager: Optional[SecurityManager] = None,
        timeout: float = 15.0,
    ) -> None:
        self.workspace_root = SecurityManager.canonical_path(workspace_root)
        self.security = security_manager or SecurityManager()
        self.timeout = timeout

    def _execute_read_only_git(self, args: List[str]) -> str:
        """Execute a read-only git command and return stdout."""
        if not args:
            raise GitCommandException("Empty git arguments provided")

        subcommand = args[0]
        if subcommand not in self.ALLOWED_GIT_SUBCOMMANDS:
            raise GitCommandException(
                f"Prohibited git command '{subcommand}'. GitAdapter is strictly read-only."
            )

        full_cmd = ["git"] + args

        try:
            res = self.security.run_safe_subprocess(
                args=full_cmd,
                cwd=self.workspace_root,
                timeout=self.timeout,
            )
        except ProcessTimeoutException as err:
            raise GitCommandException(
                f"Git command timed out: {err.message}",
                command=full_cmd,
                details=err.details,
            )
        except Exception as err:
            raise GitUnavailableException(
                f"Failed to execute git: {err}",
                details={"error": str(err)},
            )

        if res.returncode != 0:
            raise GitCommandException(
                f"Git command failed with return code {res.returncode}",
                command=full_cmd,
                returncode=res.returncode,
                stderr=res.stderr,
            )

        return res.stdout

    def check_is_git_repo(self) -> bool:
        """Check if workspace is inside a git repository."""
        try:
            stdout = self._execute_read_only_git(["rev-parse", "--is-inside-work-tree"])
            return stdout.strip().lower() == "true"
        except (GitCommandException, GitUnavailableException):
            return False

    def get_repository_root(self) -> Optional[Path]:
        """Find the root directory of the git repository."""
        try:
            stdout = self._execute_read_only_git(["rev-parse", "--show-toplevel"])
            clean_path = stdout.strip()
            return Path(clean_path).resolve() if clean_path else None
        except (GitCommandException, GitUnavailableException):
            return None

    def get_remote_origin(self) -> Optional[str]:
        """Get git remote origin URL if configured."""
        try:
            stdout = self._execute_read_only_git(["remote", "get-url", "origin"])
            url = stdout.strip()
            return url if url else None
        except (GitCommandException, GitUnavailableException):
            return None

    def get_root_commit(self) -> Optional[str]:
        """Get the root commit SHA (initial commit) of the repository.

        Command: git rev-list --max-parents=0 HEAD
        """
        try:
            stdout = self._execute_read_only_git(["rev-list", "--max-parents=0", "HEAD"])
            lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            return lines[0] if lines else None
        except (GitCommandException, GitUnavailableException):
            return None

    def get_head_commit(self) -> Optional[str]:
        """Get the current HEAD commit SHA."""
        try:
            stdout = self._execute_read_only_git(["rev-parse", "HEAD"])
            sha = stdout.strip()
            return sha if sha and not sha.startswith("fatal") else None
        except (GitCommandException, GitUnavailableException):
            return None

    def get_status(self) -> GitStatus:
        """Query repository status using `git status --porcelain=v2 --branch`."""
        if not self.check_is_git_repo():
            return GitStatus(is_git_repo=False, status_state="non_repo")

        repo_root = self.get_repository_root() or self.workspace_root
        remote_origin = self.get_remote_origin()

        try:
            stdout = self._execute_read_only_git(["status", "--porcelain=v2", "--branch"])
        except (GitCommandException, GitUnavailableException) as err:
            logger.warning(
                "Could not retrieve porcelain=v2 status",
                extra={"error": str(err)},
            )
            return GitStatus(
                is_git_repo=True,
                repository_root=repo_root,
                remote_origin=remote_origin,
                status_state="error",
            )

        branch_name: Optional[str] = None
        commit_oid: Optional[str] = None
        modified_files: List[str] = []
        staged_files: List[str] = []
        untracked_files: List[str] = []

        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("# branch.head "):
                val = line[len("# branch.head "):].strip()
                if val and val != "(detached)":
                    branch_name = val
                else:
                    branch_name = "HEAD (detached)"
            elif line.startswith("# branch.oid "):
                val = line[len("# branch.oid "):].strip()
                if val and val != "(initial)":
                    commit_oid = val

            elif line.startswith("1 ") or line.startswith("2 "):
                # Ordinary changed or renamed/copied entry
                # Format: 1 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <path>
                parts = line.split(maxsplit=8)
                if len(parts) >= 9:
                    xy = parts[1]
                    file_path = parts[8]
                    # Check staged changes (X)
                    if xy[0] != ".":
                        staged_files.append(file_path)
                    # Check unstaged changes (Y)
                    if xy[1] != ".":
                        modified_files.append(file_path)
                elif len(parts) >= 2:
                    modified_files.append(parts[-1])

            elif line.startswith("u "):
                # Unmerged entry
                parts = line.split(maxsplit=10)
                if len(parts) >= 11:
                    modified_files.append(parts[10])

            elif line.startswith("? "):
                # Untracked file
                file_path = line[2:].strip()
                untracked_files.append(file_path)

        has_uncommitted = bool(modified_files or staged_files or untracked_files)

        if not has_uncommitted:
            status_state = "clean"
        elif modified_files or staged_files:
            status_state = "dirty"
        else:
            status_state = "untracked_only"

        return GitStatus(
            is_git_repo=True,
            repository_root=repo_root,
            branch=branch_name,
            current_commit=commit_oid,
            remote_origin=remote_origin,
            modified_files=sorted(list(set(modified_files))),
            staged_files=sorted(list(set(staged_files))),
            untracked_files=sorted(list(set(untracked_files))),
            uncommitted_changes=has_uncommitted,
            status_state=status_state,
        )
