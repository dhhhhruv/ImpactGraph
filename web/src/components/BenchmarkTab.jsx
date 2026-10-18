import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchBenchmark } from '../api'

const LABELS = {
  graph: 'ImpactGraph',
  flat_commit_count: 'Flat commit count',
  most_recent_committer: 'Most recent committer',
  same_name_test: 'Same-name test file',
  grep_imports: 'Grep imports',
  llm_only: 'Title/@mention heuristic (no LLM)',
}
const BAR_CLASS = { graph: 'graph', llm_only: 'llm' }
const REVIEWER_METHODS = ['graph', 'flat_commit_count', 'most_recent_committer', 'llm_only']
const TEST_METHODS = ['graph', 'grep_imports', 'same_name_test', 'llm_only']

const pct = v => (v == null ? '—' : Math.round(v * 100) + '%')
const dec = v => (v == null ? '—' : Number(v).toFixed(2))
const tick = v => (v == null ? '—' : v > 0 ? '✓' : '✗')

function BarGroup({ title, methods, field, keys }) {
  return (
    <div className="bench-row">
      <div className="bench-label"><span>{title}</span></div>
      {keys.filter(k => methods[k]).map(k => {
        const val = methods[k][field]
        return (
          <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 190, fontSize: 11, color: 'var(--text-muted)', textAlign: 'right', flexShrink: 0 }}>{LABELS[k]}</div>
            <div className="bench-bar-bg" style={{ flex: 1 }}>
              <div className={'bench-bar ' + (BAR_CLASS[k] || 'baseline')} style={{ width: (val || 0) * 100 + '%' }} />
            </div>
            <div style={{ width: 40, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', textAlign: 'right' }}>{pct(val)}</div>
          </div>
        )
      })}
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

  const methods = data?.methods || {}
  const g = methods.graph
  const prs = data?.per_pr || []

  if (!g) return (
    <div className="state-center"><div className="state-title">No benchmark results found</div><div className="state-sub">{data?.message || 'Generate benchmark/results.json first.'}</div></div>
  )

  const tiles = [
    { label: 'PRs evaluated', val: g.n_prs },
    { label: 'PRs with test edits', val: g.n_with_test_changes },
    { label: 'Avg tests suggested by graph (PRs with test edits)', val: g.avg_tests_suggested_with_tests != null ? Number(g.avg_tests_suggested_with_tests).toFixed(1) : '—' },
  ]

  return (
    <div className="tab-content">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <h2>Benchmark Results</h2>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          borgbase/vorta · {g.n_prs} PRs{data.generated_at ? ' · generated ' + new Date(data.generated_at).toLocaleString() : ''}
        </span>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <h3 style={{ marginBottom: 16, color: 'var(--text-secondary)' }}>Summary Metrics</h3>
        <BarGroup title="Reviewer hit@3 (is a real reviewer in the top 3?)" methods={methods} field="reviewer_hit_at_3" keys={REVIEWER_METHODS} />
        <BarGroup title="Test recall@5 (PRs that edited tests)" methods={methods} field="test_recall_at_5_with_tests" keys={TEST_METHODS} />
        <div style={{ marginTop: 12, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {tiles.map(s => (
            <div key={s.label} style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 16px', textAlign: 'center' }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)' }}>{s.val}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <h3 style={{ marginBottom: 12, color: 'var(--text-secondary)' }}>All methods</h3>
        <div style={{ overflowX: 'auto' }}>
          <table className="pr-table">
            <thead>
              <tr><th>Method</th><th>Hit@3</th><th>Hit@5</th><th>MRR</th><th>Test recall@5</th></tr>
            </thead>
            <tbody>
              {Object.keys(LABELS).filter(k => methods[k]).map(k => {
                const x = methods[k]
                const hasRev = REVIEWER_METHODS.includes(k)
                const hasTests = TEST_METHODS.includes(k)
                return (
                  <tr key={k}>
                    <td style={{ color: 'var(--text-primary)' }}>{LABELS[k]}</td>
                    <td>{hasRev ? dec(x.reviewer_hit_at_3) : '—'}</td>
                    <td>{hasRev ? dec(x.reviewer_hit_at_5) : '—'}</td>
                    <td>{hasRev ? dec(x.reviewer_mrr) : '—'}</td>
                    <td>{hasTests ? dec(x.test_recall_at_5_with_tests) : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
          — means the method does not produce that kind of answer.
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
                  <th>Title</th>
                  <th>Graph hit@3</th>
                  <th>Flat count hit@3</th>
                  <th>Graph tests suggested</th>
                  <th>Graph test recall@5</th>
                  <th>Grep-imports recall@5</th>
                </tr>
              </thead>
              <tbody>
                {prs.map(pr => {
                  const pm = pr.methods || {}
                  const recall = k => (pr.has_test_changes ? pct(pm[k]?.tests?.recall_at_5) : 'n/a')
                  return (
                    <tr key={pr.number}>
                      <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>#{pr.number}</td>
                      <td title={pr.title}>{(pr.title || '').slice(0, 70)}</td>
                      <td style={{ color: pm.graph?.reviewers?.hit_at_3 > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>{tick(pm.graph?.reviewers?.hit_at_3)}</td>
                      <td style={{ color: pm.flat_commit_count?.reviewers?.hit_at_3 > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>{tick(pm.flat_commit_count?.reviewers?.hit_at_3)}</td>
                      <td>{pm.graph?.tests?.num_suggested ?? '—'}</td>
                      <td>{recall('graph')}</td>
                      <td>{recall('grep_imports')}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
            n/a = the PR did not edit any tests, so test recall is not defined.
          </div>
        </div>
      )}

      <div className="card" style={{ background: 'rgba(79,142,247,0.05)', borderColor: 'rgba(79,142,247,0.2)' }}>
        <h3 style={{ marginBottom: 10, color: 'var(--accent-blue)' }}>Method & Limitations</h3>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          <p style={{ marginBottom: 8 }}>
            PRs were selected before looking at results, using the rule in <code style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>benchmark/SELECTION_RULE.md</code>.
            Reviewer history uses only commits strictly before each PR's merge time.
          </p>
          <p style={{ marginBottom: 8 }}>
            <strong>Baselines:</strong> most recent committer and flat commit count (reviewers); same-name test file and grep imports (tests);
            and a title/@mention heuristic that stands in for an LLM with no graph evidence. No language model is called in this benchmark.
          </p>
          <p style={{ marginBottom: 8 }}>
            <strong>Scope:</strong> 40 PRs from one repository, so small differences should not be over-read. The graph and flat commit count are
            essentially equal on reviewers, and grep imports is slightly ahead on test recall. Each changed file is mapped to all of its functions
            (whole file), so these numbers are not comparable with the single-function demo. Test suggestions are capped at 30 per query.
          </p>
          <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            Call links are name-based and approximate (constructors and Qt signal connections are not modelled); a 15-function hand check is in
            <code style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}> benchmark/spotcheck.md</code>. Git emails were mapped to GitHub logins
            (90 of 95 resolved) to match ground truth.
          </p>
        </div>
      </div>
    </div>
  )
}
