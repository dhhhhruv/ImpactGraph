# ImpactGraph

> **Graph-powered pull request impact analysis.** When a PR arrives, ImpactGraph asks a FalkorDB graph of your codebase and its git history: *what can this change break, which tests should run, who should review it, how risky is it?* Every claim in the output carries its graph path.

Built for **[FalkorDB Hackathon — Track 01: Agents That Act on Connected Data](https://falkordb.com/)**.

---

## How it works

```
PR diff → AST parser → FalkorDB graph → 6 graph queries → risk score + blast radius + tests + reviewers
                                                        ↓
                                               LLM explains (never invents)
                                                        ↓
                                               GitHub PR comment + React UI
```

- **Graph (~60%)** finds facts: affected functions, reachable tests, reviewer candidates, risk score, call paths.
- **LLM (~40%)** explains and decides: picks what to investigate next, writes the "why this matters" text.
- The LLM **never invents** a name, test, file, or person — only values returned by graph tools are used.

**Target repo:** [`borgbase/vorta`](https://github.com/borgbase/vorta) (open-source backup client).

---

## Features

| Feature | Details |
|---|---|
| **Blast radius** | Call-graph traversal (up to 3 hops) to find every function that can reach changed code |
| **Affected tests** | Shortest path (up to 4 hops) from `Test` nodes back to changed functions |
| **Reviewer recommendation** | Ranked by files covered × commit recency × score formula |
| **Risk scoring** | Objective formula: blast ratio + PageRank centrality + uncovered test ratio + churn |
| **Graph evidence** | Every Cypher query, its parameters, row count, and duration logged to the UI |
| **Benchmark** | 40 PRs, graph vs. 5 baselines (most-recent-committer, flat-count, same-name test, grep-imports, LLM-only) |
| **Demo cache** | 5 pre-generated PR analyses; app works without a live AI key |
| **Dark UI** | React 18 + Vite + Cytoscape.js (fcose) — click any node to dim everything else |

---

## Architecture

```
impactgraph/
├── ingest/
│   ├── ast_parser.py       # Walk .py files via ast; build qnames + CALLS edges
│   ├── git_history.py      # pydriller → Author/Commit/TOUCHED edges
│   └── load_graph.py       # FalkorDB bulk-load (UNWIND batches of 500) + PageRank
├── graph/
│   ├── client.py           # GraphClient with evidence logging
│   ├── queries.py          # Q0–Q5: diff→fns, blast, tests, proof path, reviewers, centrality, churn
│   └── risk.py             # calculate_risk() — pure formula, no LLM
├── mcp_server/
│   └── server.py           # MCP tools wrapping Q0–Q5 for agent use
├── agent/
│   ├── loop.py             # run_impact_agent() — orchestrates all queries + risk
│   ├── comment.py          # format_pr_comment() + validate_decision() hallucination filter
│   └── prompts.py          # Template-based summary generation
├── api/
│   └── main.py             # FastAPI: /health /repos /analyze /subgraph /ask /benchmark /demo/{id}
├── benchmark/
│   ├── collect_prs.py      # Download PR data once, save as JSON
│   ├── run.py              # Benchmark runner (graph queries only, no LLM)
│   ├── baselines.py        # 5 baselines + LLM-only
│   └── results.md          # Results table
├── web/                    # React 18 + Vite frontend
│   └── src/
│       ├── App.jsx          # Main layout: topbar + left panel + right panel
│       ├── api.js           # Fetch wrappers for all endpoints
│       └── components/
│           ├── RiskCard.jsx        # Gauge + 4-factor bars
│           ├── BlastPanel.jsx      # Blast radius list (click → highlight graph)
│           ├── TestsPanel.jsx      # Tests + "No test reaches this change" finding
│           ├── ReviewersPanel.jsx  # Ranked reviewers
│           ├── AskBox.jsx          # POST /ask
│           ├── GraphCanvas.jsx     # Cytoscape.js canvas, fcose layout
│           ├── EvidenceTab.jsx     # Cypher + params + rows + Copy button
│           └── BenchmarkTab.jsx    # Metric bars + per-PR table + limitations
├── demo_cache/             # 5 pre-generated PR analyses
├── queries.cypher          # All Cypher queries (canonical)
├── AGENTS.md               # Source of truth for schema + coding rules
└── docker-compose.yml      # FalkorDB + API
```

---

## Graph schema

```
Nodes:  File {path, loc}
        Function {qname, name, file, start, end, pagerank}
        Test      ← extra label on Function when name starts with test_ in tests/
        Author {email, name}
        Commit {sha, ts, msg}

Edges:  (File)   -[:DEFINES]->  (Function)
        (Function)-[:CALLS]->   (Function)
        (File)   -[:IMPORTS]->  (File)
        (Author) -[:AUTHORED]-> (Commit)
        (Commit) -[:TOUCHED {added, deleted}]-> (File)
```

> **Honest limit:** call links are name-based and approximate. Documented here so you know.

---

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose
- A GitHub personal access token (for ingestion only)

### 1 — Clone & environment

```bash
git clone https://github.com/<you>/impactgraph.git
cd impactgraph

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy the example env file and fill in your tokens:

```bash
cp .env.example .env
# Edit .env:
#   GITHUB_TOKEN=ghp_...
#   OPENAI_API_KEY=sk-...   (optional — app works without it via demo cache)
#   FALKOR_HOST=localhost
#   FALKOR_PORT=6379
```

### 2 — Start FalkorDB

```bash
docker compose up falkordb -d
# Verify:
docker compose ps
# FalkorDB browser UI → http://localhost:3000
```

### 3 — Ingest borgbase/vorta

```bash
# Clone the target repo
mkdir -p repos && git clone https://github.com/borgbase/vorta repos/vorta

# Build the graph (takes ~2–3 min on first run)
python -m ingest.load_graph --repo borgbase/vorta --src repos/vorta --rebuild
```

This bulk-loads ~5,000 nodes and edges, runs PageRank, and prints a summary.

### 4 — Start the API

```bash
uvicorn api.main:app --reload --port 8000
# Health check → http://localhost:8000/health
```

### 5 — Start the frontend

```bash
cd web
npm install
npm run dev
# → http://localhost:5173
```

Open `http://localhost:5173`. Click **Demo** to explore pre-computed results without needing a live AI key, or enter a PR number and click **⚡ Analyze**.

### 6 — Run tests

```bash
pytest tests/ -v
# Expected: 35+ tests across ast_parser, queries, risk, comment, api, benchmark
```

---

## Running the benchmark

```bash
# Download PR data (one-time, saves to benchmark/prs.json)
python -m benchmark.collect_prs --repo borgbase/vorta --count 40

# Run benchmark (graph queries only, no LLM, no future leakage)
python -m benchmark.run --repo borgbase/vorta

# Results → benchmark/results.md and benchmark/results.json
```

---

## Docker (full stack)

```bash
docker compose up --build
# API  → http://localhost:8000
# UI   → serve web/dist/ with any static host (e.g. npx serve web/dist)
# FalkorDB → http://localhost:3000
```

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | API + FalkorDB status |
| GET | `/repos` | List ingested repositories |
| POST | `/analyze` | Full impact analysis on a PR diff |
| GET | `/subgraph` | Cytoscape-formatted subgraph for changed functions |
| POST | `/ask` | Answer free-form questions from the graph |
| GET | `/benchmark` | Latest benchmark results JSON |
| GET | `/demo/{id}` | Pre-generated demo PR (id 1–5) |

### Example: analyze a change

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "borgbase/vorta",
    "diff_hunks": [{"path": "src/vorta/scheduler/execution.py", "start": 5, "end": 25}],
    "head_sha": "abc123"
  }'
```

---

## UI walkthrough

**Top bar:** repo selector · PR number input · Analyze button · Dry-run toggle · Graph on/off · Demo mode

**Left panel (40%):**
- AI-written summary (clearly labelled)
- Risk card — score, label, 4-factor breakdown bars
- Blast radius — clickable list; clicking a row dims all non-adjacent graph nodes
- Tests to run — with `pytest` command and one-click copy; "**Finding: No test reaches this change**" when empty
- Suggested reviewers — ranked by coverage + recency
- Ask the graph — free-form questions answered by live Cypher

**Right panel (60%):**
- **Graph tab** — Cytoscape.js canvas (fcose layout); changed=red, callers=orange, tests=green, reviewers=purple; click any node to highlight its neighborhood (everything else dims to 20%); node size follows PageRank; capped at 150 nodes
- **Graph OFF** — flat baseline view beside the graph answer
- **Evidence tab** — every Cypher query with params, row count, duration, and a Copy button
- **Benchmark tab** — metric bars (ImpactGraph vs baselines vs LLM-only), per-PR table, method & limitations

---

## Benchmark results

See [`benchmark/results.md`](benchmark/results.md) for the full table.

Baselines compared:
- **most_recent_committer** — last author to touch each changed file
- **flat_commit_count** — authors ranked by raw commit count
- **same_name_test** — `tests/test_<stem>.py` naming heuristic
- **grep_imports** — test files importing changed modules
- **LLM-only** — title + @mention heuristic, zero graph evidence

All benchmark queries use history strictly before each PR's base commit timestamp — no future leakage.

---

## Disclosure

AI coding assistants (Google Antigravity, Cursor) were used in this project to accelerate development. All graph schema, query logic, risk formulas, and benchmark methodology were designed and reviewed by the team.

---

## License

MIT
=======
# ImpactGraph
