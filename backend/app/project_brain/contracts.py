"""Project Brain domain contracts and typed schemas for Continuum.

Establishes:
- Artifact Governance: HUMAN_AUTHORED, DERIVED, GENERATED, HYBRID
- Provenance tracking: Source lineage without arbitrary confidence scores
- Evidence hierarchy: CONFIRMED, INFERRED, UNBOUND, PROPOSED
- Soft Code Brain references: sym:// URI contract with resolution states
- Core semantic entities: Project Metadata, Architecture, Features, Concepts, Conventions, Decisions (ADRs)
- Conflict / Discrepancy tracking
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse
from pydantic import BaseModel, Field


class ArtifactOwnership(str, Enum):
    """Ownership and governance classification for Project Brain artifacts."""

    HUMAN_AUTHORED = "HUMAN_AUTHORED"  # Never overwritten or deleted by automation
    DERIVED = "DERIVED"                # Derived deterministically from project facts; regenerable
    GENERATED = "GENERATED"            # Machine-generated; fully regenerable
    HYBRID = "HYBRID"                  # Machine-suggested with human modifications/approvals


class ProvenanceSource(str, Enum):
    """Authoritative source category for project knowledge."""

    SOURCE_CODE = "SOURCE_CODE"
    CODE_BRAIN = "CODE_BRAIN"
    GIT = "GIT"
    DOCUMENTATION = "DOCUMENTATION"
    DEVELOPER = "DEVELOPER"
    IMPORTED = "IMPORTED"
    LLM_ASSISTED = "LLM_ASSISTED"


class EvidenceState(str, Enum):
    """Discrete evidence validation state."""

    CONFIRMED = "CONFIRMED"  # Directly verified by structural fact or human authoring
    INFERRED = "INFERRED"    # Inferred from multi-file patterns or heuristics
    UNBOUND = "UNBOUND"      # Reference target currently missing or deleted
    PROPOSED = "PROPOSED"    # Proposed knowledge pending human review


class ReferenceResolutionStatus(str, Enum):
    """Resolution state of a soft Code Brain reference."""

    RESOLVED = "RESOLVED"      # Symbol exists at exact path with matching signature
    UNRESOLVED = "UNRESOLVED"  # Symbol cannot be located in Code Brain
    STALE = "STALE"            # Symbol moved or modified


class DecisionStatus(str, Enum):
    """Status lifecycle for architectural decisions (ADRs)."""

    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


class DiscrepancyStatus(str, Enum):
    """Resolution status of a conflict between human knowledge and automated evidence."""

    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class Provenance(BaseModel):
    """Lineage and provenance metadata for a Project Brain entity."""

    source: ProvenanceSource = Field(..., description="Authoritative origin of this knowledge")
    source_ref: Optional[str] = Field(default=None, description="Specific reference identifier or file location")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 last update timestamp")
    author: Optional[str] = Field(default=None, description="Human or tool actor responsible for this fact")


class CodeSymbolRef(BaseModel):
    """Decoupled soft reference locating a Code Brain symbol by relative path, qualified name, and kind.
    
    Syntax: sym://<relative_path>#<qualified_name>?kind=<kind>
    Example: sym://backend/app/scanner/repository.py#RepositoryScanner?kind=class
    """

    file_path: str = Field(..., description="POSIX relative path from workspace root")
    qualified_name: str = Field(..., description="Language-level qualified symbol identifier")
    kind: Optional[str] = Field(default=None, description="Optional symbol kind hint (e.g. class, function)")

    def to_uri(self) -> str:
        """Serialize reference to canonical URI string."""
        base = f"sym://{self.file_path}#{self.qualified_name}"
        if self.kind:
            query = urlencode({"kind": self.kind})
            return f"{base}?{query}"
        return base

    @classmethod
    def from_uri(cls, uri: str) -> "CodeSymbolRef":
        """Parse canonical URI into a typed CodeSymbolRef."""
        if not uri.startswith("sym://"):
            raise ValueError(f"Invalid CodeSymbolRef URI scheme (must start with 'sym://'): {uri}")

        raw = uri[len("sym://"):]
        
        # Split fragment
        if "#" in raw:
            path_part, rest = raw.split("#", 1)
        else:
            path_part = raw
            rest = ""

        # Split query
        kind = None
        if "?" in rest:
            qualified_name, query_str = rest.split("?", 1)
            params = parse_qs(query_str)
            if "kind" in params and params["kind"]:
                kind = params["kind"][0]
        else:
            qualified_name = rest

        if not path_part:
            raise ValueError(f"CodeSymbolRef URI missing file path: {uri}")
        if not qualified_name:
            raise ValueError(f"CodeSymbolRef URI missing qualified name: {uri}")

        return cls(file_path=path_part, qualified_name=qualified_name, kind=kind)


class CodeReferenceResolution(BaseModel):
    """Result of resolving a CodeSymbolRef against Code Brain."""

    ref: CodeSymbolRef
    status: ReferenceResolutionStatus
    resolved_symbol_id: Optional[str] = None
    moved_to_path: Optional[str] = None
    details: Optional[str] = None


class ProjectMetadata(BaseModel):
    """Project-level identity and configuration stored in .continuum/project.md."""

    project_id: str = Field(..., description="Stable 3-tier Continuum project identity hash")
    name: str = Field(..., description="Human-readable project name")
    description: str = Field(default="", description="High-level project purpose")
    repository_root: str = Field(..., description="Canonical POSIX root path of the project")
    schema_version: str = Field(default="3.0.0", description="Project Brain schema version")
    created_at: str = Field(..., description="Creation ISO timestamp")
    updated_at: str = Field(..., description="Last updated ISO timestamp")
    tech_stack_refs: List[str] = Field(default_factory=list, description="IDs of technology concepts used (e.g. tech:fastapi)")
    ownership: ArtifactOwnership = Field(default=ArtifactOwnership.DERIVED)
    evidence: EvidenceState = Field(default=EvidenceState.CONFIRMED)
    provenance: Provenance


class ArchitectureEntity(BaseModel):
    """Architectural layer or structural boundary definition."""

    id: str = Field(..., description="Unique architecture entity ID, e.g. arch:backend-api")
    title: str = Field(..., description="Layer or component title")
    layer: str = Field(..., description="Structural tier (e.g. Presentation, Domain, Infrastructure)")
    overview: str = Field(default="", description="Architectural overview and responsibilities")
    boundaries: List[str] = Field(default_factory=list, description="Architectural constraints and boundary rules")
    code_refs: List[str] = Field(default_factory=list, description="Associated CodeSymbolRef URIs")
    tech_refs: List[str] = Field(default_factory=list, description="Associated Technology Brain IDs")
    ownership: ArtifactOwnership = Field(default=ArtifactOwnership.HUMAN_AUTHORED)
    evidence: EvidenceState = Field(default=EvidenceState.CONFIRMED)
    provenance: Provenance


class FeatureEntity(BaseModel):
    """Project-level functional feature or user journey."""

    id: str = Field(..., description="Unique feature ID, e.g. feat:scanner-pipeline")
    name: str = Field(..., description="Feature name")
    description: str = Field(default="", description="Functional feature description")
    aliases: List[str] = Field(default_factory=list, description="Alternative names or search aliases")
    code_refs: List[str] = Field(default_factory=list, description="Associated CodeSymbolRef URIs")
    tech_refs: List[str] = Field(default_factory=list, description="Associated Technology Brain IDs")
    related_decision_ids: List[str] = Field(default_factory=list, description="Related ADR IDs")
    related_concept_ids: List[str] = Field(default_factory=list, description="Related Concept IDs")
    ownership: ArtifactOwnership = Field(default=ArtifactOwnership.HUMAN_AUTHORED)
    evidence: EvidenceState = Field(default=EvidenceState.CONFIRMED)
    provenance: Provenance


class ConceptEntity(BaseModel):
    """Domain concept or semantic model unique to this project."""

    id: str = Field(..., description="Unique concept ID, e.g. concept:stable-identity")
    name: str = Field(..., description="Concept name")
    description: str = Field(default="", description="Semantic definition of the concept")
    code_refs: List[str] = Field(default_factory=list, description="Associated CodeSymbolRef URIs")
    tech_refs: List[str] = Field(default_factory=list, description="Associated Technology Brain IDs")
    related_feature_ids: List[str] = Field(default_factory=list, description="Related Feature IDs")
    ownership: ArtifactOwnership = Field(default=ArtifactOwnership.HUMAN_AUTHORED)
    evidence: EvidenceState = Field(default=EvidenceState.CONFIRMED)
    provenance: Provenance


class ConventionEntity(BaseModel):
    """Project-specific coding or architectural convention."""

    id: str = Field(..., description="Unique convention ID, e.g. conv:error-handling")
    title: str = Field(..., description="Convention title")
    rule: str = Field(..., description="Explicit convention statement/rule")
    category: str = Field(..., description="Category (e.g. naming, error_handling, testing, structure)")
    code_refs: List[str] = Field(default_factory=list, description="Supporting CodeSymbolRef URIs")
    ownership: ArtifactOwnership = Field(default=ArtifactOwnership.HUMAN_AUTHORED)
    evidence: EvidenceState = Field(default=EvidenceState.CONFIRMED)
    provenance: Provenance


class DecisionEntity(BaseModel):
    """Architectural Decision Record (ADR)."""

    id: str = Field(..., description="ADR identifier, e.g. ADR-0001")
    title: str = Field(..., description="Decision title")
    status: DecisionStatus = Field(default=DecisionStatus.ACCEPTED, description="Lifecycle status")
    context: str = Field(default="", description="Context and problem statement")
    decision: str = Field(default="", description="The decision made")
    consequences: str = Field(default="", description="Trade-offs, positive and negative consequences")
    code_refs: List[str] = Field(default_factory=list, description="Impacted or implementing CodeSymbolRef URIs")
    related_feature_ids: List[str] = Field(default_factory=list, description="Related Feature IDs")
    date: str = Field(..., description="Decision date (YYYY-MM-DD)")
    ownership: ArtifactOwnership = Field(default=ArtifactOwnership.HUMAN_AUTHORED)
    evidence: EvidenceState = Field(default=EvidenceState.CONFIRMED)
    provenance: Provenance


class DiscrepancyEntity(BaseModel):
    """Audit record capturing a conflict between human knowledge and automated evidence without mutating human facts."""

    id: str = Field(..., description="Discrepancy record ID")
    entity_id: str = Field(..., description="ID of the Project Brain entity in conflict")
    entity_type: str = Field(..., description="Type of the entity (e.g. decision, convention, feature)")
    human_statement: str = Field(..., description="Recorded human-authored statement or assertion")
    conflicting_evidence: str = Field(..., description="Conflicting observation discovered by scanner or analysis")
    detected_at: str = Field(..., description="Detection timestamp")
    status: DiscrepancyStatus = Field(default=DiscrepancyStatus.OPEN)
