"""Project Brain repository managing semantic project artifacts.

Enforces:
- Strict artifact governance (HUMAN_AUTHORED immutability against automated overwrites)
- Markdown + YAML frontmatter file loading, validation, and serialization
- In-memory index and lookup for architecture, features, concepts, conventions, decisions, and metadata
- Discrepancy / conflict tracking
"""
from pathlib import Path
from typing import Dict, List, Optional
import yaml

from backend.app.core.exceptions import GovernanceViolationException, ProjectBrainException
from backend.app.core.logging import get_logger
from backend.app.project_brain.contracts import (
    ArchitectureEntity,
    ArtifactOwnership,
    ConceptEntity,
    ConventionEntity,
    DecisionEntity,
    DiscrepancyEntity,
    DiscrepancyStatus,
    FeatureEntity,
    ProjectMetadata,
)
from backend.app.project_brain.storage import (
    ProjectBrainStorage,
    dump_frontmatter_markdown,
    parse_frontmatter_markdown,
)

logger = get_logger("continuum.project_brain")


class ProjectBrainRepository:
    """Repository managing reading, writing, and querying .continuum/ semantic artifacts."""

    def __init__(self, root_dir: Path) -> None:
        self.storage = ProjectBrainStorage(root_dir)
        self.storage.ensure_directories()

    # --------------------------------------------------------------------------
    # Project Metadata
    # --------------------------------------------------------------------------

    def get_metadata(self) -> Optional[ProjectMetadata]:
        """Read and parse project.md."""
        target = self.storage.project_file
        if not target.exists():
            return None
        raw = self.storage.read_file(target)
        meta, body = parse_frontmatter_markdown(raw)
        if not meta:
            return None
        if body and "description" not in meta:
            meta["description"] = body
        return ProjectMetadata(**meta)

    def save_metadata(self, metadata: ProjectMetadata, automated: bool = False) -> None:
        """Save project metadata respecting governance."""
        existing = self.get_metadata()
        if existing and existing.ownership == ArtifactOwnership.HUMAN_AUTHORED and automated:
            raise GovernanceViolationException(
                f"Automated overwrite rejected: Project metadata is {existing.ownership.value}"
            )
        data = metadata.model_dump(mode="json")
        content = dump_frontmatter_markdown(data, f"# {metadata.name}\n\n{metadata.description}")
        self.storage.write_file(self.storage.project_file, content)

    # --------------------------------------------------------------------------
    # Architecture
    # --------------------------------------------------------------------------

    def get_architecture(self, entity_id: str) -> Optional[ArchitectureEntity]:
        """Load an architecture artifact by ID."""
        for path in self.storage.architecture_dir.glob("*.md"):
            raw = self.storage.read_file(path)
            meta, body = parse_frontmatter_markdown(raw)
            if meta.get("id") == entity_id:
                if body and "overview" not in meta:
                    meta["overview"] = body
                return ArchitectureEntity(**meta)
        return None

    def list_architecture(self) -> List[ArchitectureEntity]:
        """List all architecture artifacts."""
        entities = []
        for path in self.storage.architecture_dir.glob("*.md"):
            raw = self.storage.read_file(path)
            meta, body = parse_frontmatter_markdown(raw)
            if meta:
                if body and "overview" not in meta:
                    meta["overview"] = body
                entities.append(ArchitectureEntity(**meta))
        return entities

    def save_architecture(self, entity: ArchitectureEntity, automated: bool = False) -> None:
        """Save an architecture artifact enforcing governance rules."""
        existing = self.get_architecture(entity.id)
        if existing and existing.ownership == ArtifactOwnership.HUMAN_AUTHORED and automated:
            raise GovernanceViolationException(
                f"Automated overwrite rejected: Architecture {entity.id} is {existing.ownership.value}"
            )
        filename = f"{entity.id.replace('arch:', '')}.md"
        target_path = self.storage.architecture_dir / filename
        data = entity.model_dump(mode="json")
        content = dump_frontmatter_markdown(data, f"# {entity.title}\n\n{entity.overview}")
        self.storage.write_file(target_path, content)

    # --------------------------------------------------------------------------
    # Features
    # --------------------------------------------------------------------------

    def get_feature(self, feature_id: str) -> Optional[FeatureEntity]:
        """Load a feature artifact by ID."""
        for path in self.storage.features_dir.glob("*.md"):
            raw = self.storage.read_file(path)
            meta, body = parse_frontmatter_markdown(raw)
            if meta.get("id") == feature_id:
                if body and "description" not in meta:
                    meta["description"] = body
                return FeatureEntity(**meta)
        return None

    def list_features(self) -> List[FeatureEntity]:
        """List all features."""
        features = []
        for path in self.storage.features_dir.glob("*.md"):
            raw = self.storage.read_file(path)
            meta, body = parse_frontmatter_markdown(raw)
            if meta:
                if body and "description" not in meta:
                    meta["description"] = body
                features.append(FeatureEntity(**meta))
        return features

    def save_feature(self, feature: FeatureEntity, automated: bool = False) -> None:
        """Save a feature artifact enforcing governance."""
        existing = self.get_feature(feature.id)
        if existing and existing.ownership == ArtifactOwnership.HUMAN_AUTHORED and automated:
            raise GovernanceViolationException(
                f"Automated overwrite rejected: Feature {feature.id} is {existing.ownership.value}"
            )
        filename = f"{feature.id.replace('feat:', '')}.md"
        target_path = self.storage.features_dir / filename
        data = feature.model_dump(mode="json")
        content = dump_frontmatter_markdown(data, f"# {feature.name}\n\n{feature.description}")
        self.storage.write_file(target_path, content)

    # --------------------------------------------------------------------------
    # Concepts
    # --------------------------------------------------------------------------

    def get_concept(self, concept_id: str) -> Optional[ConceptEntity]:
        """Load a domain concept artifact by ID."""
        for path in self.storage.concepts_dir.glob("*.md"):
            raw = self.storage.read_file(path)
            meta, body = parse_frontmatter_markdown(raw)
            if meta.get("id") == concept_id:
                if body and "description" not in meta:
                    meta["description"] = body
                return ConceptEntity(**meta)
        return None

    def list_concepts(self) -> List[ConceptEntity]:
        """List all concepts."""
        concepts = []
        for path in self.storage.concepts_dir.glob("*.md"):
            raw = self.storage.read_file(path)
            meta, body = parse_frontmatter_markdown(raw)
            if meta:
                if body and "description" not in meta:
                    meta["description"] = body
                concepts.append(ConceptEntity(**meta))
        return concepts

    def save_concept(self, concept: ConceptEntity, automated: bool = False) -> None:
        """Save a concept artifact enforcing governance."""
        existing = self.get_concept(concept.id)
        if existing and existing.ownership == ArtifactOwnership.HUMAN_AUTHORED and automated:
            raise GovernanceViolationException(
                f"Automated overwrite rejected: Concept {concept.id} is {existing.ownership.value}"
            )
        filename = f"{concept.id.replace('concept:', '')}.md"
        target_path = self.storage.concepts_dir / filename
        data = concept.model_dump(mode="json")
        content = dump_frontmatter_markdown(data, f"# {concept.name}\n\n{concept.description}")
        self.storage.write_file(target_path, content)

    # --------------------------------------------------------------------------
    # Conventions
    # --------------------------------------------------------------------------

    def get_convention(self, convention_id: str) -> Optional[ConventionEntity]:
        """Load a convention artifact by ID."""
        for path in self.storage.conventions_dir.glob("*.md"):
            raw = self.storage.read_file(path)
            meta, body = parse_frontmatter_markdown(raw)
            if meta.get("id") == convention_id:
                if body and "rule" not in meta:
                    meta["rule"] = body
                return ConventionEntity(**meta)
        return None

    def list_conventions(self) -> List[ConventionEntity]:
        """List all conventions."""
        conventions = []
        for path in self.storage.conventions_dir.glob("*.md"):
            raw = self.storage.read_file(path)
            meta, body = parse_frontmatter_markdown(raw)
            if meta:
                if body and "rule" not in meta:
                    meta["rule"] = body
                conventions.append(ConventionEntity(**meta))
        return conventions

    def save_convention(self, convention: ConventionEntity, automated: bool = False) -> None:
        """Save a convention artifact enforcing governance."""
        existing = self.get_convention(convention.id)
        if existing and existing.ownership == ArtifactOwnership.HUMAN_AUTHORED and automated:
            raise GovernanceViolationException(
                f"Automated overwrite rejected: Convention {convention.id} is {existing.ownership.value}"
            )
        filename = f"{convention.id.replace('conv:', '')}.md"
        target_path = self.storage.conventions_dir / filename
        data = convention.model_dump(mode="json")
        content = dump_frontmatter_markdown(data, f"# {convention.title}\n\n{convention.rule}")
        self.storage.write_file(target_path, content)

    # --------------------------------------------------------------------------
    # Decisions (ADRs)
    # --------------------------------------------------------------------------

    def get_decision(self, decision_id: str) -> Optional[DecisionEntity]:
        """Load an architectural decision record (ADR) by ID."""
        for path in self.storage.decisions_dir.glob("*.md"):
            raw = self.storage.read_file(path)
            meta, body = parse_frontmatter_markdown(raw)
            if meta.get("id") == decision_id:
                return DecisionEntity(**meta)
        return None

    def list_decisions(self) -> List[DecisionEntity]:
        """List all ADRs."""
        decisions = []
        for path in self.storage.decisions_dir.glob("*.md"):
            raw = self.storage.read_file(path)
            meta, body = parse_frontmatter_markdown(raw)
            if meta:
                decisions.append(DecisionEntity(**meta))
        return decisions

    def save_decision(self, decision: DecisionEntity, automated: bool = False) -> None:
        """Save an ADR enforcing governance."""
        existing = self.get_decision(decision.id)
        if existing and existing.ownership == ArtifactOwnership.HUMAN_AUTHORED and automated:
            raise GovernanceViolationException(
                f"Automated overwrite rejected: Decision {decision.id} is {existing.ownership.value}"
            )
        filename = f"{decision.id}.md"
        target_path = self.storage.decisions_dir / filename
        data = decision.model_dump(mode="json")
        body = (
            f"# {decision.title}\n\n"
            f"## Context\n{decision.context}\n\n"
            f"## Decision\n{decision.decision}\n\n"
            f"## Consequences\n{decision.consequences}"
        )
        content = dump_frontmatter_markdown(data, body)
        self.storage.write_file(target_path, content)


    # --------------------------------------------------------------------------
    # Discrepancies / Conflicts
    # --------------------------------------------------------------------------

    def list_discrepancies(self, status: Optional[DiscrepancyStatus] = None) -> List[DiscrepancyEntity]:
        """List all conflict/discrepancy records, optionally filtered by status."""
        if not self.storage.discrepancies_file.exists():
            return []
        raw = self.storage.read_file(self.storage.discrepancies_file)
        try:
            items = yaml.safe_load(raw) or []
            discrepancies = [DiscrepancyEntity(**item) for item in items]
            if status is not None:
                return [d for d in discrepancies if d.status == status]
            return discrepancies
        except Exception:
            return []

    def record_discrepancy(self, discrepancy: DiscrepancyEntity) -> None:
        """Record an observed conflict between human knowledge and automated evidence."""
        discrepancies = self.list_discrepancies()
        # Avoid duplicate active discrepancies for same entity and observation
        for d in discrepancies:
            if d.entity_id == discrepancy.entity_id and d.status == DiscrepancyStatus.OPEN:
                if d.conflicting_evidence == discrepancy.conflicting_evidence:
                    return
        discrepancies.append(discrepancy)
        data = [d.model_dump(mode="json") for d in discrepancies]
        raw_yaml = yaml.safe_dump(data, sort_keys=False)
        self.storage.write_file(self.storage.discrepancies_file, raw_yaml)
