const BASE = '/api'

export async function fetchHealth() {
  const r = await fetch(`${BASE}/health`)
  if (!r.ok) throw new Error('API unreachable')
  return r.json()
}

export async function fetchRepos() {
  const r = await fetch(`${BASE}/repos`)
  if (!r.ok) throw new Error('Failed to fetch repos')
  return r.json()
}

export async function fetchRepoPrs(repo = 'borgbase/vorta') {
  const r = await fetch(`${BASE}/repos/${repo}/prs`)
  if (!r.ok) return []
  return r.json()
}

export async function analyzeChange({ repo, diffHunks, headSha, beforeTs, prAuthor, maxHops = 4 }) {
  const r = await fetch(`${BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      repo,
      diff_hunks: diffHunks,
      head_sha: headSha,
      before_ts: beforeTs,
      pr_author: prAuthor,
      max_hops: maxHops,
    }),
  })
  if (!r.ok) throw new Error(`Analysis failed: ${r.status}`)
  return r.json()
}

export async function fetchSubgraph(repo, changed, maxHops = 4) {
  const params = new URLSearchParams({ repo, max_hops: String(maxHops) })
  if (changed?.length) params.set('changed', changed.join(','))
  const r = await fetch(`${BASE}/subgraph?${params}`)
  if (!r.ok) throw new Error('Subgraph fetch failed')
  return r.json()
}

export async function askQuestion({ repo, question, targetFunction }) {
  const r = await fetch(`${BASE}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo, question, target_function: targetFunction }),
  })
  if (!r.ok) throw new Error('Ask failed')
  return r.json()
}

export async function fetchBenchmark() {
  const r = await fetch(`${BASE}/benchmark`)
  if (!r.ok) throw new Error('Benchmark fetch failed')
  return r.json()
}

export async function fetchDemo(id, maxHops = 4) {
  const path = Number(id) === 2560
    ? `${BASE}/demo/featured?max_hops=${maxHops}`
    : `${BASE}/demo/${id}`
  const r = await fetch(path)
  if (!r.ok) throw new Error(`Demo ${id} not found`)
  return r.json()
}
