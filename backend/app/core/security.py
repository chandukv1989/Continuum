"""Security boundaries and safe execution policies for Continuum.

Enforces:
1. Workspace boundary confinement (preventing directory traversal attacks)
2. Canonical path normalization using Path.resolve().as_posix()
3. Subprocess execution security:
   - shell=False strictly enforced
   - Argument arrays only
   - Executable allowlist
   - Environment filtering (preventing credential leakage)
   - Process group creation and termination on timeout
"""
import os
import signal
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from backend.app.core.exceptions import (
    ProcessTimeoutException,
    SecurityException,
    WorkspaceBoundaryException,
)
from backend.app.core.logging import get_logger

logger = get_logger("continuum.security")

# Allowed executables for subprocess execution
DEFAULT_EXECUTABLE_ALLOWLIST: Set[str] = {
    "git",
    "python",
    "python3",
    "node",
    "npm",
    "tsc",
    "pytest",
    "which",
}

# Environment variable keys permitted to pass through to child processes
SAFE_ENV_PASSTHROUGH: Set[str] = {
    "PATH",
    "HOME",
    "USER",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "SHELL",
    "TZ",
    "TMPDIR",
    "VIRTUAL_ENV",
}


class SecurityManager:
    """Manages workspace boundaries and safe execution controls."""

    def __init__(
        self,
        allowed_executables: Optional[Set[str]] = None,
        safe_env_keys: Optional[Set[str]] = None,
    ) -> None:
        self.allowed_executables = (
            set(allowed_executables)
            if allowed_executables is not None
            else set(DEFAULT_EXECUTABLE_ALLOWLIST)
        )
        self.safe_env_keys = (
            set(safe_env_keys)
            if safe_env_keys is not None
            else set(SAFE_ENV_PASSTHROUGH)
        )

    @staticmethod
    def canonical_path(path: Path | str) -> Path:
        """Resolve a path to its canonical, absolute filesystem path."""
        p = Path(path).expanduser()
        return p.resolve()

    @staticmethod
    def canonical_posix_path(path: Path | str) -> str:
        """Return canonical POSIX string representation for a path."""
        return SecurityManager.canonical_path(path).as_posix()

    def validate_workspace_boundary(
        self,
        workspace_root: Path | str,
        target_path: Path | str,
    ) -> Path:
        """Ensure target_path is strictly within workspace_root.

        Raises WorkspaceBoundaryException if traversal outside workspace occurs.
        """
        canonical_workspace = self.canonical_path(workspace_root)
        canonical_target = self.canonical_path(target_path)

        # Check if target is workspace itself or inside workspace
        try:
            canonical_target.relative_to(canonical_workspace)
        except ValueError:
            raise WorkspaceBoundaryException(
                f"Path '{target_path}' escapes designated workspace boundary '{workspace_root}'",
                details={
                    "workspace": canonical_workspace.as_posix(),
                    "target": canonical_target.as_posix(),
                },
            )

        return canonical_target

    def filter_environment(self, custom_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Produce a filtered environment dict that omits credentials and sensitive tokens."""
        filtered: Dict[str, str] = {}

        # First copy whitelisted system variables
        for key in self.safe_env_keys:
            if key in os.environ:
                filtered[key] = os.environ[key]

        # Merge custom variables if safe
        if custom_env:
            for key, val in custom_env.items():
                upper_key = key.upper()
                if any(
                    token in upper_key
                    for token in ("KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH", "CREDENTIAL")
                ):
                    logger.warning(
                        "Filtered sensitive variable from child environment",
                        extra={"filtered_var": key},
                    )
                    continue
                filtered[key] = str(val)

        return filtered

    def run_safe_subprocess(
        self,
        args: Sequence[str],
        cwd: Path | str,
        timeout: float = 30.0,
        env: Optional[Dict[str, str]] = None,
        check_binary_allowlist: bool = True,
    ) -> subprocess.CompletedProcess:
        """Execute a process safely using shell=False, executable allowlists, and timeouts."""
        if not args or not isinstance(args, (list, tuple)):
            raise SecurityException(
                "Process arguments must be a non-empty sequence of strings (shell=False)",
                details={"args": str(args)},
            )

        binary_name = Path(args[0]).name

        if check_binary_allowlist and binary_name not in self.allowed_executables:
            raise SecurityException(
                f"Executable '{binary_name}' is not in the allowed executable list",
                details={"executable": binary_name, "allowed": sorted(list(self.allowed_executables))},
            )

        safe_cwd = self.canonical_path(cwd)
        if not safe_cwd.exists() or not safe_cwd.is_dir():
            raise SecurityException(
                f"Subprocess working directory does not exist or is not a directory: {safe_cwd}",
                details={"cwd": safe_cwd.as_posix()},
            )

        safe_env = self.filter_environment(env)

        logger.debug(
            "Executing safe subprocess",
            extra={"binary": binary_name, "cwd": safe_cwd.as_posix(), "timeout": timeout},
        )

        try:
            # We use start_new_session=True to create a new process group for clean termination
            proc = subprocess.Popen(
                list(args),
                cwd=str(safe_cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=safe_env,
                shell=False,
                start_new_session=True,
                text=True,
            )

            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                return subprocess.CompletedProcess(
                    args=list(args),
                    returncode=proc.returncode,
                    stdout=stdout,
                    stderr=stderr,
                )
            except subprocess.TimeoutExpired:
                # Terminate entire process group
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
                proc.communicate()  # Clean up zombie
                raise ProcessTimeoutException(
                    f"Command '{args[0]}' timed out after {timeout} seconds",
                    command=list(args),
                    timeout=timeout,
                )

        except (OSError, ValueError) as err:
            if isinstance(err, ProcessTimeoutException):
                raise
            raise SecurityException(
                f"Failed to execute command '{args[0]}': {err}",
                details={"command": list(args), "error": str(err)},
            )
