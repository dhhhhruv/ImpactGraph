import React, { useState, useCallback } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { fetchRepos, fetchDemo, fetchSubgraph, analyzeChange } from './api'
import RiskCard from './components/RiskCard'
import BlastPanel from './components/BlastPanel'
import TestsPanel from './components/TestsPanel'
import ReviewersPanel from './components/ReviewersPanel'
import AskBox from './components/AskBox'
import GraphCanvas from './components/GraphCanvas'
import EvidenceTab from './components/EvidenceTab'
import BenchmarkTab from './components/BenchmarkTab'

const DEMO_IDS = [1, 2, 3, 4, 5]

const DEMO_HUNKS = [
  { path: 'src/vorta/scheduler/execution.py', start: 5, end: 25 },
]

export default function App() {
  // Controls
  const [repo, setRepo] = useState('borgbase/vorta')
  const [prInput, setPrInput] = useState('')
  const [graphOn, setGraphOn] = useState(true)
  const [demoMode, setDemoMode] = useState(false)
  const [demoId, setDemoId] = useState(1)
  const [dryRun, setDryRun] = useState(false)

  // Selection state
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [activeTab, setActiveTab] = useState('graph') // 'graph' | 'evidence' | 'benchmark'

  // Data state
  const [decision, setDecision] = useState(null)
  const [subgraphData, setSubgraphData] = useState(null)

  // Repos list
  const { data: repos } = useQuery({ queryKey: ['repos'], queryFn: fetchRepos })

  // Demo query
  const { data: demoData, isLoading: demoLoading } = useQuery({
    queryKey: ['demo', demoId],
    queryFn: () => fetchDemo(demoId),
    enabled: demoMode,
    onSuccess: (d) => {
      if (d?.decision) setDecision(d.decision)
    },
  })

  // When demo loads, update decision
  React.useEffect(() => {
    if (demoMode && demoData?.decision) {
      setDecision(demoData.decision)
      setSubgraphData(null)
    }
  }, [demoMode, demoData])

  // Analyze mutation
  const analyzeMutation = useMutation({
    mutationFn: analyzeChange,
    onSuccess: async (data) => {
      setDecision(data.decision)
      // Also fetch subgraph
      if (data.decision?.changed_functions?.length) {
        const sg = await fetchSubgraph(repo, data.decision.changed_functions)
        setSubgraphData(sg)
      }
    },
  })

  const handleAnalyze = useCallback(() => {
    if (dryRun) {
      alert('Dry run mode: analysis would POST to /analyze with repo=' + repo)
      return
    }
    if (demoMode) return
    analyzeMutation.mutate({
      repo,
      diffHunks: DEMO_HUNKS,
      headSha: prInput ? `pr-${prInput}` : 'HEAD',
    })
  }, [repo, prInput, dryRun, demoMode, analyzeMutation])

  const handleNodeClick = useCallback((id) => {
    setSelectedNodeId(id)
  }, [])

  const currentDecision = demoMode ? demoData?.decision : decision
  const isLoading = (demoMode && demoLoading) || analyzeMutation.isPending
  const hasData = !!currentDecision

  // Build graph elements from decision
  const graphElements = React.useMemo(() => {
    if (!graphOn) return null
    if (subgraphData?.elements) return subgraphData.elements
    if (!currentDecision) return null

    const nodes = []
    const edges = []
    const seen = new Set()

    const addNode = (id, label, type) => {
      if (!id || seen.has(id)) return
      seen.add(id)
      nodes.push({ data: { id, label: label || id.split('.').slice(-1)[0], full_qname: id, type } })
    }

    for (const fn of currentDecision.changed_functions || []) addNode(fn, fn.split('.').slice(-1)[0], 'changed')
    for (const row of currentDecision.blast_radius || []) {
      addNode(row.affected, row.affected?.split('.').slice(-1)[0], 'caller')
      const path = row.path || []
      for (let i = 0; i < path.length - 1; i++) {
        addNode(path[i], path[i]?.split('.').slice(-1)[0], 'caller')
        addNode(path[i+1], path[i+1]?.split('.').slice(-1)[0], 'caller')
        edges.push({ data: { id: `${path[i]}->${path[i+1]}`, source: path[i], target: path[i+1] } })
      }
    }
    for (const t of currentDecision.affected_tests || []) addNode(t.test, t.test?.split('.').slice(-1)[0], 'test')
    for (const r of currentDecision.reviewers || []) addNode(r.author, r.author, 'reviewer')

    return { nodes, edges }
  }, [currentDecision, subgraphData, graphOn])

  return (
    <div className="app">
      {/* TOP BAR */}
      <header className="topbar">
        <a className="topbar-brand" href="/" aria-label="ImpactGraph home">
          <div className="logo-dot" />
          ImpactGraph
        </a>

        <div className="topbar-controls">
          <select
            id="repo-select"
            value={repo}
            onChange={e => setRepo(e.target.value)}
            aria-label="Select repository"
          >
            {(repos || ['borgbase/vorta']).map(r => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>

          <input
            id="pr-number-input"
            type="number"
            placeholder="PR #"
            value={prInput}
            onChange={e => setPrInput(e.target.value)}
            style={{ width: 80 }}
            aria-label="PR number"
          />

          <button
            id="analyze-btn"
            className="btn btn-primary"
            onClick={handleAnalyze}
            disabled={isLoading || demoMode}
            type="button"
          >
            {isLoading ? <><div className="spinner" style={{ width: 14, height: 14 }} /> Analyzing…</> : '⚡ Analyze'}
          </button>

          <label className="toggle-wrap" htmlFor="dry-run-toggle" title="Dry run — log action without posting">
            <div
              id="dry-run-toggle"
              className={`toggle ${dryRun ? 'on' : ''}`}
              onClick={() => setDryRun(v => !v)}
              role="switch"
              aria-checked={dryRun}
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && setDryRun(v => !v)}
            />
            Dry-run
          </label>

          <label className="toggle-wrap" htmlFor="graph-toggle" title="Toggle graph visualization">
            <div
              id="graph-toggle"
              className={`toggle ${graphOn ? 'on' : ''}`}
              onClick={() => setGraphOn(v => !v)}
              role="switch"
              aria-checked={graphOn}
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && setGraphOn(v => !v)}
            />
            Graph
          </label>
        </div>

        {/* Demo mode controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
          {demoMode && (
            <select
              id="demo-id-select"
              value={demoId}
              onChange={e => setDemoId(Number(e.target.value))}
              aria-label="Demo PR"
            >
              {DEMO_IDS.map(id => <option key={id} value={id}>Demo PR {id}</option>)}
            </select>
          )}
          <button
            id="demo-mode-btn"
            className={`btn btn-sm ${demoMode ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setDemoMode(v => !v)}
            type="button"
          >
            {demoMode ? <span className="badge badge-demo">DEMO ON</span> : 'Demo'}
          </button>
        </div>
      </header>

      {/* MAIN WORKSPACE */}
      <main className="workspace">
        {/* LEFT PANEL */}
        <aside className="panel-left" aria-label="Analysis results">
          {!hasData && !isLoading ? (
            <div className="state-center">
              <div className="state-icon">🔬</div>
              <div className="state-title">Ready to Analyze</div>
              <div className="state-sub">
                Enter a PR number and click Analyze, or enable Demo mode to explore pre-computed results.
              </div>
              <button
                className="btn btn-ghost"
                onClick={() => setDemoMode(true)}
                type="button"
                id="try-demo-btn"
              >
                Try Demo Mode
              </button>
            </div>
          ) : isLoading ? (
            <div className="state-center">
              <div className="spinner" />
              <div className="state-title">Running impact analysis…</div>
              <div className="state-sub">Querying graph, computing blast radius, finding tests & reviewers.</div>
            </div>
          ) : (
            <>
              {/* Summary */}
              {currentDecision?.summary && (
                <div className="section">
                  <div className="ai-label">✦ AI-written summary</div>
                  <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    {currentDecision.summary}
                  </p>
                  {currentDecision.files_changed?.length > 0 && (
                    <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {currentDecision.files_changed.map(f => (
                        <span key={f} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: 4, padding: '2px 6px' }}>
                          {f}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Risk */}
              <RiskCard risk={currentDecision?.risk} />

              {/* Blast radius */}
              <BlastPanel
                blastRadius={currentDecision?.blast_radius}
                onSelect={setSelectedNodeId}
                selectedId={selectedNodeId}
              />

              {/* Tests */}
              <TestsPanel
                affectedTests={currentDecision?.affected_tests}
                onSelect={setSelectedNodeId}
                selectedId={selectedNodeId}
              />

              {/* Reviewers */}
              <ReviewersPanel reviewers={currentDecision?.reviewers} />

              {/* Ask the graph */}
              <AskBox repo={repo} />
            </>
          )}
        </aside>

        {/* RIGHT PANEL */}
        <section className="panel-right" aria-label="Graph and evidence">
          <nav className="tabs" aria-label="Right panel tabs">
            {[
              { id: 'graph',     label: '⬡ Graph' },
              { id: 'evidence',  label: '🔍 Evidence' },
              { id: 'benchmark', label: '📊 Benchmark' },
            ].map(t => (
              <button
                key={t.id}
                id={`tab-${t.id}-btn`}
                className={`tab-btn ${activeTab === t.id ? 'active' : ''}`}
                onClick={() => setActiveTab(t.id)}
                type="button"
                aria-selected={activeTab === t.id}
                role="tab"
              >
                {t.label}
              </button>
            ))}
          </nav>

          {activeTab === 'graph' && (
            graphOn ? (
              <div className="graph-canvas">
                <GraphCanvas
                  elements={graphElements}
                  selectedNodeId={selectedNodeId}
                  onNodeClick={handleNodeClick}
                />
              </div>
            ) : (
              <div className="flat-baseline">
                <h3 style={{ marginBottom: 16, color: 'var(--text-secondary)' }}>Graph OFF — Flat Baseline View</h3>
                {hasData ? (
                  <div className="baseline-compare">
                    <div className="baseline-box">
                      <div className="baseline-box-title">ImpactGraph Answer</div>
                      <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                        <strong>Blast:</strong> {currentDecision?.blast_radius?.length ?? 0} caller(s)<br />
                        <strong>Tests:</strong> {currentDecision?.affected_tests?.length ?? 0}<br />
                        <strong>Risk:</strong> {currentDecision?.risk?.label ?? '—'} ({currentDecision?.risk?.score?.toFixed(3) ?? '—'})<br />
                        <strong>Top reviewer:</strong> {currentDecision?.reviewers?.[0]?.author ?? '—'}
                      </div>
                    </div>
                    <div className="baseline-box">
                      <div className="baseline-box-title">Baseline (No Graph)</div>
                      <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6 }}>
                        <strong>Blast:</strong> Unknown<br />
                        <strong>Tests:</strong> Same-name file only<br />
                        <strong>Risk:</strong> Not computed<br />
                        <strong>Top reviewer:</strong> Last committer
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="state-center">
                    <div className="state-sub">Run an analysis to compare graph vs. flat baseline.</div>
                  </div>
                )}
              </div>
            )
          )}

          {activeTab === 'evidence' && (
            <EvidenceTab evidence={currentDecision?.evidence} />
          )}

          {activeTab === 'benchmark' && (
            <BenchmarkTab />
          )}
        </section>
      </main>
    </div>
  )
}
