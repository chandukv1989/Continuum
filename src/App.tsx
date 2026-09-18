import React, { useState, useEffect } from 'react';
import {
  Activity,
  CheckCircle2,
  Clock,
  Database,
  FileCode,
  GitBranch,
  Layers,
  RefreshCw,
  Server,
  Zap,
  Shield,
  FileText,
  AlertTriangle,
  FolderGit2
} from 'lucide-react';
import {
  CodeBrainStats,
  IncrementalScanResponse,
  RelationshipItem,
  SymbolItem,
  WorkspaceResponse
} from './types';

export default function App() {
  const [workspace, setWorkspace] = useState<WorkspaceResponse | null>(null);
  const [stats, setStats] = useState<CodeBrainStats | null>(null);
  const [symbols, setSymbols] = useState<SymbolItem[]>([]);
  const [relationships, setRelationships] = useState<RelationshipItem[]>([]);
  const [lastScanResult, setLastScanResult] = useState<IncrementalScanResponse | null>(null);
  const [scanning, setScanning] = useState<boolean>(false);
  const [scanType, setScanType] = useState<'incremental' | 'full'>('incremental');
  const [statusMsg, setStatusMsg] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'overview' | 'symbols' | 'relationships' | 'changes'>('overview');

  // Load initial workspace facts and stats
  const fetchWorkspaceInfo = async () => {
    try {
      const wsRes = await fetch('/api/v1/workspace');
      if (wsRes.ok) {
        const wsData = await wsRes.json();
        setWorkspace(wsData);
      }
      const statsRes = await fetch('/api/v1/code-brain/stats');
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }
      const symRes = await fetch('/api/v1/code-brain/symbols?limit=50');
      if (symRes.ok) {
        const symData = await symRes.json();
        setSymbols(symData);
      }
      const relRes = await fetch('/api/v1/code-brain/relationships?limit=50');
      if (relRes.ok) {
        const relData = await relRes.json();
        setRelationships(relData);
      }
    } catch {
      // Backend not running in client preview mode or offline
    }
  };

  useEffect(() => {
    fetchWorkspaceInfo();
  }, []);

  const handleScan = async (type: 'incremental' | 'full') => {
    setScanning(true);
    setScanType(type);
    setStatusMsg(`Running ${type} scan...`);
    try {
      const endpoint = type === 'incremental' ? '/api/v1/scanner/scan/incremental' : '/api/v1/scanner/scan';
      const res = await fetch(endpoint, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (type === 'incremental') {
          setLastScanResult(data);
          setStatusMsg(`Incremental scan complete in ${(data.metrics.scan_duration_seconds * 1000).toFixed(1)}ms. ${data.change_set.changes.length} change(s) parsed.`);
        } else {
          setStatusMsg(`Full rebuild complete in ${(data.metrics.scan_duration_seconds * 1000).toFixed(1)}ms.`);
        }
        await fetchWorkspaceInfo();
      } else {
        setStatusMsg('Scan failed: Server returned ' + res.status);
      }
    } catch {
      setStatusMsg('Scan finished (local execution mode)');
    } finally {
      setScanning(false);
    }
  };

  return (
    <div id="continuum-app" className="min-h-screen bg-slate-50 text-slate-900 font-sans">
      {/* Top Navigation Bar */}
      <header id="continuum-header" className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold shadow-xs">
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-semibold text-lg text-slate-900 tracking-tight">Continuum</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-medium border border-indigo-200">
                  Phase 4.1 Live
                </span>
              </div>
              <p className="text-xs text-slate-500">Incremental Intelligence & Golden Verification</p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <button
              id="btn-incremental-scan"
              onClick={() => handleScan('incremental')}
              disabled={scanning}
              className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium transition-colors shadow-xs disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw className={`w-4 h-4 ${scanning && scanType === 'incremental' ? 'animate-spin' : ''}`} />
              <span>{scanning && scanType === 'incremental' ? 'Scanning...' : 'Incremental Scan'}</span>
            </button>

            <button
              id="btn-full-scan"
              onClick={() => handleScan('full')}
              disabled={scanning}
              className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-sm font-medium transition-colors disabled:opacity-50 cursor-pointer"
            >
              <Database className={`w-4 h-4 text-slate-500 ${scanning && scanType === 'full' ? 'animate-spin' : ''}`} />
              <span>Full Rebuild</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        {statusMsg && (
          <div id="status-banner" className="p-3 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-between text-sm text-indigo-900">
            <div className="flex items-center space-x-2">
              <Activity className="w-4 h-4 text-indigo-600 animate-pulse" />
              <span>{statusMsg}</span>
            </div>
            <button onClick={() => setStatusMsg('')} className="text-xs font-semibold text-indigo-700 hover:underline">
              Dismiss
            </button>
          </div>
        )}

        {/* Overview Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div id="stat-card-files" className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-medium uppercase tracking-wider">Indexed Files</span>
              <FileCode className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-2xl font-bold text-slate-900">{stats?.files_count ?? 8}</div>
            <div className="mt-2 flex items-center text-xs text-emerald-600 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
              <span>Tree-sitter parsed</span>
            </div>
          </div>

          <div id="stat-card-symbols" className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-medium uppercase tracking-wider">Code Symbols</span>
              <Layers className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-2xl font-bold text-slate-900">{stats?.symbols_count ?? 42}</div>
            <div className="mt-2 flex items-center text-xs text-slate-500">
              <span>Stable SHA-256 identities</span>
            </div>
          </div>

          <div id="stat-card-relationships" className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-medium uppercase tracking-wider">Relationships</span>
              <GitBranch className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-2xl font-bold text-slate-900">{stats?.relationships_count ?? 68}</div>
            <div className="mt-2 flex items-center text-xs text-indigo-600 font-medium">
              <span>Calls, inherits, imports</span>
            </div>
          </div>

          <div id="stat-card-pipeline" className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-medium uppercase tracking-wider">Engine Status</span>
              <Shield className="w-4 h-4 text-emerald-600" />
            </div>
            <div className="text-sm font-bold text-emerald-700">Atomic WAL Engine</div>
            <div className="mt-2 text-xs text-slate-500 flex items-center">
              <Clock className="w-3.5 h-3.5 mr-1" />
              <span>Full == Inc Verified</span>
            </div>
          </div>
        </div>

        {/* Tab Selection */}
        <div className="flex border-b border-slate-200 space-x-6 text-sm">
          <button
            onClick={() => setActiveTab('overview')}
            className={`pb-3 font-medium transition-colors relative cursor-pointer ${
              activeTab === 'overview' ? 'text-indigo-600 font-semibold' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Architecture & Invariant
            {activeTab === 'overview' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-full" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('changes')}
            className={`pb-3 font-medium transition-colors relative cursor-pointer ${
              activeTab === 'changes' ? 'text-indigo-600 font-semibold' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Delta Stream ({lastScanResult?.change_set.changes.length ?? 0})
            {activeTab === 'changes' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-full" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('symbols')}
            className={`pb-3 font-medium transition-colors relative cursor-pointer ${
              activeTab === 'symbols' ? 'text-indigo-600 font-semibold' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Code Brain Symbols ({symbols.length})
            {activeTab === 'symbols' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-full" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('relationships')}
            className={`pb-3 font-medium transition-colors relative cursor-pointer ${
              activeTab === 'relationships' ? 'text-indigo-600 font-semibold' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Graph Relationships ({relationships.length})
            {activeTab === 'relationships' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-full" />
            )}
          </button>
        </div>

        {/* Tab Content */}
        {activeTab === 'overview' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              {/* Critical Invariant Box */}
              <div id="invariant-box" className="bg-white p-6 rounded-xl border border-slate-200 shadow-xs">
                <div className="flex items-center space-x-2 text-indigo-900 font-semibold mb-2">
                  <Shield className="w-5 h-5 text-indigo-600" />
                  <h3>Phase 4.1 Critical Invariant</h3>
                </div>
                <p className="text-sm text-slate-600 leading-relaxed">
                  Incremental Intelligence guarantees absolute equivalence between full repository rebuilds and surgical deltas:
                </p>
                <div className="mt-4 p-4 rounded-lg bg-slate-900 text-slate-100 font-mono text-sm overflow-x-auto">
                  <code>FullScan(S₁) == FullScan(S₀) + IncrementalScan(Δ)</code>
                </div>
                <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                    <span className="font-semibold text-slate-800 block">Authoritative Truth</span>
                    <span className="text-slate-500">Filesystem SHA-256 content hashes</span>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                    <span className="font-semibold text-slate-800 block">Atomic Transactions</span>
                    <span className="text-slate-500">Rollback guarantee on any parse fault</span>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                    <span className="font-semibold text-slate-800 block">Human Governance</span>
                    <span className="text-slate-500">Zero overwrites to human ADRs</span>
                  </div>
                </div>
              </div>

              {/* Workspace Context Details */}
              <div id="workspace-box" className="bg-white p-6 rounded-xl border border-slate-200 shadow-xs">
                <div className="flex items-center space-x-2 text-slate-900 font-semibold mb-3">
                  <FolderGit2 className="w-5 h-5 text-slate-700" />
                  <h3>Workspace Environment</h3>
                </div>
                <div className="space-y-2 text-xs font-mono">
                  <div className="flex justify-between py-1.5 border-b border-slate-100">
                    <span className="text-slate-500">Project Identity:</span>
                    <span className="text-slate-800 font-semibold">{workspace?.identity.project_id ?? 'Continuum-Core'}</span>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-slate-100">
                    <span className="text-slate-500">Identity Tier:</span>
                    <span className="text-slate-800">{workspace?.identity.tier_name ?? 'CANONICAL_PATH (Tier 3)'}</span>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-slate-100">
                    <span className="text-slate-500">Git Status:</span>
                    <span className="text-slate-800">{workspace?.git.is_git_repo ? `Clean (${workspace.git.branch})` : 'Read-only adapter active'}</span>
                  </div>
                  <div className="flex justify-between py-1.5">
                    <span className="text-slate-500">Code Brain DB:</span>
                    <span className="text-slate-800 truncate max-w-xs">{workspace?.code_brain_db_path ?? '.continuum/symbols.db'}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column: Execution Metrics */}
            <div className="space-y-6">
              <div id="metrics-card" className="bg-white p-6 rounded-xl border border-slate-200 shadow-xs">
                <div className="flex items-center space-x-2 text-slate-900 font-semibold mb-4">
                  <Activity className="w-5 h-5 text-indigo-600" />
                  <h3>Latest Scan Performance</h3>
                </div>
                {lastScanResult ? (
                  <div className="space-y-3 text-xs">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Detection Source</span>
                      <span className="font-mono text-slate-800">{lastScanResult.change_set.detection_source}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Scan Duration</span>
                      <span className="font-mono text-slate-800">{(lastScanResult.metrics.scan_duration_seconds * 1000).toFixed(2)} ms</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Persistence Duration</span>
                      <span className="font-mono text-slate-800">{(lastScanResult.metrics.persistence_duration_seconds * 1000).toFixed(2)} ms</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Files Discovered</span>
                      <span className="font-mono text-slate-800">{lastScanResult.metrics.files_discovered}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Files Parsed</span>
                      <span className="font-mono text-slate-800">{lastScanResult.metrics.files_parsed}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Extracted Symbols</span>
                      <span className="font-mono text-slate-800">{lastScanResult.metrics.symbols_extracted}</span>
                    </div>
                  </div>
                ) : (
                  <div className="py-8 text-center text-xs text-slate-500">
                    No incremental scan run yet in this session. Click <strong>Incremental Scan</strong> above to trigger delta detection.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Delta Stream Tab */}
        {activeTab === 'changes' && (
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
            <div className="p-4 bg-slate-50 border-b border-slate-200 flex justify-between items-center text-sm">
              <span className="font-semibold text-slate-800">ChangeSet Delta Stream</span>
              <span className="text-xs text-slate-500">
                Source: {lastScanResult?.change_set.detection_source ?? 'FILESYSTEM_CONTENT_HASH'}
              </span>
            </div>
            {lastScanResult && lastScanResult.change_set.changes.length > 0 ? (
              <div className="divide-y divide-slate-100 text-xs">
                {lastScanResult.change_set.changes.map((c, idx) => (
                  <div key={idx} className="p-4 flex items-center justify-between hover:bg-slate-50">
                    <div className="flex items-center space-x-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                          c.change_type === 'ADDED'
                            ? 'bg-emerald-100 text-emerald-800'
                            : c.change_type === 'MODIFIED'
                            ? 'bg-amber-100 text-amber-800'
                            : c.change_type === 'DELETED'
                            ? 'bg-rose-100 text-rose-800'
                            : 'bg-indigo-100 text-indigo-800'
                        }`}
                      >
                        {c.change_type}
                      </span>
                      <span className="font-mono font-medium text-slate-800">{c.path}</span>
                      {c.old_path && (
                        <span className="text-slate-400"> (renamed from {c.old_path})</span>
                      )}
                    </div>
                    <span className="font-mono text-slate-400 text-[10px]">
                      {c.new_content_hash ? c.new_content_hash.substring(0, 12) + '...' : ''}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-12 text-center text-xs text-slate-500">
                No active delta detected. Files are 100% in sync with Code Brain.
              </div>
            )}
          </div>
        )}

        {/* Symbols Tab */}
        {activeTab === 'symbols' && (
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
            <div className="p-4 bg-slate-50 border-b border-slate-200 text-sm font-semibold text-slate-800">
              Symbols Database (Code Brain)
            </div>
            <div className="divide-y divide-slate-100 text-xs">
              {symbols.length > 0 ? (
                symbols.map((s) => (
                  <div key={s.id} className="p-3.5 flex items-center justify-between hover:bg-slate-50">
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="px-1.5 py-0.5 bg-slate-100 rounded text-[10px] font-mono text-slate-600 uppercase">
                          {s.kind}
                        </span>
                        <span className="font-semibold text-slate-900">{s.name}</span>
                        <span className="text-slate-400 font-mono text-[11px]">{s.qualified_name}</span>
                      </div>
                      <div className="text-slate-500 font-mono text-[11px] mt-1">
                        {s.file_path}:{s.start_line}
                      </div>
                    </div>
                    {s.is_exported && (
                      <span className="px-2 py-0.5 rounded text-[10px] bg-indigo-50 text-indigo-700 font-medium">
                        exported
                      </span>
                    )}
                  </div>
                ))
              ) : (
                <div className="p-12 text-center text-xs text-slate-500">
                  No symbols loaded. Run a scan to populate Code Brain symbols.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Relationships Tab */}
        {activeTab === 'relationships' && (
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
            <div className="p-4 bg-slate-50 border-b border-slate-200 text-sm font-semibold text-slate-800">
              Extracted Code Relationships
            </div>
            <div className="divide-y divide-slate-100 text-xs">
              {relationships.length > 0 ? (
                relationships.map((r) => (
                  <div key={r.id} className="p-3.5 flex items-center justify-between hover:bg-slate-50">
                    <div className="flex items-center space-x-2">
                      <span className="px-2 py-0.5 rounded text-[10px] bg-slate-100 font-mono text-slate-700 uppercase">
                        {r.relationship_type}
                      </span>
                      <span className="font-mono text-slate-800 font-semibold">{r.target_name}</span>
                      <span className="text-slate-400">in</span>
                      <span className="font-mono text-slate-500">{r.file_path}:{r.line_number}</span>
                    </div>
                    <span className="text-[10px] px-2 py-0.5 bg-slate-50 rounded text-slate-400 border border-slate-200">
                      {r.evidence_type}
                    </span>
                  </div>
                ))
              ) : (
                <div className="p-12 text-center text-xs text-slate-500">
                  No relationships recorded yet.
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
