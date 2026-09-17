"""Unit tests for Continuum Scanner recursive file discovery."""
import os
from pathlib import Path
import pytest

from backend.app.core.exceptions import ScannerException
from backend.app.scanner.contracts import FileFilterStatus, Language
from backend.app.scanner.discovery import FileDiscovery, compute_content_hash
from backend.app.scanner.filtering import FileFilter


def test_discovery_basic(tmp_path: Path):
    """Verify recursive file discovery and categorization."""
    workspace = tmp_path / "project"
    workspace.mkdir()

    # Source files
    (workspace / "src").mkdir()
    (workspace / "src" / "index.ts").write_text("export const a = 1;", encoding="utf-8")
    (workspace / "main.py").write_text("print('hello')", encoding="utf-8")

    # Ignored directory
    (workspace / "node_modules" / "dep").mkdir(parents=True)
    (workspace / "node_modules" / "dep" / "index.js").write_text("bad", encoding="utf-8")

    # Unsupported file
    (workspace / "README.md").write_text("# Project", encoding="utf-8")

    discovery = FileDiscovery(workspace_root=workspace)
    discovered = discovery.discover()

    rel_paths = {d.relative_path: d for d in discovered}

    # node_modules should be pruned early and not present in discovered files
    assert "node_modules/dep/index.js" not in rel_paths

    assert "main.py" in rel_paths
    assert rel_paths["main.py"].status == FileFilterStatus.PARSEABLE
    assert rel_paths["main.py"].language == Language.PYTHON
    assert rel_paths["main.py"].content_hash is not None

    assert "src/index.ts" in rel_paths
    assert rel_paths["src/index.ts"].status == FileFilterStatus.PARSEABLE
    assert rel_paths["src/index.ts"].language == Language.TYPESCRIPT

    assert "README.md" in rel_paths
    assert rel_paths["README.md"].status == FileFilterStatus.UNSUPPORTED


def test_discovery_content_hash(tmp_path: Path):
    """Verify deterministic content hashing."""
    test_file = tmp_path / "test.py"
    test_file.write_text("def test(): pass\n", encoding="utf-8")

    hash1 = compute_content_hash(test_file)
    hash2 = compute_content_hash(test_file)
    assert hash1 == hash2
    assert len(hash1) == 64


def test_discovery_symlink_boundary(tmp_path: Path):
    """Verify symlink pointing outside workspace root is categorized as OUTSIDE_WORKSPACE."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside_file = tmp_path / "secret.py"
    outside_file.write_text("secret_data = True", encoding="utf-8")

    # Create symlink inside workspace pointing outside
    symlink_file = workspace / "linked_secret.py"
    try:
        symlink_file.symlink_to(outside_file)
    except OSError:
        pytest.skip("Symlinks not supported on filesystem")

    discovery = FileDiscovery(workspace_root=workspace)
    discovered = discovery.discover()

    linked = next((d for d in discovered if "linked_secret.py" in d.relative_path), None)
    assert linked is not None
    assert linked.status == FileFilterStatus.OUTSIDE_WORKSPACE


def test_discovery_invalid_root(tmp_path: Path):
    """Verify ScannerException when workspace root does not exist."""
    nonexistent = tmp_path / "ghost"
    discovery = FileDiscovery(workspace_root=nonexistent)
    with pytest.raises(ScannerException):
        discovery.discover()
