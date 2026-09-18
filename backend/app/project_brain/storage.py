"""Storage engine for Project Brain markdown artifacts with YAML frontmatter.

Enforces:
- Git-trackable, human-readable format (Markdown + YAML frontmatter)
- Strong typed serialization and deserialization
- Content security sanitization (forbidding API keys, private tokens, passwords, and sensitive credentials)
- Preservation of human markdown body and comments
"""
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import yaml

from backend.app.core.exceptions import ProjectBrainException
from backend.app.project_brain.contracts import (
    ArchitectureEntity,
    ConceptEntity,
    ConventionEntity,
    DecisionEntity,
    DiscrepancyEntity,
    FeatureEntity,
    ProjectMetadata,
)

# Sensitive patterns that must never be committed to .continuum/
SECRET_PATTERNS = [
    re.compile(r"(?:api_key|apikey|secret|password|passwd|token|private_key)\s*[:=]\s*['\"][a-zA-Z0-9_\-\.]{8,}['\"]", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"sk-[a-zA-Z0-9]{32,}"),
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
]


def sanitize_content(content: str) -> None:
    """Scan content for sensitive tokens or credentials; raise exception if detected."""
    for pattern in SECRET_PATTERNS:
        if pattern.search(content):
            raise ProjectBrainException(
                "Content rejected: Detected sensitive credentials or secret pattern",
                details={"pattern": pattern.pattern},
            )


def parse_frontmatter_markdown(raw_text: str) -> Tuple[Dict[str, Any], str]:
    """Parse a Markdown document with YAML frontmatter into (metadata_dict, body_text)."""
    if not raw_text.startswith("---"):
        return {}, raw_text.strip()

    parts = raw_text.split("---", 2)
    if len(parts) < 3:
        return {}, raw_text.strip()

    frontmatter_raw = parts[1].strip()
    body_raw = parts[2].strip()

    if not frontmatter_raw:
        metadata = {}
    else:
        try:
            metadata = yaml.safe_load(frontmatter_raw) or {}
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception as e:
            raise ProjectBrainException(f"Invalid YAML frontmatter: {e}") from e

    return metadata, body_raw


def dump_frontmatter_markdown(metadata: Dict[str, Any], body: str) -> str:
    """Serialize metadata dict and body into a Markdown document with YAML frontmatter."""
    yaml_str = yaml.safe_dump(metadata, sort_keys=False, default_flow_style=False).strip()
    clean_body = body.strip()
    if clean_body:
        full_text = f"---\n{yaml_str}\n---\n\n{clean_body}\n"
    else:
        full_text = f"---\n{yaml_str}\n---\n"

    sanitize_content(full_text)
    return full_text


class ProjectBrainStorage:
    """Filesystem driver managing the <repo>/.continuum directory tree."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.architecture_dir = self.root_dir / "architecture"
        self.features_dir = self.root_dir / "features"
        self.concepts_dir = self.root_dir / "concepts"
        self.conventions_dir = self.root_dir / "conventions"
        self.decisions_dir = self.root_dir / "decisions"
        self.discrepancies_file = self.root_dir / "discrepancies.yaml"
        self.project_file = self.root_dir / "project.md"

    def ensure_directories(self) -> None:
        """Create standard Project Brain directories idempotently."""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.architecture_dir.mkdir(parents=True, exist_ok=True)
        self.features_dir.mkdir(parents=True, exist_ok=True)
        self.concepts_dir.mkdir(parents=True, exist_ok=True)
        self.conventions_dir.mkdir(parents=True, exist_ok=True)
        self.decisions_dir.mkdir(parents=True, exist_ok=True)

    def write_file(self, target_path: Path, content: str) -> None:
        """Safely write content to target path ensuring parent directories exist."""
        sanitize_content(content)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")

    def read_file(self, target_path: Path) -> str:
        """Read content from target path."""
        if not target_path.exists():
            raise ProjectBrainException(f"Project Brain file not found: {target_path}")
        return target_path.read_text(encoding="utf-8")
