import React from 'react'

const RISK_COLOR = {
  low: 'var(--risk-low)',
  medium: 'var(--risk-medium)',
  high: 'var(--risk-high)',
  critical: 'var(--risk-critical)',
}

const FACTORS = [
  { key: 'blast_component',    label: 'Blast Radius',  color: 'var(--accent-orange)' },
  { key: 'pagerank_component', label: 'PageRank',      color: 'var(--accent-purple)' },
  { key: 'uncovered_component',label: 'Uncovered Tests',color: 'var(--accent-red)'   },
  { key: 'churn_component',    label: 'Churn',         color: 'var(--accent-yellow)' },
]

export default function RiskCard({ risk }) {
  if (!risk) return null
  const color = RISK_COLOR[risk.label] || 'var(--text-secondary)'
  const factors = risk.factors || {}

  return (
    <div className="section">
      <div className="section-title">
        <div className="dot" style={{ background: color }} />
        Risk Assessment
      </div>
      <div className="risk-gauge-wrap">
        <div className="risk-score-big" style={{ color }}>{risk.score?.toFixed(3) ?? '—'}</div>
        <span className={`badge badge-${risk.label}`}>{risk.label?.toUpperCase()}</span>
      </div>

      <div className="risk-factors">
        {FACTORS.map(f => {
          const val = factors[f.key] ?? 0
          const pct = Math.min(val * 100 / 0.5, 100)
          return (
            <div key={f.key} className="risk-factor">
              <span className="risk-factor-label">{f.label}</span>
              <div className="risk-factor-bar-bg">
                <div className="risk-factor-bar" style={{ width: `${pct}%`, background: f.color }} />
              </div>
              <span className="risk-factor-val">{val.toFixed(3)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
