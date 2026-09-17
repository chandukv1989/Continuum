"""Continuum FastAPI application factory and entry point."""
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.app.api.routes import router as api_router
from backend.app.core.config import ContinuumSettings, get_settings, reset_settings
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
from backend.app.core.logging import configure_logging, get_logger

logger = get_logger("continuum.api")


def create_app(settings: Optional[ContinuumSettings] = None) -> FastAPI:
    """Create and configure FastAPI application instance."""
    cfg = settings or get_settings()
    if settings:
        reset_settings(settings)

    configure_logging(level=cfg.log_level)

    app = FastAPI(
        title="Continuum Core API",
        version=cfg.app_version,
        description="Local-first developer intelligence and learning platform core foundation",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Register domain exception handlers
    @app.exception_handler(InvalidWorkspaceException)
    async def invalid_workspace_handler(request: Request, exc: InvalidWorkspaceException):
        logger.warning(f"Invalid workspace: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=400,
            content=exc.to_dict(),
        )

    @app.exception_handler(WorkspaceBoundaryException)
    async def boundary_violation_handler(request: Request, exc: WorkspaceBoundaryException):
        logger.warning(f"Workspace boundary violation: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=403,
            content=exc.to_dict(),
        )

    @app.exception_handler(SecurityException)
    async def security_violation_handler(request: Request, exc: SecurityException):
        logger.error(f"Security violation: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=403,
            content=exc.to_dict(),
        )

    @app.exception_handler(ProcessTimeoutException)
    async def timeout_handler(request: Request, exc: ProcessTimeoutException):
        logger.error(f"Process timeout: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=504,
            content=exc.to_dict(),
        )

    @app.exception_handler(GitUnavailableException)
    async def git_unavailable_handler(request: Request, exc: GitUnavailableException):
        logger.error(f"Git unavailable: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=503,
            content=exc.to_dict(),
        )

    @app.exception_handler(GitCommandException)
    async def git_command_handler(request: Request, exc: GitCommandException):
        logger.error(f"Git command failed: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=500,
            content=exc.to_dict(),
        )

    @app.exception_handler(ConfigurationException)
    async def config_error_handler(request: Request, exc: ConfigurationException):
        logger.error(f"Configuration error: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=500,
            content=exc.to_dict(),
        )

    @app.exception_handler(ContinuumBaseException)
    async def domain_error_handler(request: Request, exc: ContinuumBaseException):
        logger.error(f"Continuum domain error: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=500,
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def general_unhandled_handler(request: Request, exc: Exception):
        logger.critical(f"Unhandled server error: {exc}", exc_info=True)
        # Never expose raw internal stack traces to the client
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An internal error occurred. Detailed error details are logged securely.",
                "details": {},
            },
        )

    # Attach API router
    app.include_router(api_router)

    return app


# Default ASGI application instance
app = create_app()
