"""Technology Brain domain contracts and typed schemas for Continuum.

Universal, reusable technology knowledge (frameworks, languages, patterns, best practices).
Strictly project-independent with no local project file paths or proprietary code logic.
"""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class TechnologyCategory(str, Enum):
    """Categorization of universal technology knowledge."""

    LANGUAGE = "LANGUAGE"
    FRAMEWORK = "FRAMEWORK"
    LIBRARY = "LIBRARY"
    DATABASE = "DATABASE"
    TOOL = "TOOL"
    PATTERN = "PATTERN"
    ARCHITECTURE = "ARCHITECTURE"


class TechnologyConcept(BaseModel):
    """Universal, reusable technology knowledge model."""

    id: str = Field(..., description="Stable technology identifier, e.g. tech:fastapi")
    name: str = Field(..., description="Canonical name of technology or pattern")
    category: TechnologyCategory = Field(..., description="Category classification")
    description: str = Field(..., description="Universal explanation of role and capabilities")
    official_docs: Optional[str] = Field(default=None, description="URL to official reference documentation")
    best_practices: List[str] = Field(default_factory=list, description="Recommended architectural patterns and idioms")
    tags: List[str] = Field(default_factory=list, description="Search and classification tags")
    schema_version: str = Field(default="1.0.0", description="Schema version")
