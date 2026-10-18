import React from 'react'
import CopyBtn from './CopyBtn'

export default function EvidenceTab({ evidence }) {
  if (!evidence || evidence.length === 0) {
    return (
      <div className="state-center">
        <div className="state-icon">🔍</div>
        <div className="state-title">No Evidence</div>
        <div className="state-sub">Evidence will appear after running an analysis.</div>
      </div>
    )
  }

  return (
    <div className="tab-content">
      <h3 style={{ marginBottom: 16, color: 'var(--text-secondary)' }}>
        Cypher Queries & Evidence — {evidence.length} {evidence.length === 1 ? 'query' : 'queries'} run
      </h3>
      <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>
        Rows below are raw query results (one row per path). The summary panel counts each production caller once, keeping its shortest path, so row counts can be higher than the caller count.
      </p>
      {evidence.map((ev, i) => {
        const cypher = (ev.cypher || '').trim()
        const params = ev.params || {}
        const rows = ev.rows || []
        const ms = ev.duration_ms ?? '?'
        const rowCount = ev.row_count ?? rows.length

        return (
          <div key={i} className="evidence-item">
            <div className="evidence-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="evidence-ms">{ms} ms</span>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>· {rowCount} row{rowCount !== 1 ? 's' : ''}</span>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <CopyBtn text={cypher} label="Copy Cypher" />
              </div>
            </div>
            <div className="evidence-body">
              <div className="code-block code-cypher">{cypher}</div>
              {Object.keys(params).length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 4 }}>Parameters</div>
                  <div className="code-block" style={{ color: 'var(--text-secondary)' }}>
                    {JSON.stringify(params, null, 2)}
                  </div>
                </div>
              )}
              {rows.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 4 }}>Rows</div>
                  <div className="code-block" style={{ color: 'var(--accent-green)', maxHeight: 120, overflow: 'auto' }}>
                    {JSON.stringify(rows, null, 2)}
                  </div>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
