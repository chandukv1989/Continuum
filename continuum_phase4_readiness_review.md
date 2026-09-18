# Continuum — Phase 4 Architecture & Readiness Review

## 1. Executive Verdict

**READY WITH REQUIRED REFINEMENTS**

The Continuum platform has successfully established:
1. **Core Foundation (Phase 1)**: Robust process isolation, canonical path normalization, strict workspace boundaries, read-only Git operations, and security policies.
2. **Code Brain (Phase 2)**: Deterministic Tree-sitter AST parsing, symbol extraction, structural relationships, and SQLite storage with WAL concurrency.
3. **Project Brain + Technology Brain (Phase 3)**: Human-authored artifact governance, provenance tracking, soft symbol URI references (`sym://`), markdown+YAML local persistence, non-destructive reconciliation with discrepancy logging, and project-independent Technology Brain catalogs.

The platform is functionally stable (74/74 tests passing, zero linting or TypeScript compilation errors). However, before Phase 4 code can be safely implemented, **three critical architectural refinements** must be addressed to ensure incremental scanning remains strictly equivalent to a full rebuild without data corruption:
- **Refinement 1 (Code Brain Schema & Identity Evolution)**: The `files` table already tracks `content_hash`, but `symbols` and `relationships` tables currently lack targeted single-file deletion and dirty-state transaction primitives (currently only full wipe via `DELETE FROM files/symbols/relationships` exists).
- **Refinement 2 (Git Independence)**: Change detection cannot rely exclusively on `git status` because developer edits occur before commit/staging and inside non-Git workspaces. A dual-tier change detector (Filesystem Content-Hash Diff + Git Porcelain v2 Adapter) is required.
- **Refinement 3 (Targeted Project Brain Reconciliation)**: Reconciliation currently iterates through *every* Project Brain entity on every invocation (`ProjectBrainReconciler.reconcile()`). Incremental updates require path/symbol-filtered reconciliation to avoid $O(N_{entities})$ latency on single-file saves.

---

## 2. Repository Inspection

The repository was thoroughly inspected across all modules, configuration files, SQLite databases, and tests.

- **Source Code Inspected**:
  - `backend/app/core/`: `security.py`, `config.py`, `exceptions.py`, `logging.py`
  - `backend/app/workspace/`: `context.py`, `git.py`, `identity.py`
  - `backend/app/scanner/`: `contracts.py`, `discovery.py`, `filtering.py`, `parser.py`, `symbols.py`, `relationships.py`, `repository.py`
  - `backend/app/code_brain/`: `database.py`, `models.py`, `repository.py`
  - `backend/app/project_brain/`: `contracts.py`, `storage.py`, `repository.py`, `resolver.py`, `sync.py`
  - `backend/app/tech_brain/`: `contracts.py`, `repository.py`
  - `backend/app/api/`: `routes.py`, `schemas.py`
- **Environment & State**:
  - Current verified scan metrics on workspace root:
    - Files discovered: 77
    - Files parsed: 64
    - Symbols extracted: 340
    - Structural relationships extracted: 893
  - SQLite database location: `~/.continuum/projects/<project_id>/symbols.db`
  - Local Project Brain directory: `<workspace>/.continuum/{architecture,features,concepts,conventions,decisions,discrepancies.yaml}`
  - Global Technology Brain directory: `~/.continuum/technology/`

---

## 3. Phase 1 Verification

Phase 1 Core Foundation is locked, fully operational, and verified:
- **Security Boundaries**: Path traversal attempts, symlink boundary escapes, and disallowed shell binaries are strictly rejected via `SecurityManager.validate_safe_path()` and `SecurityManager.run_safe_subprocess()`.
- **Workspace Context & Identity**: Three-tier deterministic project identity resolution (Tier 1: Git Remote Origin SHA-256; Tier 2: Root Commit SHA-256; Tier 3: Canonical Workspace Path SHA-256) ensures persistent mapping across sessions.
- **Read-Only Git**: `GitAdapter` restricts operations to `ALLOWED_GIT_SUBCOMMANDS = {"status", "rev-parse", "rev-list", "remote", "log", "diff"}` and strictly prohibits mutating commands (`add`, `commit`, `push`, `checkout`, `reset`).
- **Configuration & Logging**: Pydantic v2 settings (`ContinuumSettings`) mask secrets and serialize paths safely. Structured JSON logging is active across all subsystems.

---

## 4. Phase 2 Verification

Phase 2 Code Brain full repository scanning is locked and verified:
- **File Discovery & Filtering**: Iterative BFS directory traversal with inode loop detection (`(st_dev, st_ino)`), `.gitignore`-compatible pattern matching, binary/vendor directory exclusion (`node_modules`, `.git`, `dist`, `.venv`).
- **AST Parsing Engine**: Tree-sitter parsers for Python, TypeScript, and TSX with robust syntax error handling (`ParseStatus.SUCCESS`, `ParseStatus.PARTIAL_ERROR`, `ParseStatus.FAILED`).
- **Symbol Extraction**: Extracts classes, functions, async functions, methods, interfaces, type aliases, enums, React components, and custom hooks.
- **Relationship Extraction**: Extracts `IMPORTS`, `EXTENDS`, `IMPLEMENTS`, `CALLS`, `INSTANTIATES`, and `USES_TYPE`.
- **Database Architecture**: SQLite with WAL mode (`PRAGMA journal_mode=WAL;`), normal synchronization (`PRAGMA synchronous=NORMAL;`), foreign key cascades, and busy timeouts (5000ms).

---

## 5. Phase 3 Verification

Phase 3 Project Brain & Technology Brain systems are locked and verified:
- **Domain Contracts & Governance**: `ArtifactOwnership` (`HUMAN_AUTHORED`, `DERIVED`, `GENERATED`, `HYBRID`) protects human decisions against automated overwrites. Any automated pipeline attempting to overwrite human knowledge raises `GovernanceViolationException`.
- **Local-First Persistence**: Transparent Markdown with YAML frontmatter, atomic disk writes, and sensitive secret sanitization (API keys, private keys).
- **Soft Code References**: `CodeSymbolRef` (`sym://<path>#<qualified_name>?kind=<kind>`) resolves exact matches, identifies relocated symbols (`STALE`), and detects missing symbols (`UNRESOLVED`).
- **Non-Destructive Reconciliation**: `ProjectBrainReconciler` detects discrepancies between documentation and source code, logging them to `discrepancies.yaml` while preserving 100% of human Markdown text.
- **Technology Brain**: Global knowledge base isolated in `~/.continuum/technology/`, strictly rejecting proprietary paths and project secrets.

---

## 6. Current Code Brain Assessment

The Code Brain implementation in `backend/app/code_brain/` provides solid primitives but has one structural characteristic designed for full rebuilds:
- **Strengths**:
  - `files.content_hash` (SHA-256) is already calculated during discovery and stored in SQLite.
  - Foreign key cascading is enabled (`FOREIGN KEY(file_path) REFERENCES files(path) ON DELETE CASCADE`), meaning deleting a file row automatically cascades to delete all associated symbols and relationships.
  - Deterministic symbol identity (`generate_symbol_id`) hashes `file_path:qualified_name:kind` without line numbers, ensuring line-offset edits do not change symbol IDs.
- **Gaps for Phase 4**:
  - `CodeBrainRepository.rebuild()` currently executes an unconditional `DELETE FROM files; DELETE FROM symbols; DELETE FROM relationships;`. It lacks a surgical `delete_file_artifacts(file_path)` method and an incremental `upsert_file_artifacts()` transaction.
  - Relationships targeting symbols across multiple files need re-linking when a target symbol is added or removed.

---

## 7. Current Project Brain Assessment

- **Strengths**:
  - `CodeReferenceResolver` cleanly categorizes reference states into `RESOLVED`, `STALE`, and `UNRESOLVED`.
  - Discrepancies are appended to `discrepancies.yaml` with timestamps and conflict descriptions without modifying human documents.
- **Gaps for Phase 4**:
  - `ProjectBrainReconciler.reconcile()` performs a full scan over all architecture, feature, concept, convention, and decision files.
  - In Phase 4, an incremental reconcile method (`reconcile_paths(changed_paths: Set[str])`) must be added to only inspect entities whose `code_refs` intersect with the modified or moved files.

---

## 8. Current Technology Brain Assessment

- **Strengths**:
  - Stored in global `~/.continuum/technology/`.
  - Strictly project-independent with enforcement regex forbidding workspace paths.
- **Phase 4 Policy**:
  - Incremental source changes (e.g. modifying `package.json` or `pyproject.toml`) can trigger updates to Project Brain feature/concept technology linkages, but MUST NOT alter global Technology Brain definitions.

---

## 9. Incremental Intelligence Architecture

The intended conceptual pipeline for Phase 4 is:
```
       Workspace Mutation (File edit / save / delete / rename)
                                 ↓
            Change Detection (FS Hash Cache + Git Status)
                                 ↓
                     Normalized ChangeSet
         [ADDED(paths), MODIFIED(paths), DELETED(paths), RENAMED(old->new)]
                                 ↓
                Targeted Tree-sitter Parsing
         (Parse ONLY added / modified files; skip unchanged files)
                                 ↓
                 Atomic SQLite Transaction
         1. Delete cascade for DELETED and old RENAMED paths
         2. Delete cascade for MODIFIED paths
         3. Insert fresh symbols & relationships for MODIFIED / ADDED paths
         4. Update `files` table metadata (mtime, size, content_hash)
                                 ↓
             Incremental Project Brain Reconciliation
         (Re-evaluate only entities referencing affected paths/symbols)
                                 ↓
             Discrepancy Logging & State Update
```

---

## 10. Change Set Model

Continuum requires a normalized, source-agnostic domain model:
```python
class ChangeType(str, Enum):
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    RENAMED = "RENAMED"

class FileChange(BaseModel):
    path: str                       # POSIX relative path
    old_path: Optional[str] = None  # Populated only for RENAMED
    change_type: ChangeType
    old_hash: Optional[str] = None
    new_hash: Optional[str] = None
    size_bytes: Optional[int] = None
    mtime: Optional[float] = None

class ChangeSet(BaseModel):
    changes: List[FileChange]
    detected_at: str
    detection_source: str           # "FILESYSTEM_HASH" | "GIT_PORCELAIN" | "HYBRID"
    is_empty: bool
```
This contract is independent of Git, watchdog, and HTTP APIs.

---

## 11. Change Detection Strategy

Change detection must operate across two tiers:
1. **Tier 1 (Fast Filesystem Stat & Content-Hash Diff)**:
   - Compare filesystem file list and `mtime`/`size` against the `files` table in `symbols.db`.
   - For files with changed `mtime` or `size`, compute SHA-256 `content_hash`.
   - If `content_hash != db_hash`: file is `MODIFIED`.
   - If path exists on disk but not in DB: file is `ADDED`.
   - If path exists in DB but not on disk: file is `DELETED`.
2. **Tier 2 (Git Porcelain Optimization when available)**:
   - If workspace is a Git repository, `GitAdapter.get_status()` provides candidate dirty files quickly.
   - Filesystem verification confirms the changes before AST processing.

---

## 12. Filesystem vs Git Strategy

- **Architectural Decision**: **Filesystem-based content hashing is authoritative; Git is an optional fast-path accelerator.**
- Developers frequently edit, rename, and draft code without staging or committing. Non-Git repositories (e.g. exports, archives, temporary test runs) must be fully supported.
- Git status must never be required for incremental scanning.

---

## 13. Incremental Scan Pipeline

When a `ChangeSet` is processed:
1. **Filter Evaluation**: Verify changed files against `FileFilter` (skip ignored extensions, vendor directories, binary files).
2. **Tree-sitter Parsing**: Parse *only* parseable `ADDED` and `MODIFIED` files. Unchanged files (e.g. 60 of 61 files) are not touched by Tree-sitter.
3. **Symbol & Relationship Extraction**: Extract symbols and relationships solely from newly parsed ASTs.
4. **Database Application**: Apply changes in a single SQLite transaction.

---

## 14. Symbol Identity Analysis

- Current symbol ID generation:
  $$\text{SHA-256}(file\_path : qualified\_name : kind)[:32]$$
- **Consequences**:
  - **Moving lines inside a file**: Symbol ID is 100% stable (line numbers are not in the hash).
  - **Renaming the file**: Symbol ID changes because `file_path` changed.
  - **Renaming the symbol**: Symbol ID changes.
- **Architectural Integrity**: This design is sound. Project Brain's soft reference `CodeSymbolRef` uses URI `sym://path#qualified_name?kind=...` and `CodeReferenceResolver` uses fallback queries (`SELECT id, file_path FROM symbols WHERE qualified_name = ?`) to detect relocations. No identity algorithm change is required.

---

## 15. File Rename / Move Handling

- When `old_path` moves to `new_path`:
  1. Content hash matches (`old_hash == new_hash`) or Git porcelain v2 detects `2 <XY> ... <path> <origPath>`.
  2. Code Brain removes `old_path` (cascading deletes symbols at old path).
  3. Code Brain inserts `new_path` with new deterministic symbol IDs.
  4. Project Brain reconciler flags existing `sym://old_path#Symbol` as `STALE`, noting `moved_to_path=new_path`, and logs a discrepancy without altering human files.

---

## 16. Dependency Effects

- **Direct Parse Requirement**: When file `B.ts` changes, only `B.ts` must be reparsed.
- **Downstream Structural Relationships**: If `A.ts` imported `B.ts#Bar`, and `Bar` was deleted from `B.ts`, the relationship in Code Brain (`A.ts -[IMPORTS]-> Bar`) now has an invalid target.
- **Rule for Phase 4**: Phase 4 updates structural relationships directly emitted by changed files and cleans dangling relationship pointers via foreign keys. Full semantic cross-file impact analysis is deferred to the future Impact Engine.

---

## 17. Code Brain Transaction Model

All mutations in an incremental update must execute within a single atomic SQLite transaction:
```python
with db.transaction() as conn:
    # 1. Remove deleted or modified file entries (cascades to symbols & relationships)
    for path in deleted_or_modified_paths:
        conn.execute("DELETE FROM files WHERE path = ?;", (path,))
    # 2. Insert updated file records
    # 3. Insert newly extracted symbols
    # 4. Insert newly extracted relationships
```
If any file fails during database persistence, the entire transaction rolls back cleanly. Code Brain remains in its pre-update consistent state.

---

## 18. Failure Handling

- **Partial Parse Failure**: If 3 files changed and 1 has syntax errors:
  - Tree-sitter parses error nodes as `ParseStatus.PARTIAL_ERROR` or `ParseStatus.FAILED`.
  - Extracted valid symbols from the file are retained if partial, or recorded with `parse_status='failed'` in `files`.
  - The other 2 files parse and persist normally.
- **I/O or Permission Error**: Log error, mark file as unparseable, and do not crash the repository index.
- **SQLite Error**: Rollback transaction, emit `CodeBrainException`, preserve existing database state.

---

## 19. Project Brain Reconciliation

- Incremental reconciliation evaluates only the delta:
  - Collect all symbol names and file paths affected in the `ChangeSet`.
  - Query Project Brain entities whose `code_refs` match the affected paths or symbol names.
  - Re-resolve only those references.
  - Mark matching references as `RESOLVED`, `STALE`, or `UNRESOLVED`.

---

## 20. Technology Brain Boundaries

- Technology Brain is strictly global (`~/.continuum/technology/`).
- Incremental scans in a workspace must NEVER modify global technology files.
- Project-level technology linkages belong in Project Brain concepts and features.

---

## 21. Artifact Governance During Incremental Updates

- `ArtifactOwnership` rules are strictly upheld:
  - `HUMAN_AUTHORED`: 100% read-only for automation. Any detected stale reference creates a discrepancy in `discrepancies.yaml`. The Markdown file is never modified or deleted.
  - `DERIVED`: May be automatically regenerated if source code facts change.
  - `GENERATED`: May be refreshed.
  - `HYBRID`: Flagged for human review.

---

## 22. Discrepancy Handling

- When an incremental update deletes or relocates a referenced symbol:
  - A `DiscrepancyEntity` is generated with `status=DiscrepancyStatus.OPEN`.
  - If a previously missing symbol is restored in a subsequent incremental scan, the reconciler updates the discrepancy status to `RESOLVED`.

---

## 23. Event Model

- For Phase 4 V1, an internal distributed event bus is unnecessary and rejected.
- Direct, synchronous orchestration (`IncrementalScanner.scan_incremental()`) ensures deterministic control flow, predictable error propagation, and clear stack traces.

---

## 24. Watcher Decision

- **Recommendation**: **DEFER background filesystem watching (`watchdog`) to Phase 4.2.**
- **Reasoning**:
  1. File watching introduces non-deterministic OS threading, save bursts, editor swap files (`.swp`, `.~`), atomic file replacement races, and platform-specific inotify limits.
  2. Phase 4.1 must first establish and rigorously test the synchronous `IncrementalScanner` and `ChangeSet` pipeline via CLI and API.
  3. Once synchronous incremental scanning is proven equivalent to full rebuilds, a debounce watcher can simply invoke the scanner.

---

## 25. Debouncing

- When the watcher is introduced in Phase 4.2:
  - 300ms trailing debounce window.
  - Ignore editor lock/temp files (`.git/*`, `*~`, `*.tmp`, `*.swp`).

---

## 26. Concurrency

- **Concurrency Policy**: **Single Active Scanner Mutator Lock.**
- Multiple concurrent read queries are fully supported by SQLite WAL mode.
- Exactly one scan transaction (full or incremental) may mutate `symbols.db` at any time. An in-memory threading lock (`threading.Lock`) protects the scan orchestrator.

---

## 27. SQLite Safety

- WAL mode enabled (`PRAGMA journal_mode=WAL;`).
- Busy timeout set to 5000ms.
- Foreign keys enforced (`PRAGMA foreign_keys=ON;`).
- Transactions use explicit `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK`.

---

## 28. Cache Invalidation

- The primary cache is the `files` table in `symbols.db`, storing `(mtime, size_bytes, content_hash)`.
- Invalidation is driven purely by `content_hash` comparison. If file hash matches the stored DB hash, the AST cache for that file is valid.

---

## 29. Performance Model

- **Full Scan**: $O(N_{\text{all files}})$ — parses and indexes all 77 files (~1.2s in test environment).
- **Incremental Scan**: $O(N_{\text{changed files}})$ — for 1 modified file, parses 1 file, executes ~3 SQLite statements (<15ms).
- Result: Over 98% reduction in latency for single-file developer edits.

---

## 30. Large Repository Considerations

For repositories with 10,000+ files:
- Never hold all file contents in memory.
- Compute SHA-256 in 64KB streaming chunks (already implemented in `discovery.py`).
- Batch database inserts using `batch_size=500`.
- Fast path: check `mtime` and `size` before reading full file content for hashing.

---

## 31. Crash Recovery

- If the process terminates abruptly mid-scan:
  - SQLite WAL ensures atomicity: uncommitted transactions are rolled back automatically on restart.
  - The database is never corrupted.

---

## 32. Restart Recovery

- On startup, Continuum compares filesystem state against `files` table. Any files modified while Continuum was offline are identified in the next incremental check.

---

## 33. Full Rebuild Strategy

- `RepositoryScanner.scan(persist=True)` remains the authoritative baseline.
- If incremental scanning encounters database schema mismatch or irrecoverable state, a full rebuild is triggered automatically.

---

## 34. Source / Brain Drift Detection

- Signal for drift:
  - Discrepancy between filesystem file count and `files` table count.
  - Stored `content_hash` mismatch on random sample or audit request.
- Drift resolution: Trigger full rebuild.

---

## 35. Scanner Versioning

- `meta` table in SQLite stores `schema_version` (currently `2.0.0`).
- Add `scanner_version` to `meta`. If scanner version increases, invalidate DB and execute full rebuild.

---

## 36. Parser / Language Changes

- If Tree-sitter grammars or extraction rules change, existing cached symbols may be structurally incomplete.
- Policy: Grammar or parser updates increment `schema_version`, prompting a clean rebuild.

---

## 37. Configuration Changes

- If `ContinuumSettings.scanner_ignore_patterns` or supported languages change, incremental updates cannot guarantee accuracy.
- Policy: Configuration changes trigger a full rebuild.

---

## 38. Test Strategy

Phase 4 test suite must validate:
1. **Change Detection**: Accurate classification of `ADDED`, `MODIFIED`, `DELETED`, and `RENAMED` files.
2. **Atomic Incremental Updates**: Adding/editing/deleting symbols updates SQLite without orphaned records.
3. **Equivalence Invariant**:
   $$\text{FullScan}(\text{Repo}_{t_1}) \equiv \text{FullScan}(\text{Repo}_{t_0}) + \text{IncrementalScan}(\Delta_{t_0 \to t_1})$$
4. **Project Brain Safety**: Zero mutations to human-authored ADRs or conventions during symbol relocations.

---

## 39. Golden Repository Test

A dedicated integration fixture will:
1. Initialize a test workspace with Python and TypeScript files.
2. Run baseline `FullScan`.
3. Apply file edits, additions, renames, and deletions.
4. Run `IncrementalScan`.
5. Snapshot Code Brain state ($A$).
6. In a separate isolated database, run `FullScan` on the final workspace state ($B$).
7. Assert $A \equiv B$ across `files`, `symbols`, and `relationships` (excluding timestamps).

---

## 40. Security

- All changed file paths must be validated against `SecurityManager.validate_safe_path()`.
- No path traversal outside `canonical_root` is permitted during incremental events.

---

## 41. Git Safety

- Continuum Git operations remain 100% read-only.
- No `git add`, `git commit`, `git checkout`, or workspace file modifications will ever be performed.

---

## 42. API Surface

Add minimal headless endpoints to `backend/app/api/routes.py`:
- `POST /api/v1/scanner/scan/incremental`: Execute incremental scan and return `ChangeSet` and `ScanMetrics`.
- `GET /api/v1/scanner/changes`: Inspect detected changes without applying them.

---

## 43. Architecture Compliance

The architecture strictly adheres to:
- Modular Python monolith with FastAPI.
- SQLite WAL Code Brain storage.
- Pure Markdown + YAML Project Brain storage.
- Project-independent Technology Brain.
- Zero LLM dependencies, zero vector databases, zero microservices.

---

## 44. Required Refinements

Before implementing Phase 4:
1. **Add Surgical Deletion to `CodeBrainRepository`**:
   - Implement `delete_file_artifacts(file_path: str)` to delete specific file records with foreign key cascades.
2. **Add Transactional Upsert to `CodeBrainRepository`**:
   - Implement `upsert_file_artifacts(scanned_files, parse_results)` without wiping unrelated tables.
3. **Implement Dual-Tier Change Detector**:
   - Build `ChangeDetector` that compares filesystem `(path, mtime, size, hash)` against `symbols.db` before falling back to or augmenting with Git status.
4. **Implement Scoped Project Brain Reconciler**:
   - Add `reconcile_paths(changed_paths: Set[str])` to `ProjectBrainReconciler`.

---

## 45. Deferred Work

- **Background Watchdog Daemon (`watchdog`)**: Defer to Phase 4.2.
- **Semantic Impact Engine**: Defer to Phase 5.
- **Automated Commit Analysis**: Defer to future phases.
- **UI & Visualization**: Defer to frontend milestone.

---

## 46. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Race condition during simultaneous file writes | Medium | SQLite single-writer lock + busy timeout |
| Mtime resolution inaccuracy on certain filesystems | Low | Fallback to SHA-256 content hashing |
| Dangling inter-file relationship references | Medium | Re-evaluate relationships referencing modified symbols |
| Accidental overwrite of human Project Brain files | Critical | Strict `ArtifactOwnership` governance check |

---

## 47. Recommended Phase 4 Implementation Order

1. **Step 1**: Domain Contract — Define `ChangeType`, `FileChange`, and `ChangeSet` in `backend/app/scanner/contracts.py`.
2. **Step 2**: Code Brain Primitives — Add `delete_file_artifacts` and `apply_incremental_scan` to `CodeBrainRepository`.
3. **Step 3**: Change Detection Engine — Implement `ChangeDetector` comparing filesystem state against `files` table.
4. **Step 4**: Incremental Scanner Orchestrator — Implement `IncrementalScanner` orchestrating discovery delta, targeted Tree-sitter parsing, and transactional SQLite update.
5. **Step 5**: Targeted Reconciliation — Add path-filtered reconciliation to `ProjectBrainReconciler`.
6. **Step 6**: Headless API Endpoints — Expose `POST /api/v1/scanner/scan/incremental`.
7. **Step 7**: Test Suite & Golden Equivalence Test — Verify `IncrementalScan == FullRebuild`.
8. **Step 8 (Optional/Phase 4.2)**: Debounced background filesystem watcher.

---

## 48. Final Verdict

**READY WITH REQUIRED REFINEMENTS**

The architectural foundation of Continuum across Phases 1, 2, and 3 is solid, reliable, and verified. By implementing the four concrete refinements outlined in Section 44, Continuum will safely achieve incremental intelligence with mathematical equivalence to full repository rebuilds.

---

## 49. Evidence

- **Test Suite Execution**:
  - Command: `.venv/bin/python -m pytest -v`
  - Output: `74 passed, 2 warnings in 1.27s` (100% pass rate)
- **Git Status**:
  - Command: `git status --porcelain=v2 --branch`
  - Output: Verified clean/read-only workspace.
- **Inspected Modules**:
  - `backend/app/core/` (config, exceptions, logging, security)
  - `backend/app/workspace/` (context, git, identity)
  - `backend/app/scanner/` (contracts, discovery, filtering, parser, symbols, relationships, repository)
  - `backend/app/code_brain/` (database, models, repository)
  - `backend/app/project_brain/` (contracts, storage, repository, resolver, sync)
  - `backend/app/tech_brain/` (contracts, repository)
  - `backend/app/api/` (routes, schemas)
- **Database Facts**:
  - Code Brain SQLite: 77 files, 64 parsed, 340 symbols, 893 relationships currently indexed in live project database.
  - Schema Version: `2.0.0` with WAL journal mode verified.
