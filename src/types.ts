export interface WorkspaceIdentity {
  project_id: string;
  tier: number;
  tier_name: string;
  raw_identifier: string;
  canonical_path: string;
}

export interface GitStatus {
  is_git_repo: boolean;
  repository_root?: string;
  branch?: string;
  current_commit?: string;
  remote_origin?: string;
  modified_files: string[];
  staged_files: string[];
  untracked_files: string[];
  uncommitted_changes: boolean;
  status_state: string;
}

export interface WorkspaceResponse {
  canonical_root: string;
  identity: WorkspaceIdentity;
  git: GitStatus;
  project_brain_dir: string;
  code_brain_db_path: string;
}

export interface ScanMetrics {
  files_discovered: number;
  files_filtered: number;
  files_parsed: number;
  parse_failures: number;
  symbols_extracted: number;
  relationships_extracted: number;
  scan_duration_seconds: number;
  persistence_duration_seconds: number;
}

export interface FileChangeItem {
  path: string;
  change_type: 'ADDED' | 'MODIFIED' | 'DELETED' | 'RENAMED';
  old_path?: string;
  old_content_hash?: string;
  new_content_hash?: string;
  size_bytes?: number;
  mtime?: number;
}

export interface ChangeSetData {
  changes: FileChangeItem[];
  detected_at?: string;
  detection_source: string;
  is_empty: boolean;
}

export interface IncrementalScanResponse {
  project_id: string;
  canonical_root: string;
  symbols_db_path: string;
  change_set: ChangeSetData;
  metrics: ScanMetrics;
  reconciliation_report?: {
    entities_inspected: number;
    references_resolved: number;
    references_unresolved: number;
    references_stale: number;
    discrepancies_recorded: number;
    human_artifacts_preserved: number;
  };
}

export interface CodeBrainStats {
  files_count: number;
  symbols_count: number;
  relationships_count: number;
}

export interface SymbolItem {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  language: string;
  file_path: string;
  start_line: number;
  end_line: number;
  is_exported: boolean;
}

export interface RelationshipItem {
  id: string;
  source_id: string;
  target_name: string;
  target_id?: string;
  relationship_type: string;
  evidence_type: string;
  file_path: string;
  line_number: number;
}
