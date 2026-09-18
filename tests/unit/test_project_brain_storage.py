"""Unit tests for Project Brain storage, frontmatter parsing, and security sanitization."""
import pytest
from backend.app.core.exceptions import ProjectBrainException
from backend.app.project_brain.storage import (
    ProjectBrainStorage,
    dump_frontmatter_markdown,
    parse_frontmatter_markdown,
    sanitize_content,
)


def test_frontmatter_roundtrip():
    metadata = {
        "id": "feat:ast-scanner",
        "name": "AST Scanner",
        "tags": ["scanner", "parser"],
    }
    body = "# AST Scanner\n\nThis feature parses code into deterministic AST symbols."
    serialized = dump_frontmatter_markdown(metadata, body)
    assert serialized.startswith("---\n")
    assert "feat:ast-scanner" in serialized

    parsed_meta, parsed_body = parse_frontmatter_markdown(serialized)
    assert parsed_meta["id"] == "feat:ast-scanner"
    assert parsed_meta["name"] == "AST Scanner"
    assert parsed_meta["tags"] == ["scanner", "parser"]
    assert "# AST Scanner" in parsed_body


def test_empty_frontmatter_markdown():
    raw = "# Raw Markdown Without Frontmatter\nJust normal content."
    meta, body = parse_frontmatter_markdown(raw)
    assert meta == {}
    assert "Just normal content." in body


def test_invalid_yaml_frontmatter():
    bad_yaml = "---\n: bad yaml: [unclosed\n---\nBody"
    with pytest.raises(ProjectBrainException, match="Invalid YAML"):
        parse_frontmatter_markdown(bad_yaml)


def test_security_sanitization_rejects_credentials():
    bad_inputs = [
        "api_key = 'super_secret_1234567890'",
        "sk-1234567890abcdef1234567890abcdef",
        "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...",
    ]
    for bad in bad_inputs:
        with pytest.raises(ProjectBrainException, match="Detected sensitive credentials"):
            sanitize_content(bad)

        with pytest.raises(ProjectBrainException, match="Detected sensitive credentials"):
            dump_frontmatter_markdown({"key": "val"}, f"Note: {bad}")


def test_project_brain_storage_lifecycle(tmp_path):
    storage = ProjectBrainStorage(tmp_path / ".continuum")
    storage.ensure_directories()
    assert storage.architecture_dir.exists()
    assert storage.features_dir.exists()
    assert storage.decisions_dir.exists()

    target_file = storage.architecture_dir / "backend.md"
    storage.write_file(target_file, "---\nid: arch:backend\n---\n# Backend")
    assert target_file.exists()

    read_back = storage.read_file(target_file)
    assert "arch:backend" in read_back
