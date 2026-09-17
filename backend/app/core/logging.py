"""Centralized structured logging for Continuum.

Features:
- Structured JSON-friendly and human-readable output
- Secret and credential sanitization (tokens, API keys, passwords)
- Prevention of raw environment or credential leakage
- Contextual tags (workspace, component, operation)
"""
import json
import logging
import re
from typing import Any, Dict, Optional

SENSITIVE_KEY_PATTERNS = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|auth|credential|bearer|private[_-]?key)"
)

SENSITIVE_VALUE_PATTERNS = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{10,}", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(ghp_[A-Za-z0-9]{20,})", re.IGNORECASE), r"[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"([a-zA-Z0-9_-]{20,}:[a-zA-Z0-9_-]{20,})"), r"[REDACTED_CREDENTIAL]"),
]


def sanitize_value(value: Any) -> Any:
    """Recursively sanitize potentially sensitive values in data structures."""
    if isinstance(value, dict):
        sanitized = {}
        for k, v in value.items():
            if SENSITIVE_KEY_PATTERNS.search(str(k)):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_value(v)
        return sanitized
    elif isinstance(value, (list, tuple, set)):
        return [sanitize_value(item) for item in value]
    elif isinstance(value, str):
        masked = value
        for pattern, replacement in SENSITIVE_VALUE_PATTERNS:
            masked = pattern.sub(replacement, masked)
        return masked
    return value


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs JSON-friendly structured logs with sanitized metadata."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_value(record.getMessage()),
        }

        # Include structured extra fields if present
        extra_data: Dict[str, Any] = {}
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
        }
        for key, val in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                extra_data[key] = sanitize_value(val)

        if extra_data:
            payload["context"] = extra_data

        if record.exc_info:
            # We provide a clean exception summary instead of dumping raw internals
            exc_type, exc_val, _ = record.exc_info
            payload["exception"] = {
                "type": getattr(exc_type, "__name__", "Exception"),
                "message": sanitize_value(str(exc_val)),
            }

        return json.dumps(payload, default=str)


def get_logger(name: str = "continuum") -> logging.Logger:
    """Retrieve a configured structured logger."""
    return logging.getLogger(name)


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Configure root logging for Continuum."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger("continuum")
    root_logger.setLevel(numeric_level)

    # Avoid duplicate handlers
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        if json_output:
            handler.setFormatter(StructuredFormatter())
        else:
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
        root_logger.addHandler(handler)
    else:
        root_logger.setLevel(numeric_level)
