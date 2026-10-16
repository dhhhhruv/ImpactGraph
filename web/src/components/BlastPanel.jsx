import React from 'react'

export default function BlastPanel({ blastRadius, onSelect, selectedId }) {
  if (!blastRadius || blastRadius.length === 0) {
    return (
      <div className="section">
        <div className="section-title">
          <div className="dot" style={{ background: 'var(--accent-orange)' }} />
          Blast Radius
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
          No callers identified — change is isolated.
        </div>
      </div>
    )
  }

  return (
    <div className="section">
      <div className="section-title">
        <div className="dot" style={{ background: 'var(--accent-orange)' }} />
        Blast Radius
        <span className="badge" style={{ marginLeft: 'auto', background: 'rgba(251,146,60,0.12)', color: 'var(--accent-orange)', border: '1px solid rgba(251,146,60,0.25)', fontSize: '11px' }}>
          {blastRadius.length} caller{blastRadius.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="item-list scroll-inner">
        {blastRadius.map((row, i) => {
          const id = row.affected || row.via || `caller-${i}`
          const isActive = selectedId === id
          return (
            <div
              key={i}
              className={`item-row ${isActive ? 'active' : ''}`}
              onClick={() => onSelect(isActive ? null : id)}
              role="button"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && onSelect(isActive ? null : id)}
            >
              <div className="item-row-icon" style={{ background: 'var(--node-caller)' }} />
              <div className="item-row-content">
                <div className="item-row-main">{row.affected || '—'}</div>
                {row.via && <div className="item-row-sub">via {row.via}</div>}
              </div>
              {row.hops != null && (
                <span className="badge" style={{ background: 'rgba(17,19,24,0.8)', color: 'var(--text-muted)', border: '1px solid var(--border)', fontSize: '10px' }}>
                  {row.hops}h
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
