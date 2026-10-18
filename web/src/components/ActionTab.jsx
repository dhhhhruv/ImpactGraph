import React, { useState, useEffect } from 'react'
import { previewAction } from '../api'
import CopyBtn from './CopyBtn'

export default function ActionTab({ decision }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setResult(null)
    setError(null)
  }, [decision])

  if (!decision) {
    return (
      <div className="state-center">
        <div className="state-icon">🚀</div>
        <div className="state-title">No Decision Yet</div>
        <div className="state-sub">Run an analysis first, then preview the PR action.</div>
      </div>
    )
  }

  const run = async () => {
    setLoading(true)
    setError(null)
    try {
      setResult(await previewAction(decision))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="tab-content">
      <h3 style={{ marginBottom: 8, color: 'var(--text-secondary)' }}>PR Action (dry run)</h3>
      <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
        Dry run: nothing is posted. This shows the comment, label, reviewer requests and test command
        built from the agent's decision. It makes no model call and no GitHub call.
      </p>
      <button className="tab-btn active" type="button" onClick={run} disabled={loading}>
        {loading ? 'Building preview...' : 'Preview PR action'}
      </button>
      {error && <div style={{ color: 'var(--accent-red, #f87171)', marginTop: 12 }}>{error}</div>}
      {result && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, marginBottom: 6 }}>
            <strong>Label:</strong> {result.label.replace('dry_run_label_', '')}
            {' · '}
            <strong>Would request review from:</strong> {result.reviewers.join(', ') || 'none'}
            {' · '}
            <strong>Posted:</strong> {String(result.posted)}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', margin: '10px 0 4px' }}>Test command</div>
          <div className="code-block">{result.pytest_command}</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', margin: '10px 0 4px' }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>PR comment (would be posted)</span>
            <CopyBtn text={result.pr_comment} label="Copy comment" />
          </div>
          <div className="code-block" style={{ maxHeight: 360, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
            {result.pr_comment}
          </div>
        </div>
      )}
    </div>
  )
}
