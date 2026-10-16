import React, { useState } from 'react'
import { askQuestion } from '../api'

export default function AskBox({ repo }) {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState(null)
  const [error, setError] = useState(null)

  const handleAsk = async () => {
    if (!question.trim()) return
    setLoading(true)
    setError(null)
    try {
      const result = await askQuestion({ repo, question })
      setResponse(result)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="section">
      <div className="section-title">
        <div className="dot" style={{ background: 'var(--accent-blue)' }} />
        Ask the Graph
      </div>
      <div className="ask-box">
        <input
          id="ask-input"
          type="text"
          placeholder="e.g. Who changed this most recently?"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleAsk()}
          style={{ flex: 1 }}
        />
        <button
          id="ask-submit-btn"
          className="btn btn-ghost btn-sm"
          onClick={handleAsk}
          disabled={loading || !question.trim()}
          type="button"
        >
          {loading ? <div className="spinner" style={{ width: 14, height: 14 }} /> : 'Ask'}
        </button>
      </div>
      {error && <div className="ask-response" style={{ color: 'var(--accent-red)' }}>Error: {error}</div>}
      {response && (
        <div className="ask-response">
          <div style={{ marginBottom: '6px' }}>{response.answer}</div>
          {response.evidence_rows?.length > 0 && (
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              {response.evidence_rows.length} graph row{response.evidence_rows.length !== 1 ? 's' : ''} returned
            </div>
          )}
        </div>
      )}
    </div>
  )
}
