"""Unit tests for domain exception hierarchy."""
from backend.app.core.exceptions import (
    ConfigurationException,
    ContinuumBaseException,
    GitCommandException,
    GitUnavailableException,
    InvalidWorkspaceException,
    ProcessTimeoutException,
    SecurityException,
    WorkspaceBoundaryException,
)


def test_exception_inheritance():
    """Verify all domain exceptions inherit from ContinuumBaseException."""
    exceptions = [
        InvalidWorkspaceException("invalid"),
        WorkspaceBoundaryException("boundary"),
        GitUnavailableException("no git"),
        GitCommandException("git failed"),
        ConfigurationException("config error"),
        SecurityException("security issue"),
        ProcessTimeoutException("timed out"),
    ]
    for exc in exceptions:
        assert isinstance(exc, ContinuumBaseException)
        assert isinstance(exc, Exception)
        data = exc.to_dict()
        assert "error" in data
        assert "message" in data
        assert "details" in data


def test_git_command_exception_details():
    """Verify GitCommandException structures command, returncode, and stderr."""
    exc = GitCommandException(
        message="Failed command",
        command=["git", "status"],
        returncode=128,
        stderr="fatal: not a git repo",
    )
    data = exc.to_dict()
    assert data["error"] == "GIT_COMMAND_FAILED"
    assert data["details"]["command"] == "git status"
    assert data["details"]["returncode"] == 128
    assert data["details"]["stderr"] == "fatal: not a git repo"


def test_process_timeout_exception_details():
    """Verify ProcessTimeoutException stores command and timeout."""
    exc = ProcessTimeoutException(
        message="Subprocess timed out",
        command=["python3", "script.py"],
        timeout=10.0,
    )
    data = exc.to_dict()
    assert data["error"] == "PROCESS_TIMEOUT"
    assert data["details"]["command"] == "python3 script.py"
    assert data["details"]["timeout_seconds"] == 10.0


def test_workspace_boundary_exception():
    """Verify WorkspaceBoundaryException code."""
    exc = WorkspaceBoundaryException(
        message="Escaped boundary",
        details={"workspace": "/app", "target": "/etc/passwd"},
    )
    data = exc.to_dict()
    assert data["error"] == "WORKSPACE_BOUNDARY_VIOLATION"
    assert data["details"]["workspace"] == "/app"
    assert data["details"]["target"] == "/etc/passwd"
