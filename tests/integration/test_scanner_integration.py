"""Integration tests for Continuum Scanner and Code Brain."""
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from backend.app.core.config import ContinuumSettings
from backend.app.scanner.contracts import ParseStatus
from backend.app.scanner.repository import RepositoryScanner
from backend.app.workspace.context import WorkspaceContext


@pytest.fixture
def complex_workspace(tmp_path: Path) -> Path:
    """Create a realistic mixed-language repository fixture."""
    workspace = tmp_path / "my_project"
    workspace.mkdir()

    # Python module
    py_dir = workspace / "backend"
    py_dir.mkdir()
    (py_dir / "service.py").write_text(
        '''
import os
from typing import List

class DataService:
    """Processes user records."""
    def __init__(self):
        pass

    async def fetch_data(self) -> List[str]:
        """Fetch records async."""
        return ["a", "b"]

def compute_total(items: list) -> int:
    return len(items)
''',
        encoding="utf-8",
    )

    # TypeScript/TSX module
    ts_dir = workspace / "frontend" / "src"
    ts_dir.mkdir(parents=True)
    (ts_dir / "types.ts").write_text(
        """
export interface Item {
    id: string;
    title: string;
}

export type ItemList = Item[];
""",
        encoding="utf-8",
    )

    (ts_dir / "ItemList.tsx").write_text(
        """
import React from 'react';
import { Item } from './types';

export function useItems() {
    return [];
}

export const ItemList: React.FC<{ items: Item[] }> = ({ items }) => {
    return <ul>{items.map(i => <li key={i.id}>{i.title}</li>)}</ul>;
};
""",
        encoding="utf-8",
    )

    # Broken syntax file
    (workspace / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")

    # Ignored directory
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text("dummy", encoding="utf-8")
    (workspace / "node_modules" / "pkg").mkdir(parents=True)
    (workspace / "node_modules" / "pkg" / "index.js").write_text("ignore", encoding="utf-8")

    return workspace


def test_headless_scanner_full_run(complex_workspace: Path, tmp_path: Path):
    """Verify headless RepositoryScanner end-to-end execution without HTTP context."""
    continuum_home = tmp_path / ".continuum_test"
    settings = ContinuumSettings(continuum_home=continuum_home)

    context = WorkspaceContext.create(workspace_path=complex_workspace, config=settings)
    scanner = RepositoryScanner(context=context)
    result = scanner.scan(persist=True)

    # Check metrics
    assert result.metrics.files_discovered >= 4
    assert result.metrics.files_parsed >= 3
    assert result.metrics.symbols_extracted > 0
    assert result.metrics.relationships_extracted > 0

    # Verify broken file handled with partial error status
    broken_pr = next(pr for pr in result.parse_results if "broken.py" in pr.file_path)
    assert broken_pr.status == ParseStatus.PARTIAL_ERROR
    assert broken_pr.has_syntax_errors is True

    # Verify SQLite database exists and contains facts
    db_file = Path(result.symbols_db_path)
    assert db_file.exists()

    stats = scanner.code_brain_repo.get_stats()
    assert stats.files_count >= 4
    assert stats.symbols_count >= 6
    assert stats.relationships_count >= 6


def test_scanner_and_code_brain_api(test_client: TestClient, complex_workspace: Path, monkeypatch, tmp_path: Path):
    """Verify scanner execution and querying through the REST API."""
    continuum_home = tmp_path / ".continuum_api_test"
    monkeypatch.setenv("CONTINUUM_HOME", str(continuum_home))

    # 1. Trigger scan via POST
    response = test_client.post(f"/api/v1/scanner/scan?path={complex_workspace}")
    assert response.status_code == 200
    data = response.json()
    assert "project_id" in data
    assert data["metrics"]["files_parsed"] >= 3
    assert data["metrics"]["symbols_extracted"] > 0

    # 2. Query stats via GET
    stats_resp = test_client.get(f"/api/v1/code-brain/stats?path={complex_workspace}")
    assert stats_resp.status_code == 200
    stats_data = stats_resp.json()
    assert stats_data["symbols_count"] > 0

    # 3. Query symbols via GET
    sym_resp = test_client.get(f"/api/v1/code-brain/symbols?path={complex_workspace}")
    assert sym_resp.status_code == 200
    symbols = sym_resp.json()
    assert len(symbols) > 0
    names = {s["name"] for s in symbols}
    assert "DataService" in names
    assert "ItemList" in names
    assert "useItems" in names

    # 4. Query relationships via GET
    rel_resp = test_client.get(f"/api/v1/code-brain/relationships?path={complex_workspace}")
    assert rel_resp.status_code == 200
    rels = rel_resp.json()
    assert len(rels) > 0
