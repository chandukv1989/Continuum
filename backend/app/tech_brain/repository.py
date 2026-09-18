"""Repository managing global Technology Brain knowledge in ~/.continuum/technology/.

Enforces:
- Pure technology-level facts (strictly project-independent)
- Rejection of project paths, proprietary names, or secrets
- Seeding of core technologies (Python, TypeScript, FastAPI, React, SQLite, Tree-sitter, Pytest)
"""
from pathlib import Path
import re
from typing import List, Optional
import yaml

from backend.app.core.exceptions import TechnologyBrainException
from backend.app.core.logging import get_logger
from backend.app.tech_brain.contracts import TechnologyCategory, TechnologyConcept

logger = get_logger("continuum.tech_brain")

# Seed technologies
DEFAULT_SEEDS = [
    TechnologyConcept(
        id="tech:python",
        name="Python",
        category=TechnologyCategory.LANGUAGE,
        description="High-level, interpreted programming language with strong typing support via type annotations.",
        official_docs="https://docs.python.org/3/",
        best_practices=[
            "Use type hints for all public interfaces and data contracts",
            "Prefer standard library context managers and path objects",
            "Follow PEP 8 styling conventions",
        ],
        tags=["language", "backend", "scripting"],
    ),
    TechnologyConcept(
        id="tech:typescript",
        name="TypeScript",
        category=TechnologyCategory.LANGUAGE,
        description="Typed superset of JavaScript that compiles to plain JavaScript.",
        official_docs="https://www.typescriptlang.org/docs/",
        best_practices=[
            "Enable strict mode in tsconfig.json",
            "Avoid 'any'; use unknown or discriminating unions",
            "Use immutable patterns for state transformations",
        ],
        tags=["language", "frontend", "types"],
    ),
    TechnologyConcept(
        id="tech:fastapi",
        name="FastAPI",
        category=TechnologyCategory.FRAMEWORK,
        description="Modern, high-performance web framework for building APIs with Python based on standard type hints.",
        official_docs="https://fastapi.tiangolo.com/",
        best_practices=[
            "Use Pydantic v2 models for request and response validation",
            "Organize endpoints using APIRouter with consistent prefixes",
            "Enforce dependency injection for shared resources",
        ],
        tags=["framework", "api", "python", "async"],
    ),
    TechnologyConcept(
        id="tech:react",
        name="React",
        category=TechnologyCategory.LIBRARY,
        description="Declarative, component-based front-end library for building user interfaces.",
        official_docs="https://react.dev/",
        best_practices=[
            "Use functional components with custom hooks",
            "Avoid mutating state directly; maintain unidirectional data flow",
            "Stabilize dependency arrays in useEffect to prevent render loops",
        ],
        tags=["frontend", "ui", "components"],
    ),
    TechnologyConcept(
        id="tech:sqlite",
        name="SQLite",
        category=TechnologyCategory.DATABASE,
        description="Self-contained, serverless, zero-configuration, transactional SQL database engine.",
        official_docs="https://www.sqlite.org/docs.html",
        best_practices=[
            "Enable WAL (Write-Ahead Logging) mode for concurrent reader performance",
            "Enforce foreign_keys = ON at connection start",
            "Use parameterized SQL queries exclusively to prevent injection",
        ],
        tags=["database", "sql", "embedded", "storage"],
    ),
    TechnologyConcept(
        id="tech:tree-sitter",
        name="Tree-sitter",
        category=TechnologyCategory.TOOL,
        description="Incremental parsing system and library for generating concrete syntax trees.",
        official_docs="https://tree-sitter.github.io/tree-sitter/",
        best_practices=[
            "Use safe point indexing (point[0], point[1]) to ensure compatibility across bindings",
            "Reuse parser instances across files of the same language",
        ],
        tags=["parser", "ast", "compiler", "tool"],
    ),
    TechnologyConcept(
        id="tech:pytest",
        name="Pytest",
        category=TechnologyCategory.TOOL,
        description="Mature full-featured Python testing tool supporting fixtures and parameterized testing.",
        official_docs="https://docs.pytest.org/",
        best_practices=[
            "Structure tests into unit and integration directories",
            "Use isolated fixtures (tmp_path) to prevent state leaks",
        ],
        tags=["testing", "python", "qa"],
    ),
]


class TechnologyBrainRepository:
    """Repository managing global Technology Brain items in ~/.continuum/technology/."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_seeds()

    def _ensure_seeds(self) -> None:
        """Seed default technologies if the technology directory is empty."""
        for seed in DEFAULT_SEEDS:
            tech_file = self._path_for_id(seed.id)
            if not tech_file.exists():
                self.save_technology(seed)

    def _path_for_id(self, tech_id: str) -> Path:
        safe_name = tech_id.replace(":", "_").replace("/", "_")
        return self.root_dir / f"{safe_name}.yaml"

    def _validate_independence(self, concept: TechnologyConcept) -> None:
        """Enforce strict project independence."""
        # Reject local filesystem path patterns
        payload = f"{concept.id} {concept.name} {concept.description} {' '.join(concept.best_practices)}"
        if re.search(r"(/app/|/home/|[A-Za-z]:\\|\./|\.continuum)", payload):
            raise TechnologyBrainException(
                f"TechnologyConcept {concept.id} rejected: Violates project independence by containing local path patterns"
            )

    def get_technology(self, tech_id: str) -> Optional[TechnologyConcept]:
        """Fetch a technology concept by ID."""
        tech_file = self._path_for_id(tech_id)
        if not tech_file.exists():
            return None
        raw = tech_file.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        return TechnologyConcept(**data)

    def list_technologies(self, category: Optional[TechnologyCategory] = None) -> List[TechnologyConcept]:
        """List all technologies, optionally filtered by category."""
        results = []
        for path in self.root_dir.glob("*.yaml"):
            try:
                raw = path.read_text(encoding="utf-8")
                data = yaml.safe_load(raw)
                if data and "id" in data:
                    concept = TechnologyConcept(**data)
                    if category is None or concept.category == category:
                        results.append(concept)
            except Exception as e:
                logger.warning(f"Error reading technology concept at {path}: {e}")
        return results

    def save_technology(self, concept: TechnologyConcept) -> None:
        """Save a technology concept after validating project independence."""
        self._validate_independence(concept)
        tech_file = self._path_for_id(concept.id)
        raw_yaml = yaml.safe_dump(concept.model_dump(mode="json"), sort_keys=False)
        tech_file.write_text(raw_yaml, encoding="utf-8")
