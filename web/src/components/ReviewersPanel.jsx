import React from 'react'

const MEDAL = ['🥇', '🥈', '🥉']

export default function ReviewersPanel({ reviewers }) {
  return (
    <div className="section">
      <div className="section-title">
        <div className="dot" style={{ background: 'var(--accent-purple)' }} />
        Suggested Reviewers
      </div>
      {(!reviewers || reviewers.length === 0) ? (
        <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>No reviewer candidates found.</div>
      ) : (
        <div className="item-list">
          {reviewers.map((r, i) => (
            <div key={i} className="item-row" style={{ cursor: 'default' }}>
              <div className="reviewer-rank">{MEDAL[i] || (i + 1)}</div>
              <div className="item-row-content">
                <div className="item-row-main" style={{ fontFamily: 'var(--font-sans)' }}>{r.author || '—'}</div>
                <div className="item-row-sub">
                  {r.files_covered} file{r.files_covered !== 1 ? 's' : ''} · {r.commits} commit{r.commits !== 1 ? 's' : ''}
                </div>
              </div>
              <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--accent-purple)', fontWeight: 700 }}>
                {r.score?.toFixed(3)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
