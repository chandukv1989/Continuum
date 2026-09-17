"""Domain exception hierarchy for Continuum.

All exceptions inherit from ContinuumBaseException to enable unified error
handling, structured logging, and safe translation to API responses without
exposing internal stack traces.
"""
from typing import Any, Dict, Optional


class ContinuumBaseException(Exception):
    """Base exception for all Continuum domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "CONTINUUM_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to structured dict for safe logging and responses."""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


class InvalidWorkspaceException(ContinuumBaseException):
    """Raised when the specified workspace path is invalid, missing, or not a directory."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="INVALID_WORKSPACE",
            details=details,
        )


class WorkspaceBoundaryException(ContinuumBaseException):
    """Raised when a path or operation escapes the designated workspace boundary."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="WORKSPACE_BOUNDARY_VIOLATION",
            details=details,
        )


class GitUnavailableException(ContinuumBaseException):
    """Raised when the git executable is not found or not functional."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="GIT_UNAVAILABLE",
            details=details,
        )


class GitCommandException(ContinuumBaseException):
    """Raised when a read-only Git command execution fails."""

    def __init__(
        self,
        message: str,
        command: Optional[list] = None,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        merged_details = details or {}
        if command:
            merged_details["command"] = " ".join(command)
        if returncode is not None:
            merged_details["returncode"] = returncode
        if stderr:
            merged_details["stderr"] = stderr.strip()
        super().__init__(
            message=message,
            code="GIT_COMMAND_FAILED",
            details=merged_details,
        )


class ConfigurationException(ContinuumBaseException):
    """Raised when configuration validation or loading fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            details=details,
        )


class SecurityException(ContinuumBaseException):
    """Raised when a security boundary, allowlist, or environment rule is violated."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="SECURITY_VIOLATION",
            details=details,
        )


class ProcessTimeoutException(ContinuumBaseException):
    """Raised when a subprocess command exceeds its allowed timeout."""

    def __init__(
        self,
        message: str,
        command: Optional[list] = None,
        timeout: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        merged_details = details or {}
        if command:
            merged_details["command"] = " ".join(command)
        if timeout is not None:
            merged_details["timeout_seconds"] = timeout
        super().__init__(
            message=message,
            code="PROCESS_TIMEOUT",
            details=merged_details,
        )


class ScannerException(ContinuumBaseException):
    """Raised when repository scanning encounters an unrecoverable failure."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="SCANNER_ERROR",
            details=details,
        )


class ParserException(ContinuumBaseException):
    """Raised when AST parsing fails or encounters an unrecoverable grammar issue."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="PARSER_ERROR",
            details=details,
        )


class CodeBrainException(ContinuumBaseException):
    """Raised when Code Brain SQLite persistence or retrieval encounters an error."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="CODE_BRAIN_ERROR",
            details=details,
        )

