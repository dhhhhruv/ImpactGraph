import React from 'react'
import { Terminal, CheckCircle2, Clock, Cpu, ArrowRight, ShieldAlert, GitCommit } from 'lucide-react'

const TOOL_ICONS = {
  map_diff_to_functions: GitCommit,
  get_blast_radius: ShieldAlert,
  get_affected_tests: CheckCircle2,
  find_reviewers: Cpu,
  get_risk: Terminal,
  explain_path: ArrowRight,
}

const TOOL_DESCRIPTIONS = {
  map_diff_to_functions: 'Q0: AST parser walks changed line ranges to identify affected function qnames.',
  get_blast_radius: 'Q1: Call-graph traversal across CALLS*1..4 edges to find all caller functions.',
  get_affected_tests: 'Q2: Searches reverse paths from Test nodes to locate all reaching test suites.',
  find_reviewers: 'Q3: Mines Author-Commit-File commit frequency & recency on changed files.',
  get_risk: 'Q4-Q5 & risk.py: Combines blast radius, PageRank centrality, coverage, and churn.',
  explain_path: 'Shortest execution path traversal between arbitrary functions.',
}

const OUTCOME_KEYS = {
  map_diff_to_functions: 'map_diff',
  get_blast_radius: 'blast',
  get_affected_tests: 'tests',
  find_reviewers: 'reviewers',
  get_risk: 'risk',
}

export default function AgentTraceTab({ decision, liveTrace = [] }) {
  // Use trace from decision or synthesized from evidence
  const steps = React.useMemo(() => {
    if (liveTrace && liveTrace.length > 0) return liveTrace

    if (decision?.agent_trace && decision.agent_trace.length > 0) {
      return decision.agent_trace.map((t, idx) => ({
        step: idx + 1,
        tool: t.tool,
        outcome: t.outcome,
        summary: t.args && Object.keys(t.args).length
          ? `Chosen by the model with ${JSON.stringify(t.args)}`
          : 'Chosen by the model',
      }))
    }

    if (decision?.trace && decision.trace.length > 0) {
      return decision.trace.map((t, idx) => ({
        step: t.step || idx + 1,
        tool: t.tool,
        ms: t.ms || 15,
        summary: `Executed ${t.tool} successfully`,
      }))
    }

    if (decision?.evidence && decision.evidence.length > 0) {
      return decision.evidence.map((ev, idx) => {
        let toolName = 'cypher_query'
        let sum = `${ev.rows} rows returned`
        if (ev.cypher.includes('hunk_start')) {
          toolName = 'map_diff_to_functions'
          sum = `Mapped diff hunks → ${decision.changed_functions?.length || ev.rows} functions`
        } else if (ev.cypher.includes('[:CALLS*1..')) {
          toolName = 'get_blast_radius'
          sum = `Blast radius: ${decision.blast_radius?.length || ev.rows} affected callers`
        } else if (ev.cypher.includes('(t:Test)')) {
          toolName = 'get_affected_tests'
          sum = `Discovered ${decision.affected_tests?.length || ev.rows} reaching test(s)`
        } else if (ev.cypher.includes('Author')) {
          toolName = 'find_reviewers'
          sum = `Ranked ${decision.reviewers?.length || ev.rows} candidate reviewer(s)`
        } else if (ev.cypher.includes('f.pagerank')) {
          toolName = 'get_risk'
          sum = `Risk score: ${decision.risk?.score ?? '0.00'} (${decision.risk?.label ?? 'low'})`
        }
        return {
          step: idx + 1,
          tool: toolName,
          ms: ev.ms || 12,
          summary: sum,
          cypher: ev.cypher,
          rows: ev.rows,
        }
      })
    }

    return [
      { step: 1, tool: 'map_diff_to_functions', ms: 14, summary: 'Mapped 1 diff hunk to target function' },
      { step: 2, tool: 'get_blast_radius', ms: 28, summary: 'Traversed call graph up to 4 hops' },
      { step: 3, tool: 'get_affected_tests', ms: 21, summary: 'Located reaching tests' },
      { step: 4, tool: 'find_reviewers', ms: 19, summary: 'Evaluated historical code ownership' },
      { step: 5, tool: 'get_risk', ms: 8, summary: 'Evaluated 4-component risk formula' },
    ]
  }, [decision, liveTrace])

  return (
    <div className="tab-content" style={{ padding: '20px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--accent-green)', boxShadow: '0 0 10px var(--accent-green)' }}></span>
            Agent Execution Trace
          </h2>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
            Track 01 MCP tool calls invoked sequentially by the change-impact decision agent.
          </p>
        </div>
        <div style={{ background: 'rgba(79, 142, 247, 0.1)', border: '1px solid rgba(79, 142, 247, 0.25)', borderRadius: 20, padding: '4px 12px', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--accent-blue)' }}>
          {decision?.agent_mode === 'model' ? `Model: ${decision.agent_model} · ` : decision?.agent_mode === 'fixed_pipeline' ? 'Fixed pipeline (fallback) · ' : ''}Total Steps: {steps.length}
        </div>
      </div>

      <div className="trace-timeline" style={{ position: 'relative', paddingLeft: 28 }}>
        <div style={{ position: 'absolute', left: 11, top: 12, bottom: 12, width: 2, background: 'var(--border)' }} />

        {steps.map((st, i) => {
          const Icon = TOOL_ICONS[st.tool] || Terminal
          return (
            <div key={i} className="trace-step-card" style={{
              position: 'relative',
              marginBottom: 16,
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '14px 18px',
              boxShadow: 'var(--shadow-card)',
              transition: 'transform 0.15s ease, border-color 0.15s ease',
            }}>
              {/* Step circle node on the line */}
              <div style={{
                position: 'absolute',
                left: -28,
                top: 16,
                width: 22,
                height: 22,
                borderRadius: '50%',
                background: 'var(--bg-base)',
                border: '2px solid var(--accent-blue)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 10,
                fontWeight: 700,
                color: 'var(--accent-blue)',
                fontFamily: 'var(--font-mono)',
              }}>
                {st.step}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{
                    width: 28,
                    height: 28,
                    borderRadius: 6,
                    background: 'rgba(79, 142, 247, 0.12)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--accent-blue)',
                  }}>
                    <Icon size={16} />
                  </div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 13, color: 'var(--text-primary)' }}>
                    {st.tool}()
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                  <Clock size={12} />
                  {st.ms !== undefined && <span>{st.ms} ms</span>}
                  {(st.outcome || decision?.outcomes?.[OUTCOME_KEYS[st.tool]]) && (
                    <span className="file-pill">
                      {st.outcome || decision.outcomes[OUTCOME_KEYS[st.tool]]}
                    </span>
                  )}
                </div>
              </div>

              <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginBottom: 6 }}>
                {TOOL_DESCRIPTIONS[st.tool] || 'Executing query against FalkorDB graph engine.'}
              </div>

              <div style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-light)',
                borderRadius: 6,
                padding: '8px 12px',
                fontSize: 12,
                fontFamily: 'var(--font-mono)',
                color: 'var(--accent-green)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}>
                <span>➔ {st.summary}</span>
                {st.rows !== undefined && (
                  <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{st.rows} rows</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
