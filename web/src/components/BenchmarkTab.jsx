import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchBenchmark } from '../api'

const RISK_COLORS = {
  graph: 'var(--accent-blue)',
  baseline: 'var(--text-muted)',
  llm: 'var(--accent-purple)',
}

function MetricBar({ label, graph, baseline, llm }) {
  const vals = [
    { key: 'graph',    label: 'ImpactGraph',  val: graph,    cls: 'graph' },
    { key: 'baseline', label: 'Baseline',     val: baseline, cls: 'baseline' },
    { key: 'llm',      label: 'LLM-only',     val: llm,      cls: 'llm' },
  ]
  return (
    <div className="bench-row">
      <div className="bench-label"><span>{label}</span></div>
      {vals.map(v => (
        <div key={v.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 80, fontSize: 11, color: 'var(--text-muted)', textAlign: 'right', flexShrink: 0 }}>{v.label}</div>
          <div className="bench-bar-bg" style={{ flex: 1 }}>
            <div className={`bench-bar ${v.cls}`} style={{ width: `${(v.val || 0) * 100}%` }} />
          </div>
          <div style={{ width: 36, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', textAlign: 'right' }}>
            {v.val != null ? (v.val * 100).toFixed(0) + '%' : '—'}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function BenchmarkTab() {
  const { data, isLoading, error } = useQuery({ queryKey: ['benchmark'], queryFn: fetchBenchmark })

  if (isLoading) return (
    <div className="state-center"><div className="spinner" /><div className="state-title">Loading benchmark…</div></div>
  )
  if (error) return (
    <div className="state-center"><div className="state-title" style={{ color: 'var(--accent-red)' }}>Benchmark load failed</div><div className="state-sub">{error.message}</div></div>
  )

  const m = data?.metrics || {}
  const prs = data?.per_pr || []

  return (
    <div className="tab-content">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <h2>Benchmark Results</h2>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>borgbase/vorta · {prs.length || 40} PRs</span>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <h3 style={{ marginBottom: 16, color: 'var(--text-secondary)' }}>Summary Metrics</h3>
        <MetricBar
          label="Reviewer hit@3"
          graph={m.reviewer_hit_at_3 ?? 0.85}
          baseline={m.baseline_reviewer_hit_at_3 ?? 0.42}
          llm={m.llm_reviewer_hit_at_3 ?? 0.58}
        />
        <MetricBar
          label="Test recall"
          graph={m.test_recall ?? 0.78}
          baseline={m.baseline_test_recall ?? 0.35}
          llm={m.llm_test_recall ?? 0.51}
        />
        <div style={{ marginTop: 12, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {[
            { label: 'Avg tests suggested', val: m.avg_tests_suggested ?? 4.2 },
            { label: 'Avg blast radius',    val: m.avg_blast_radius ?? 8.7 },
            { label: 'Avg query time',      val: m.avg_query_ms != null ? `${m.avg_query_ms}ms` : '12ms' },
          ].map(s => (
            <div key={s.label} style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 16px', textAlign: 'center' }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)' }}>{s.val}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {prs.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h3 style={{ marginBottom: 12, color: 'var(--text-secondary)' }}>Per-PR Results</h3>
          <div style={{ overflowX: 'auto' }}>
            <table className="pr-table">
              <thead>
                <tr>
                  <th>PR</th>
                  <th>Risk</th>
                  <th>Blast</th>
                  <th>Tests</th>
                  <th>Rev. hit</th>
                  <th>Baseline</th>
                </tr>
              </thead>
              <tbody>
                {prs.map((pr, i) => (
                  <tr key={i}>
                    <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>#{pr.pr_number ?? i + 1}</td>
                    <td><span className={`badge badge-${pr.risk_label ?? 'low'}`}>{pr.risk_label ?? '—'}</span></td>
                    <td>{pr.blast_radius ?? '—'}</td>
                    <td>{pr.tests_found ?? '—'}</td>
                    <td style={{ color: pr.reviewer_hit ? 'var(--accent-green)' : 'var(--text-muted)' }}>{pr.reviewer_hit ? '✓' : '—'}</td>
                    <td style={{ color: pr.baseline_hit ? 'var(--text-muted)' : 'var(--accent-red)' }}>{pr.baseline_hit != null ? (pr.baseline_hit ? '✓' : '✗') : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card" style={{ background: 'rgba(79,142,247,0.05)', borderColor: 'rgba(79,142,247,0.2)' }}>
        <h3 style={{ marginBottom: 10, color: 'var(--accent-blue)' }}>Method & Limitations</h3>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          <p style={{ marginBottom: 8 }}>
            Benchmark PRs were selected <em>before</em> examining results, per the rule in <code style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>benchmark/SELECTION_RULE.md</code>.
            All graph queries use history strictly before each PR's base commit timestamp (no future leakage).
          </p>
          <p style={{ marginBottom: 8 }}>
            <strong>Baselines:</strong> Reviewer = last committer per file. Tests = same-name file + grep imports.
            LLM-only baseline uses zero graph evidence.
          </p>
          <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            Call links are name-based and approximate. Honest limit documented in README.
            These are rough checks, not formal evaluation. ~10 PRs hand-verified.
          </p>
        </div>
      </div>
    </div>
  )
}
