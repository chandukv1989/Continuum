"""Code reference resolver for Project Brain.

Resolves soft symbol references (sym://<relative_path>#<qualified_name>?kind=<kind>)
against the deterministic Code Brain SQLite repository without relying on database primary keys.
"""
from typing import Optional

from backend.app.code_brain.repository import CodeBrainRepository
from backend.app.project_brain.contracts import (
    CodeReferenceResolution,
    CodeSymbolRef,
    ReferenceResolutionStatus,
)


class CodeReferenceResolver:
    """Resolves soft CodeSymbolRef URIs against the Code Brain repository."""

    def __init__(self, code_brain_repo: CodeBrainRepository) -> None:
        self.repo = code_brain_repo

    def resolve(self, ref_or_uri: CodeSymbolRef | str) -> CodeReferenceResolution:
        """Resolve a CodeSymbolRef or URI string against Code Brain facts."""
        if isinstance(ref_or_uri, str):
            ref = CodeSymbolRef.from_uri(ref_or_uri)
        else:
            ref = ref_or_uri

        # 1. Look for symbols in the target file
        file_symbols = self.repo.get_symbols(file_path=ref.file_path)
        matching_in_file = [
            s
            for s in file_symbols
            if s.get("qualified_name") == ref.qualified_name
            or s.get("name") == ref.qualified_name
            or (s.get("qualified_name") or "").endswith(f".{ref.qualified_name}")
        ]

        if matching_in_file:
            # Check kind if specified
            if ref.kind:
                kind_matched = [s for s in matching_in_file if s.get("kind") == ref.kind]
                if kind_matched:
                    return CodeReferenceResolution(
                        ref=ref,
                        status=ReferenceResolutionStatus.RESOLVED,
                        resolved_symbol_id=kind_matched[0]["id"],
                        details="Symbol resolved with matching path, qualified name, and kind",
                    )
            return CodeReferenceResolution(
                ref=ref,
                status=ReferenceResolutionStatus.RESOLVED,
                resolved_symbol_id=matching_in_file[0]["id"],
                details="Symbol resolved with matching path and qualified name",
            )

        # 2. Check if the symbol moved to another file
        conn = self.repo.db.get_connection()
        query = """
            SELECT id, file_path, kind FROM symbols
            WHERE qualified_name = ? OR name = ? OR qualified_name LIKE ?
            LIMIT 1;
        """
        row = conn.execute(
            query,
            (ref.qualified_name, ref.qualified_name, f"%.{ref.qualified_name}"),
        ).fetchone()
        if row:
            return CodeReferenceResolution(
                ref=ref,
                status=ReferenceResolutionStatus.STALE,
                resolved_symbol_id=row["id"],
                moved_to_path=row["file_path"],
                details=f"Symbol relocated from {ref.file_path} to {row['file_path']}",
            )



        # 3. Not found in Code Brain
        return CodeReferenceResolution(
            ref=ref,
            status=ReferenceResolutionStatus.UNRESOLVED,
            details=f"Symbol {ref.qualified_name} not found in Code Brain",
        )

