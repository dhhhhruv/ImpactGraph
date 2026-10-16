import React, { useState } from 'react'

export default function CopyBtn({ text, label = 'Copy' }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }
  return (
    <button className={`copy-btn ${copied ? 'copied' : ''}`} onClick={handleCopy} type="button">
      {copied ? '✓ Copied' : label}
    </button>
  )
}
