import React, { useMemo } from 'react'
import CopyBtn from './CopyBtn'

export default function TestsPanel({ affectedTests, onSelect, selectedId }) {
  const pytestCmd = useMemo(() => {
    if (!affectedTests?.length) return ''
    const files = [...new Set(affectedTests.map(t => t.file).filter(Boolean))]
    return 'pytest ' + files.join(' ')
  }, [affectedTests])

  return (
    <div className="section">
      <div className="section-title">
        <div className="dot" style={{ background: 'var(--accent-green)' }} />
        Tests to Run
        {affectedTests?.length > 0 && (
          <span className="badge" style={{ marginLeft: 'auto', background: 'rgba(52,211,153,0.12)', color: 'var(--accent-green)', border: '1px solid rgba(52,211,153,0.25)', fontSize: '11px' }}>
            {affectedTests.length}
          </span>
        )}
      </div>

      {(!affectedTests || affectedTests.length === 0) ? (
        <span className="finding-badge">⚠ Finding: No test reaches this change</span>
      ) : (
        <>
          <div className="item-list scroll-inner" style={{ marginBottom: '12px' }}>
            {affectedTests.map((t, i) => {
              const id = t.test || `test-${i}`
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
                  <div className="item-row-icon" style={{ background: 'var(--node-test)' }} />
                  <div className="item-row-content">
                    <div className="item-row-main">{t.test || '—'}</div>
                    {t.file && <div className="item-row-sub">{t.file}</div>}
                  </div>
                  {t.hops != null && (
                    <span className="badge" style={{ background: 'rgba(17,19,24,0.8)', color: 'var(--text-muted)', border: '1px solid var(--border)', fontSize: '10px' }}>
                      {t.hops}h
                    </span>
                  )}
                </div>
              )
            })}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Run command</span>
            <CopyBtn text={pytestCmd} label="Copy pytest" />
          </div>
          <div className="code-block">{pytestCmd}</div>
        </>
      )}
    </div>
  )
}
