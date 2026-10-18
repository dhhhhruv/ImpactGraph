import React, { useState, useCallback, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { fetchRepos, fetchRepoPrs, fetchDemo, fetchSubgraph, analyzeChange } from './api'
import RiskCard from './components/RiskCard'
import BlastPanel from './components/BlastPanel'
import TestsPanel from './components/TestsPanel'
import ReviewersPanel from './components/ReviewersPanel'
import AskBox from './components/AskBox'
import GraphCanvas from './components/GraphCanvas'
import EvidenceTab from './components/EvidenceTab'
import BenchmarkTab from './components/BenchmarkTab'
import AgentTraceTab from './components/AgentTraceTab'
import { 
  Sparkles, 
  Activity, 
  GitPullRequest, 
  Database, 
  Layers, 
  ShieldAlert, 
  Code2, 
  Terminal, 
  CheckCircle2, 
  BarChart3,
  Search
} from 'lucide-react'

const PR_DIFF_MAP = {
  2560: [{ path: 'src/vorta/scheduler/execution.py', start: 49, end: 106 }],
  1: [{ path: 'src/vorta/scheduler/execution.py', start: 5, end: 25 }],
  2: [{ path: 'src/vorta/borg/borg_job.py', start: 225, end: 250 }],
  3: [{ path: 'src/vorta/network_status/network_manager.py', start: 150, end: 160 }],
  4: [{ path: 'src/vorta/borg/borg_job.py', start: 50, end: 120 }],
  5: [{ path: 'src/vorta/views/dialogs/archive/exclude.py', start: 278, end: 296 }],
}

export default function App() {
  // Controls
  const [repo, setRepo] = useState('borgbase/vorta')
  const [selectedPrNumber, setSelectedPrNumber] = useState('2560')
  const [graphOn, setGraphOn] = useState(true)
  const [demoMode, setDemoMode] = useState(true)
  const [dryRun, setDryRun] = useState(false)
  const [hopDepth, setHopDepth] = useState(4)

  // Selection state
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [activeTab, setActiveTab] = useState('graph') // 'graph' | 'trace' | 'evidence' | 'benchmark'

  // Data state
  const [decision, setDecision] = useState(null)
  const [subgraphData, setSubgraphData] = useState(null)
  const [liveTrace, setLiveTrace] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)

  // Repos list
  const { data: repos } = useQuery({ queryKey: ['repos'], queryFn: fetchRepos })

  // PRs list for selector
  const { data: repoPrs } = useQuery({
    queryKey: ['repoPrs', repo],
    queryFn: () => fetchRepoPrs(repo),
  })

  // Demo query for selected PR
  const { data: demoData, isLoading: demoLoading } = useQuery({
    queryKey: ['demo', selectedPrNumber, hopDepth],
    queryFn: () => fetchDemo(Number(selectedPrNumber) || 1, hopDepth),
    enabled: demoMode,
  })

  // When demo loads, update decision
  useEffect(() => {
    if (demoMode && demoData?.decision) {
      setDecision(demoData.decision)
      setSubgraphData(null)
      setLiveTrace([])
    }
  }, [demoMode, demoData])

  // Normal Analyze mutation (non-streaming fallback)
  const analyzeMutation = useMutation({
    mutationFn: analyzeChange,
    onSuccess: async (data, variables) => {
      setDecision(data.decision)
      if (data.decision?.changed_functions?.length) {
        const sg = await fetchSubgraph(
          repo,
          data.decision.changed_functions,
          data.decision.max_hops ?? variables.maxHops ?? hopDepth,
        )
        setSubgraphData(sg)
      }
    },
  })

  // Re-run subgraph when hop depth changes (demo moment: depth 1 vs 4)
  useEffect(() => {
    if (!decision?.changed_functions?.length || !graphOn) return
    if (demoMode) {
      setSubgraphData(null)
      return
    }
    let cancelled = false
    fetchSubgraph(repo, decision.changed_functions, hopDepth).then((sg) => {
      if (!cancelled) setSubgraphData(sg)
    })
    return () => { cancelled = true }
  }, [hopDepth, repo, graphOn, demoMode]) // eslint-disable-line react-hooks/exhaustive-deps

  // SSE Live streaming analysis
  const handleAnalyzeStreaming = useCallback(() => {
    if (dryRun) {
      alert(`[Dry-run] Simulated analysis for ${repo} PR #${selectedPrNumber}. No external actions will be posted to GitHub.`)
      return
    }

    setDemoMode(false)
    setIsStreaming(true)
    setLiveTrace([])
    setActiveTab('trace')

    const prNum = Number(selectedPrNumber) || 1
    const hunks = PR_DIFF_MAP[prNum] || PR_DIFF_MAP[1]
    const hunk = hunks[0]
    const path = hunk.path
    const start = hunk.start
    const end = hunk.end
    const url = `/api/analyze/stream?repo=${encodeURIComponent(repo)}&path=${encodeURIComponent(path)}&start=${start}&end=${end}&head_sha=pr-${selectedPrNumber}&max_hops=${hopDepth}`
    const eventSource = new EventSource(url)

    eventSource.addEventListener('tool_start', (e) => {
      try {
        const data = JSON.parse(e.data)
        setLiveTrace((prev) => [
          ...prev,
          {
            step: prev.length + 1,
            tool: data.tool,
            ms: 0,
            summary: `Calling ${data.tool}...`,
            status: 'running',
          },
        ])
      } catch (err) {
        console.error(err)
      }
    })

    eventSource.addEventListener('tool_result', (e) => {
      try {
        const data = JSON.parse(e.data)
        setLiveTrace((prev) => {
          const updated = [...prev]
          const lastIdx = updated.findIndex((s) => s.tool === data.tool && s.status === 'running')
          const sum = data.count !== undefined 
            ? `Returned ${data.count} result(s)` 
            : data.score !== undefined 
            ? `Risk calculated: ${data.score} (${data.label})` 
            : `Completed in ${data.ms}ms`
          if (lastIdx !== -1) {
            updated[lastIdx] = {
              ...updated[lastIdx],
              ms: data.ms,
              summary: sum,
              status: 'done',
              outcome: data.outcome,
            }
          }
          return updated
        })
      } catch (err) {
        console.error(err)
      }
    })

    eventSource.addEventListener('decision', async (e) => {
      try {
        const payload = JSON.parse(e.data)
        setDecision(payload.decision)
        setIsStreaming(false)
        eventSource.close()

        if (payload.decision?.changed_functions?.length) {
          const sg = await fetchSubgraph(repo, payload.decision.changed_functions, hopDepth)
          setSubgraphData(sg)
        }
      } catch (err) {
        console.error(err)
        setIsStreaming(false)
        eventSource.close()
      }
    })

    eventSource.onerror = (err) => {
      console.warn('SSE stream closed or error, falling back to standard analyze', err)
      setIsStreaming(false)
      eventSource.close()
      const prNum = Number(selectedPrNumber) || 1
      analyzeMutation.mutate({
        repo,
        diffHunks: PR_DIFF_MAP[prNum] || PR_DIFF_MAP[1],
        headSha: `pr-${selectedPrNumber}`,
        maxHops: hopDepth,
      })
    }
  }, [repo, selectedPrNumber, dryRun, analyzeMutation, hopDepth])

  const handleNodeClick = useCallback((id) => {
    setSelectedNodeId(id)
  }, [])

  const currentDecision = decision
  const handleHopDepthChange = useCallback((depth) => {
    setHopDepth(depth)
    if (!demoMode && decision) {
      const prNum = Number(selectedPrNumber) || 1
      analyzeMutation.mutate({
        repo,
        diffHunks: PR_DIFF_MAP[prNum] || PR_DIFF_MAP[1],
        headSha: `pr-${selectedPrNumber}`,
        maxHops: depth,
      })
    }
  }, [demoMode, decision, selectedPrNumber, repo, analyzeMutation])
  const isLoading = (demoMode && demoLoading) || analyzeMutation.isPending || isStreaming
  const hasData = !!currentDecision

  // Build Cytoscape graph elements
  const graphElements = React.useMemo(() => {
    if (!graphOn) return null
    if (subgraphData?.elements) return subgraphData.elements
    if (!currentDecision) return null

    const nodes = []
    const edges = []
    const seenEdges = new Set()
    const seen = new Set()

    const addNode = (id, label, type) => {
      if (!id || seen.has(id)) return
      seen.add(id)
      nodes.push({ data: { id, label: label || id.split('.').slice(-1)[0], full_qname: id, type } })
    }

    for (const fn of currentDecision.changed_functions || []) {
      addNode(fn, fn.split('.').slice(-1)[0], 'changed')
    }
    const addPath = (path, isEvidence = false) => {
      for (let i = 0; i < path.length - 1; i++) {
        addNode(path[i], path[i]?.split('.').slice(-1)[0], 'caller')
        addNode(path[i + 1], path[i + 1]?.split('.').slice(-1)[0], 'caller')
        const edgeId = `${path[i]}->${path[i + 1]}`
        if (!seenEdges.has(edgeId)) {
          seenEdges.add(edgeId)
          edges.push({
            data: {
              id: edgeId,
              source: path[i],
              target: path[i + 1],
              ...(isEvidence ? { type: 'evidence' } : {}),
            },
          })
        } else if (isEvidence) {
          const existingEdge = edges.find((edge) => edge.data.id === edgeId)
          if (existingEdge) existingEdge.data.type = 'evidence'
        }
      }
    }
    for (const row of currentDecision.blast_radius || []) {
      addNode(row.affected, row.affected?.split('.').slice(-1)[0], 'caller')
      addPath(row.path || [])
    }
    for (const t of currentDecision.affected_tests || []) {
      addNode(t.test, t.test?.split('.').slice(-1)[0], 'test')
    }
    for (const path of Object.values(currentDecision.test_proof_paths || {})) {
      addPath(path, true)
    }
    

    return { nodes, edges }
  }, [currentDecision, subgraphData, graphOn])

  // Affected-test count; the query is capped at 30, so 30 means "30 or more"
  const testTotal = (currentDecision?.affected_tests?.length || 0)
  const testCountLabel = testTotal >= 30 ? '30 or more' : String(testTotal)

  return (
    <div className="app">
      {/* TOP HEADER */}
      <header className="topbar">
        <a className="topbar-brand" href="/" aria-label="ImpactGraph home">
          <div className="logo-dot" />
          <span style={{ letterSpacing: '-0.02em' }}>ImpactGraph</span>
          <span className="badge-track">Track 01</span>
        </a>

        <div className="topbar-controls">
          {/* Repo selector */}
          <div className="input-group">
            <span className="input-icon"><Layers size={14} /></span>
            <select
              id="repo-select"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              aria-label="Select repository"
            >
              {(repos || ['borgbase/vorta']).map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          {/* PR Selector */}
          <div className="input-group">
            <span className="input-icon"><GitPullRequest size={14} /></span>
            <select
              id="pr-select"
              value={selectedPrNumber}
              onChange={(e) => {
                setSelectedPrNumber(e.target.value)
                setDemoMode(true)
              }}
              aria-label="Select Pull Request"
              style={{ minWidth: 160 }}
            >
              {(repoPrs || [
                { number: 2560, title: 'extract Execution and close the job lifecycle' },
                { number: 1, title: 'Fix backup path handling in scheduler' },
                { number: 2, title: 'Refactor BorgJob execution & cancel' },
                { number: 3, title: 'Update DBus network monitor integration' },
                { number: 4, title: 'Core borg process & credential security' },
                { number: 5, title: 'Exclude pattern matching & diff parser' },
              ]).map((pr) => (
                <option key={pr.number} value={pr.number}>
                  PR #{pr.number} · {pr.title.slice(0, 26)}…
                </option>
              ))}
            </select>
          </div>

          {/* Live Analyze Button */}
          <button
            id="analyze-btn"
            className="btn btn-primary"
            onClick={handleAnalyzeStreaming}
            disabled={isLoading}
            type="button"
          >
            {isLoading ? (
              <>
                <div className="spinner" style={{ width: 14, height: 14 }} />
                <span>Analyzing…</span>
              </>
            ) : (
              <>
                <Sparkles size={14} />
                <span>⚡ Analyze Impact</span>
              </>
            )}
          </button>

          {/* Dry Run Switch */}
          <label className="toggle-wrap" htmlFor="dry-run-toggle" title="Dry run — evaluate decisions without modifying GitHub">
            <div
              id="dry-run-toggle"
              className={`toggle ${dryRun ? 'on' : ''}`}
              onClick={() => setDryRun((v) => !v)}
              role="switch"
              aria-checked={dryRun}
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && setDryRun((v) => !v)}
            />
            <span>Dry-run</span>
          </label>

          {/* Graph Toggle */}
          <label className="toggle-wrap" htmlFor="graph-toggle" title="Toggle FalkorDB Graph vs Flat Baseline">
            <div
              id="graph-toggle"
              className={`toggle ${graphOn ? 'on' : ''}`}
              onClick={() => setGraphOn((v) => !v)}
              role="switch"
              aria-checked={graphOn}
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && setGraphOn((v) => !v)}
            />
            <span>Graph {graphOn ? 'ON' : 'OFF'}</span>
          </label>

          {/* Hop depth — demo moment: same question at depth 1 then 4 */}
          <div className="toggle-wrap" title="Call-graph hop depth for blast / tests">
            <span style={{ marginRight: 6 }}>Hop depth</span>
            <button
              type="button"
              className={`btn btn-sm ${hopDepth === 1 ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => handleHopDepthChange(1)}
              id="hop-depth-1"
            >
              1
            </button>
            <button
              type="button"
              className={`btn btn-sm ${hopDepth === 4 ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => handleHopDepthChange(4)}
              id="hop-depth-4"
              style={{ marginLeft: 4 }}
            >
              4
            </button>
          </div>
        </div>

        {/* Demo Mode Badge and Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginLeft: 'auto' }}>
          <div className="status-pill">
            <Database size={13} style={{ color: 'var(--accent-green)' }} />
            <span>FalkorDB Connected</span>
          </div>

          <button
            id="demo-mode-btn"
            className={`btn btn-sm ${demoMode ? 'btn-demo-active' : 'btn-ghost'}`}
            onClick={() => setDemoMode((v) => !v)}
            type="button"
            title="Toggle between instant pre-computed demo PRs and live query mode"
          >
            {demoMode ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span className="live-dot" /> DEMO CACHE ON
              </span>
            ) : (
              'Live Mode'
            )}
          </button>
        </div>
      </header>

      {/* MAIN WORKSPACE */}
      <main className="workspace">
        {/* LEFT PANEL (40%) */}
        <aside className="panel-left" aria-label="Analysis results">
          {!hasData && !isLoading ? (
            <div className="state-center">
              <div className="state-icon">🔬</div>
              <div className="state-title">Ready to Analyze</div>
              <div className="state-sub">
                Select a PR above and click <strong>⚡ Analyze Impact</strong>, or explore the pre-indexed demo PR scenarios.
              </div>
              <button
                className="btn btn-primary"
                onClick={() => setDemoMode(true)}
                type="button"
                id="try-demo-btn"
                style={{ marginTop: 12 }}
              >
                Explore Demo PR #1
              </button>
            </div>
          ) : isLoading && !hasData ? (
            <div className="state-center">
              <div className="spinner" />
              <div className="state-title">Querying FalkorDB Graph…</div>
              <div className="state-sub">Traversing call graph, discovering affected tests & mining reviewer git recency.</div>
            </div>
          ) : (
            <>
              {/* AI-written summary card */}
              {currentDecision?.summary && (
                <div className="section ai-summary-card">
                  <div className="ai-label">
                    <Sparkles size={13} />
                    <span>Evidence-Bound Summary</span>
                  </div>
                  <p className="ai-summary-text">
                    {currentDecision.summary}
                  </p>
                  <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
                    Built from the query results by a fixed template. No language model is called.
                  </p>
                  {(currentDecision.outcome || currentDecision.outcomes) && (
                    <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      <span className="file-pill">outcome: {currentDecision.outcome || '—'}</span>
                      {currentDecision.outcomes && Object.entries(currentDecision.outcomes).map(([k, v]) => (
                        <span key={k} className="file-pill">{k}: {v}</span>
                      ))}
                      <span className="file-pill">hops: {hopDepth}</span>
                    </div>
                  )}
                  {currentDecision.files_changed?.length > 0 && (
                    <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {currentDecision.files_changed.map((f) => (
                        <span key={f} className="file-pill">
                          <Code2 size={12} />
                          {f}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Risk Gauge & Breakdown Card */}
              <RiskCard risk={currentDecision?.risk} />

              {/* Blast Radius Panel */}
              <BlastPanel
                blastRadius={currentDecision?.blast_radius}
                onSelect={setSelectedNodeId}
                selectedId={selectedNodeId}
              />

              {/* Affected Tests Panel */}
              <TestsPanel
                affectedTests={currentDecision?.affected_tests}
                onSelect={setSelectedNodeId}
                selectedId={selectedNodeId}
              />

              {/* Suggested Reviewers Panel */}
              <ReviewersPanel reviewers={currentDecision?.reviewers} />

              {/* Ask the Graph Box */}
              <AskBox repo={repo} />
            </>
          )}
        </aside>

        {/* RIGHT PANEL (60%) */}
        <section className="panel-right" aria-label="Graph and evidence">
          <nav className="tabs" aria-label="Right panel tabs">
            {[
              { id: 'graph', label: '⬡ Graph Canvas', icon: Activity },
              { id: 'trace', label: '⚡ Agent Trace', icon: Terminal },
              { id: 'evidence', label: '🔍 Evidence (Cypher)', icon: Search },
              { id: 'benchmark', label: '📊 Benchmark', icon: BarChart3 },
            ].map((t) => {
              const TabIcon = t.icon
              return (
                <button
                  key={t.id}
                  id={`tab-${t.id}-btn`}
                  className={`tab-btn ${activeTab === t.id ? 'active' : ''}`}
                  onClick={() => setActiveTab(t.id)}
                  type="button"
                  aria-selected={activeTab === t.id}
                  role="tab"
                >
                  <TabIcon size={14} />
                  <span>{t.label}</span>
                </button>
              )
            })}
          </nav>

          {/* TAB 1: GRAPH CANVAS */}
          {activeTab === 'graph' && (
            graphOn ? (
              <div className="graph-canvas-wrapper" style={{ height: 'calc(100% - 45px)', display: 'flex', flexDirection: 'column' }}>
                <div className="graph-canvas-bar">
                  <div className="legend-items">
                    <span className="legend-pill" style={{ '--dot-color': 'var(--node-changed)' }}>Changed Function</span>
                    <span className="legend-pill" style={{ '--dot-color': 'var(--node-caller)' }}>Affected Caller (Blast)</span>
                    <span className="legend-pill" style={{ '--dot-color': 'var(--node-test)' }}>Reaching Test</span>
                    
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {graphElements?.nodes?.length || 0} nodes · fcose physics layout
                  </div>
                </div>

                <div className="graph-canvas" style={{ flex: 1, position: 'relative' }}>
                  <GraphCanvas
                    elements={graphElements}
                    selectedNodeId={selectedNodeId}
                    onNodeClick={handleNodeClick}
                  />
                </div>
              </div>
            ) : (
              /* GRAPH OFF: Baseline Comparison View */
              <div className="flat-baseline-container">
                <div className="flat-baseline-header">
                  <ShieldAlert size={20} style={{ color: 'var(--accent-orange)' }} />
                  <div>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                      Graph OFF — Ablation Baseline Comparison
                    </h3>
                    <p style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginTop: 2 }}>
                      Comparing graph traversal against flat heuristics on this PR.
                    </p>
                  </div>
                </div>

                {hasData ? (
                  <div>
                    <div className="baseline-delta-callout">
                      <Sparkles size={16} style={{ color: 'var(--accent-blue)', flexShrink: 0 }} />
                      <div>
                        <strong>Graph Advantage:</strong> Found <strong>{testCountLabel} affected test(s)</strong> by walking CALLS edges back from the changed code; a same-name heuristic only looks for test_*.py by file name.
                        On reviewers, a plain commit-count ranking performed about the same as the graph in the 40-PR benchmark.
                      </div>
                    </div>

                    <div className="baseline-grid">
                      <div className="baseline-card graph-advantage-card">
                        <div className="baseline-card-header">
                          <span className="badge badge-graph">FalkorDB Connected Engine</span>
                          <span style={{ fontSize: 11, color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)' }}>Full Multi-Hop</span>
                        </div>
                        <ul className="baseline-list">
                          <li><strong>Blast Radius:</strong> {currentDecision?.blast_radius?.length || 0} callers reached via CALLS edges</li>
                          <li><strong>Tests to Run:</strong> {testCountLabel} discovered by backward search from Test nodes</li>
                          <li><strong>Risk Score:</strong> Objective formula: {currentDecision?.risk?.score} ({currentDecision?.risk?.label?.toUpperCase()})</li>
                          <li><strong>Reviewer:</strong> {currentDecision?.reviewers?.[0]?.author || '—'} (weighted by files covered & recency)</li>
                        </ul>
                      </div>

                      <div className="baseline-card flat-heuristic-card">
                        <div className="baseline-card-header">
                          <span className="badge badge-baseline">Flat Baseline (No Graph)</span>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>Regex / Heuristic</span>
                        </div>
                        <ul className="baseline-list">
                          <li><strong>Blast Radius:</strong> Unknown (cannot traverse multi-hop callers)</li>
                          <li><strong>Tests to Run:</strong> Same-name heuristic only (test_*.py)</li>
                          <li><strong>Risk Score:</strong> None (no PageRank centrality or blast ratio)</li>
                          <li><strong>Reviewer:</strong> Most recent committer, or raw commit count (about equal to the graph in the benchmark)</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="state-center">
                    <div className="state-sub">Run an analysis to inspect graph vs. flat baseline ablation.</div>
                  </div>
                )}
              </div>
            )
          )}

          {/* TAB 2: AGENT TRACE TIMELINE */}
          {activeTab === 'trace' && (
            <AgentTraceTab decision={currentDecision} liveTrace={liveTrace} />
          )}

          {/* TAB 3: EVIDENCE (CYPHER QUERIES) */}
          {activeTab === 'evidence' && (
            <EvidenceTab evidence={currentDecision?.evidence} />
          )}

          {/* TAB 4: BENCHMARK */}
          {activeTab === 'benchmark' && (
            <BenchmarkTab />
          )}
        </section>
      </main>
    </div>
  )
}
